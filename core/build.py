"""Build runner orchestrating Dockerfile analysis, rendering, and metrics capture."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from .analyzer import build_analysis_payload, perform_analysis
from .config import CodiEnvironment
from .detect import DetectionResult
from .llm import (
    AssistCandidate,
    AssistContext,
    AssistDetection,
    ImageMetricsSnapshot,
    LLMAssist,
    LLMRankingService,
    RAGMatchReference,
    RankingResult,
    TemplateRecommendation,
)
from .parse import DockerfileDocument, DockerStage
from .render import (
    CandidateValidationError,
    NoMatchingRulesError,
    RenderContext,
    RenderedCandidate,
    RenderError,
    add_llm_rationale_comment,
    build_cmd_runtime_summary,
    extract_cmd_render_context,
    render_for_stack,
)
from .rules import AllowedStack
from .security import SecurityPolicyError, enforce_airgap_guard, validate_or_raise
from .store import RAGIndex, RAGMatch, RunStore, create_run_store

__all__ = [
    "AssistResult",
    "BuildCandidateResult",
    "BuildMetrics",
    "BuildRunResult",
    "BuildRunner",
    "BuildRunnerError",
    "CmdRunSummary",
]


class BuildRunnerError(RuntimeError):
    """Base exception for build runner failures."""


@dataclass(slots=True)
class BuildMetrics:
    size_bytes: int
    layers: int
    build_seconds: float
    mode: str  # "dry_run" | "real"

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - exercised in integration tests
        return {
            "size_bytes": self.size_bytes,
            "layers": self.layers,
            "build_seconds": self.build_seconds,
            "mode": self.mode,
        }


@dataclass(slots=True)
class BuildTimings:
    analysis_seconds: float
    render_seconds: float
    total_seconds: float

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - exercised in integration tests
        return {
            "analysis_seconds": self.analysis_seconds,
            "render_seconds": self.render_seconds,
            "total_seconds": self.total_seconds,
        }


@dataclass(slots=True)
class BuildCandidateResult:
    rule_id: str
    name: str | None
    description: str | None
    rationale: Sequence[str]
    policy_notes: Sequence[str]
    dockerfile_path: str
    metrics: BuildMetrics

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - exercised in integration tests
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "rationale": list(self.rationale),
            "policy_notes": list(self.policy_notes),
            "dockerfile_path": self.dockerfile_path,
            "metrics": self.metrics.to_dict(),
        }


@dataclass(slots=True)
class OriginalBuildResult:
    dockerfile_path: str
    metrics: BuildMetrics

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - exercised in integration tests
        return {
            "dockerfile_path": self.dockerfile_path,
            "metrics": self.metrics.to_dict(),
        }


@dataclass(slots=True)
class AssistResult:
    summary: str
    recommendation: TemplateRecommendation | None

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - exercised in integration tests
        return {
            "summary": self.summary,
            "recommendation": self.recommendation.to_dict() if self.recommendation else None,
        }


@dataclass(slots=True)
class BuildRunResult:
    run_id: str
    run_dir: Path
    stack: AllowedStack
    detection: DetectionResult
    original: OriginalBuildResult
    candidates: Sequence[BuildCandidateResult]
    mode: str
    assist: AssistResult | None
    environment: CodiEnvironment
    timings: BuildTimings
    cmd: CmdRunSummary | None

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - exercised in integration tests
        return {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "stack": self.stack,
            "mode": self.mode,
            "detection": asdict(self.detection),
            "original": self.original.to_dict(),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "assist": self.assist.to_dict() if self.assist else None,
            "environment": self.environment.to_metadata(),
            "timings": self.timings.to_dict(),
            "cmd": self.cmd.to_dict() if self.cmd else None,
        }


@dataclass(slots=True)
class CmdRunSummary:
    analysis: dict[str, Any] | None
    runtime: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - convenience wrapper
        payload: dict[str, Any] = {}
        if self.analysis is not None:
            payload["analysis"] = self.analysis
        if self.runtime is not None:
            payload["runtime"] = self.runtime
        return payload


@dataclass(slots=True)
class LLMSummary:
    run_payload: dict[str, Any]
    metrics_payload: dict[str, Any]
    ranking_entries: Sequence[dict[str, Any]]


class BuildRunner:
    """High-level orchestrator for executing the CODI build pipeline."""

    def __init__(
        self,
        project_root: Path,
        output_root: Path,
        *,
        real_builds: bool = False,
        candidate_limit: int | None = 2,
        environment: CodiEnvironment | None = None,
    ) -> None:
        self.project_root = project_root
        self.output_root = output_root
        self.real_builds = real_builds
        self.candidate_limit = candidate_limit
        base_env = environment or CodiEnvironment.from_env()
        self.environment = base_env.with_output_root(output_root)

    def run(self) -> BuildRunResult:
        enforce_airgap_guard()
        overall_start = time.perf_counter()

        analysis_start = time.perf_counter()
        dockerfile_path = self._locate_dockerfile()

        analysis = perform_analysis(self.project_root, dockerfile_path=dockerfile_path)
        try:
            validate_or_raise(analysis.document)
        except SecurityPolicyError as exc:
            raise BuildRunnerError(str(exc)) from exc

        document = analysis.document
        detection = analysis.detection
        stack = detection.stack
        if stack not in {"node", "python", "java"}:
            raise BuildRunnerError("Unable to determine supported stack (node/python/java).")

        analysis_duration = time.perf_counter() - analysis_start

        allowed_stack = cast(AllowedStack, stack)
        store = create_run_store(
            self.output_root,
            stack=allowed_stack,
            label=self.project_root.name,
        )

        store.snapshot_file(dockerfile_path, destination_name="Dockerfile")
        store.write_json("metadata/detect.json", asdict(detection))

        analysis_payload = build_analysis_payload(analysis)
        analysis_payload["project_root"] = str(self.project_root)
        analysis_payload["dockerfile_path"] = str(dockerfile_path)
        analysis_payload["mode"] = "run"
        store.write_json("metadata/analysis.json", analysis_payload)

        render_context = self._build_render_context(allowed_stack, document, analysis=analysis)

        start_time = time.perf_counter()
        candidates = self._render_candidates(render_context)
        render_duration = time.perf_counter() - start_time
        cmd_runtime_snapshot = build_cmd_runtime_summary(render_context)

        original_metrics = self._build_metrics(document)
        original = OriginalBuildResult(
            dockerfile_path=str(store.paths.inputs / "Dockerfile"),
            metrics=original_metrics,
        )

        candidate_results, assist_candidates = self._persist_candidates(store, candidates)

        rag_tokens = _build_rag_tokens(
            detection=detection,
            context=render_context,
            original_metrics=original_metrics,
            candidates=candidate_results,
        )

        rag_index = RAGIndex(self.output_root)
        rag_matches = rag_index.query_similar(
            stack=allowed_stack,
            tokens=rag_tokens,
            exclude_run_id=None,
        )

        rag_payload = {
            "query_tokens": sorted({token for token in rag_tokens}),
            "matches": [match.to_dict() for match in rag_matches],
        }

        store.write_json("metadata/rag.json", rag_payload)

        assist_context = _build_assist_context(
            project_name=self.project_root.name,
            detection=detection,
            render_context=render_context,
            original_metrics=original_metrics,
            candidates=assist_candidates,
            rag_matches=rag_matches,
        )

        env_settings = self.environment
        assist_engine = LLMAssist.from_settings(env_settings)
        assist_summary = assist_engine.summarise(assist_context)
        assist_recommendation = assist_engine.recommend_template(assist_context)
        assist_result = AssistResult(summary=assist_summary, recommendation=assist_recommendation)
        assist_payload = assist_result.to_dict()

        ranking_service = LLMRankingService.from_settings(env_settings)
        ranking_result = ranking_service.rank_candidates(assist_context)
        llm_summary = _summarise_llm_result(
            run_id=store.run_id,
            ranking_result=ranking_result,
            candidates=candidate_results,
        )
        store.write_json("metadata/llm_metrics.json", llm_summary.metrics_payload)
        _annotate_candidates_with_llm(
            ranking_entries=llm_summary.ranking_entries,
            adapter_version=ranking_result.adapter_version,
            rationale=ranking_result.rationale,
            total_candidates=len(candidate_results),
        )

        mode = "real" if self.real_builds else "dry_run"
        total_duration = time.perf_counter() - overall_start

        timings = BuildTimings(
            analysis_seconds=round(analysis_duration, 4),
            render_seconds=round(render_duration, 4),
            total_seconds=round(total_duration, 4),
        )

        cmd_analysis_payload = analysis_payload.get("cmd_analysis")
        cmd_summary: CmdRunSummary | None = None
        if cmd_analysis_payload is not None or cmd_runtime_snapshot is not None:
            cmd_summary = CmdRunSummary(
                analysis=cmd_analysis_payload if isinstance(cmd_analysis_payload, dict) else None,
                runtime=cmd_runtime_snapshot,
            )

        run_summary: dict[str, Any] = {
            "run_id": store.run_id,
            "stack": allowed_stack,
            "mode": mode,
            "project_root": str(self.project_root),
            "created_at": store.run_id.split("-")[0],
            "environment": env_settings.to_metadata(),
            "metrics": {
                "analysis_seconds": timings.analysis_seconds,
                "render_seconds": timings.render_seconds,
                "total_seconds": timings.total_seconds,
            },
            "analysis": analysis_payload,
            "original": original.to_dict(),
            "candidates": [candidate.to_dict() for candidate in candidate_results],
            "detection": asdict(detection),
            "rag": rag_payload,
            "assist": assist_payload,
            "llm": llm_summary.run_payload,
        }

        if cmd_summary:
            run_summary["cmd"] = cmd_summary.to_dict()

        store.write_json("metadata/run.json", run_summary)
        store.write_json("metadata/environment.json", env_settings.to_metadata())
        if cmd_summary and cmd_summary.analysis:
            store.write_json("metadata/cmd_analysis.json", cmd_summary.analysis)
        if cmd_summary and cmd_summary.runtime:
            store.write_json("metadata/cmd_runtime.json", cmd_summary.runtime)

        rag_index.upsert(
            run_id=store.run_id,
            stack=allowed_stack,
            label=self.project_root.name,
            created_at=run_summary["created_at"],
            run_dir=store.paths.root,
            tokens=rag_tokens,
            payload={
                "project_root": str(self.project_root),
                "original_metrics": original.metrics.to_dict(),
                "candidate_rules": [candidate.rule_id for candidate in candidate_results],
            },
        )

        return BuildRunResult(
            run_id=store.run_id,
            run_dir=store.paths.root,
            stack=allowed_stack,
            detection=detection,
            original=original,
            candidates=candidate_results,
            mode=mode,
            assist=assist_result,
            environment=env_settings,
            timings=timings,
            cmd=cmd_summary,
        )

    # ---------------------------------------------------------------------
    # Helper methods
    # ---------------------------------------------------------------------

    def _locate_dockerfile(self) -> Path:
        dockerfile_path = self.project_root / "Dockerfile"
        if dockerfile_path.exists():
            return dockerfile_path
        for candidate in ("docker/Dockerfile", "Dockerfile.dev", "Dockerfile.release"):
            path = self.project_root / candidate
            if path.exists():
                return path
        raise BuildRunnerError("Unable to locate a Dockerfile in the target project.")

    def _build_render_context(
        self,
        stack: AllowedStack,
        document: DockerfileDocument,
        *,
        analysis: Any,
    ) -> RenderContext:
        context = RenderContext(stack=stack)
        for path in _collect_files(self.project_root):
            context.add_file(path)
        for lockfile in _collect_lockfiles(self.project_root):
            context.add_lockfile(lockfile)
        for feature in _collect_features(stack, self.project_root):
            context.add_feature(feature)
        context.variables.update(
            {
                "project_name": self.project_root.name,
                "stage_count": len(document.stages),
            }
        )

        cmd_context = extract_cmd_render_context(getattr(analysis, "cmd", None))
        if cmd_context:
            context.cmd = cmd_context
            context.variables.setdefault(
                "cmd_flags",
                {key: bool(value) for key, value in cmd_context.flags.items()},
            )

        return context

    def _render_candidates(self, context: RenderContext) -> Sequence[RenderedCandidate]:
        try:
            return render_for_stack(context, limit=self.candidate_limit)
        except (NoMatchingRulesError, CandidateValidationError, RenderError) as exc:
            raise BuildRunnerError(str(exc)) from exc

    def _persist_candidates(
        self,
        store: RunStore,
        candidates: Sequence[RenderedCandidate],
    ) -> tuple[list[BuildCandidateResult], list[AssistCandidate]]:
        results: list[BuildCandidateResult] = []
        assist_candidates: list[AssistCandidate] = []
        for index, candidate in enumerate(candidates, start=1):
            filename = f"{index:03d}-{candidate.rule_id}.Dockerfile"
            target = store.write_candidate(filename, candidate.content)
            metrics = self._build_metrics(candidate.document)
            results.append(
                BuildCandidateResult(
                    rule_id=candidate.rule_id,
                    name=candidate.name,
                    description=candidate.description,
                    rationale=candidate.rationale,
                    policy_notes=candidate.policy_notes,
                    dockerfile_path=str(target),
                    metrics=metrics,
                )
            )
            assist_candidates.append(
                AssistCandidate(
                    rule_id=candidate.rule_id,
                    name=candidate.name,
                    description=candidate.description,
                    rationale=candidate.rationale,
                    policy_notes=candidate.policy_notes,
                    metrics=ImageMetricsSnapshot(
                        size_bytes=metrics.size_bytes,
                        layers=metrics.layers,
                        build_seconds=metrics.build_seconds,
                    ),
                )
            )
        return results, assist_candidates

    def _build_metrics(self, document: DockerfileDocument) -> BuildMetrics:
        if self.real_builds:
            return self._real_build_metrics(document)
        return _estimate_metrics(document)

    def _real_build_metrics(self, document: DockerfileDocument) -> BuildMetrics:
        # Placeholder for future implementation when BuildKit integration is available.
        raise BuildRunnerError(
            "Real builds are not yet supported; the runner operates in dry-run mode."
        )


def _summarise_llm_result(
    *,
    run_id: str,
    ranking_result: RankingResult,
    candidates: Sequence[BuildCandidateResult],
) -> LLMSummary:
    candidate_lookup: dict[str, BuildCandidateResult] = {
        f"candidate_{index}": candidate for index, candidate in enumerate(candidates, start=1)
    }

    ranking_entries: list[dict[str, Any]] = []
    for ranked in ranking_result.ranking:
        entry: dict[str, Any] = {
            "candidate_id": ranked.candidate_id,
            "rule_id": ranked.rule_id,
            "rank": ranked.rank,
            "score": round(float(ranked.score), 4),
        }
        candidate = candidate_lookup.get(ranked.candidate_id)
        if candidate:
            entry["dockerfile_path"] = candidate.dockerfile_path
            entry["metrics"] = candidate.metrics.to_dict()
            label = candidate.rule_id
            if candidate.name:
                label = f"{candidate.rule_id}:{candidate.name}"
            entry["label"] = label
        ranking_entries.append(entry)

    llm_metrics = dict(ranking_result.llm_metrics or {})
    run_payload = {
        "adapter_version": ranking_result.adapter_version,
        "rationale": ranking_result.rationale,
        "metrics": llm_metrics,
        "ranking": ranking_entries,
    }
    metrics_payload = {
        "run_id": run_id,
        **run_payload,
    }
    return LLMSummary(
        run_payload=run_payload, metrics_payload=metrics_payload, ranking_entries=ranking_entries
    )


def _annotate_candidates_with_llm(
    *,
    ranking_entries: Sequence[dict[str, Any]],
    adapter_version: str,
    rationale: str,
    total_candidates: int,
) -> None:
    if total_candidates <= 0 or not ranking_entries:
        return

    for entry in ranking_entries:
        path_value = entry.get("dockerfile_path")
        if not path_value:
            continue
        path = Path(path_value)
        if not path.exists():
            continue

        try:
            rank = int(entry.get("rank") or 0)
        except (TypeError, ValueError):
            rank = 0
        score_value = entry.get("score")
        score = None
        if isinstance(score_value, (int, float)):
            score = float(score_value)

        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue

        updated = add_llm_rationale_comment(
            content,
            rank=rank if rank > 0 else 1,
            total=total_candidates,
            score=score,
            adapter_version=adapter_version,
            rationale=rationale,
        )
        if updated != content:
            try:
                path.write_text(updated, encoding="utf-8")
            except OSError:
                continue


def _collect_files(root: Path) -> Iterable[str]:
    wanted = [
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "pom.xml",
        "Dockerfile",
    ]
    for name in wanted:
        path = root / name
        if path.exists():
            yield path.relative_to(root).as_posix()


def _collect_lockfiles(root: Path) -> Iterable[str]:
    lockfiles = [
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "poetry.lock",
        "Pipfile.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
    ]
    for name in lockfiles:
        path = root / name
        if path.exists():
            yield path.relative_to(root).as_posix()


def _collect_features(stack: AllowedStack, root: Path) -> Iterable[str]:
    if stack == "node":
        package_json = root / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            dependencies = {}
            dependencies.update(data.get("dependencies") or {})
            dependencies.update(data.get("devDependencies") or {})
            if any("next" in key.lower() for key in dependencies):
                yield "nextjs"
    elif stack == "python":
        requirements = root / "requirements.txt"
        if requirements.exists():
            content = requirements.read_text(encoding="utf-8").lower()
            if "fastapi" in content:
                yield "fastapi"
    elif stack == "java":
        pom = root / "pom.xml"
        if pom.exists():
            content = pom.read_text(encoding="utf-8").lower()
            if "spring-boot" in content:
                yield "spring-boot"


_BYTES_IN_MB = 1024 * 1024

_BASE_IMAGE_SIZES: dict[str, int] = {
    "node:20-alpine": 130 * _BYTES_IN_MB,
    "node:20-slim": 205 * _BYTES_IN_MB,
    "python:3.12-slim": 140 * _BYTES_IN_MB,
    "python:3.12": 210 * _BYTES_IN_MB,
    "eclipse-temurin:21-jre": 210 * _BYTES_IN_MB,
    "maven:3.9-eclipse-temurin-21": 430 * _BYTES_IN_MB,
    "maven:3.9.6-eclipse-temurin-21": 430 * _BYTES_IN_MB,
}

_DEFAULT_BASE_IMAGE_SIZE = 260 * _BYTES_IN_MB
_RUNTIME_LAYER_WEIGHT = 3 * _BYTES_IN_MB
_MULTISTAGE_SAVINGS = 45 * _BYTES_IN_MB
_CROSS_STAGE_COPY_BONUS = 12 * _BYTES_IN_MB
_NON_ROOT_SAVINGS = 12 * _BYTES_IN_MB
_CACHE_MOUNT_SAVINGS = 8 * _BYTES_IN_MB
_MIN_IMAGE_SIZE = 24 * _BYTES_IN_MB

_LAYER_IMPACT_KEYWORDS = {
    "RUN",
    "COPY",
    "ADD",
    "ENV",
    "EXPOSE",
    "WORKDIR",
    "CMD",
    "ENTRYPOINT",
    "USER",
}


def _estimate_metrics(document: DockerfileDocument) -> BuildMetrics:
    runtime_stage = document.stages[-1]
    multistage = len(document.stages) > 1

    base_size = _estimate_base_image_size(runtime_stage.base_image)
    runtime_layers = _count_layer_instructions(runtime_stage)
    heavy_penalty_bytes, heavy_penalty_seconds = _estimate_heavy_costs(runtime_stage)

    size_budget = base_size + (runtime_layers * _RUNTIME_LAYER_WEIGHT) + heavy_penalty_bytes

    savings = 0
    if multistage:
        savings += _MULTISTAGE_SAVINGS
        if _has_cross_stage_copy(document):
            savings += _CROSS_STAGE_COPY_BONUS
    if _uses_non_root_user(runtime_stage):
        savings += _NON_ROOT_SAVINGS
    if _has_cache_mount(document):
        savings += _CACHE_MOUNT_SAVINGS

    size_bytes = max(int(size_budget - savings), _MIN_IMAGE_SIZE)

    layer_count = _estimate_layer_count(runtime_stage, multistage)
    runtime_instruction_count = _count_layer_instructions(runtime_stage)
    builder_instruction_count = sum(
        _count_layer_instructions(stage) for stage in document.stages[:-1]
    )
    build_seconds = _estimate_build_time(
        runtime_instruction_count,
        builder_instruction_count,
        heavy_penalty_seconds,
        multistage,
    )

    return BuildMetrics(
        size_bytes=size_bytes,
        layers=layer_count,
        build_seconds=build_seconds,
        mode="dry_run",
    )


def _estimate_base_image_size(image: str) -> int:
    normalized = image.strip().lower()
    return _BASE_IMAGE_SIZES.get(normalized, _DEFAULT_BASE_IMAGE_SIZE)


def _count_layer_instructions(stage: DockerStage) -> int:
    return sum(
        1 for instruction in stage.instructions if instruction.keyword in _LAYER_IMPACT_KEYWORDS
    )


def _estimate_heavy_costs(stage: DockerStage) -> tuple[int, float]:
    size_penalty = 0
    time_penalty = 0.0

    for instruction in stage.instructions:
        text = f"{instruction.keyword} {instruction.arguments}".lower()

        if instruction.keyword == "RUN":
            if "npm install" in text:
                size_penalty += 38 * _BYTES_IN_MB
                time_penalty += 12.0
            if "npm ci" in text:
                size_penalty += 28 * _BYTES_IN_MB
                time_penalty += 10.0
            if "pip install" in text:
                if "/wheels" in text:
                    size_penalty += 12 * _BYTES_IN_MB
                    time_penalty += 5.0
                elif "-r" in text or "requirements" in text:
                    size_penalty += 42 * _BYTES_IN_MB
                    time_penalty += 16.0
                else:
                    size_penalty += 26 * _BYTES_IN_MB
                    time_penalty += 10.0
            if "apt-get install" in text:
                size_penalty += 18 * _BYTES_IN_MB
                time_penalty += 8.0
            if "mvn" in text:
                if "package" in text:
                    size_penalty += 55 * _BYTES_IN_MB
                    time_penalty += 22.0
                if "spring-boot:run" in text:
                    size_penalty += 70 * _BYTES_IN_MB
                    time_penalty += 18.0

        if instruction.keyword == "CMD":
            if "mvn" in instruction.arguments.lower():
                size_penalty += 48 * _BYTES_IN_MB
                time_penalty += 12.0

    return size_penalty, time_penalty


def _has_cross_stage_copy(document: DockerfileDocument) -> bool:
    for stage in document.stages:
        for instruction in stage.instructions:
            if instruction.keyword == "COPY" and "--from=" in instruction.arguments:
                return True
    return False


def _uses_non_root_user(stage: DockerStage) -> bool:
    for instruction in stage.instructions:
        if instruction.keyword != "USER":
            continue
        user = instruction.arguments.strip().strip("\"'")
        if user and user not in {"0", "root"}:
            return True
    return False


def _has_cache_mount(document: DockerfileDocument) -> bool:
    for stage in document.stages:
        for instruction in stage.instructions:
            if "--mount=type=cache" in instruction.arguments:
                return True
    return False


def _estimate_layer_count(stage: DockerStage, multistage: bool) -> int:
    base_layers = max(1, _count_layer_instructions(stage))
    if multistage:
        return max(2, round(base_layers * 0.7))
    return base_layers + 2


def _estimate_build_time(
    runtime_instructions: int,
    builder_instructions: int,
    heavy_penalty: float,
    multistage: bool,
) -> float:
    runtime_time = 10.0 + (runtime_instructions * 0.9) + heavy_penalty
    builder_time = builder_instructions * 0.35
    base_time = runtime_time + builder_time
    if multistage:
        base_time *= 0.9
    return round(max(base_time, 6.0), 2)


def _build_rag_tokens(
    *,
    detection: DetectionResult,
    context: RenderContext,
    original_metrics: BuildMetrics,
    candidates: Sequence[BuildCandidateResult],
) -> list[str]:
    tokens: list[str] = []

    tokens.append(f"stack:{detection.stack}")
    confidence_bucket = round(detection.confidence * 10)
    tokens.append(f"confidence:{confidence_bucket}")

    for category, items in detection.evidence.items():
        for item in items:
            parts = str(item).split(":", 1)
            signal = parts[0]
            tokens.append(f"evidence:{category}:{signal}")

    for feature in sorted(context.features):
        tokens.append(f"feature:{feature}")

    for lockfile in sorted(context.lockfiles):
        suffix = lockfile.split("/")[-1]
        tokens.append(f"lock:{suffix}")

    for file_name in sorted(context.files):
        suffix = Path(file_name).suffix or Path(file_name).name
        tokens.append(f"file:{suffix}")

    tokens.append(f"metric:layers:{_bucketize(original_metrics.layers, (4, 8, 12, 16))}")
    tokens.append(
        f"metric:size_mb:{_bucketize(round(original_metrics.size_bytes / _BYTES_IN_MB), (150, 250, 400, 600))}"
    )

    build_seconds_int = round(original_metrics.build_seconds)
    tokens.append(f"metric:seconds:{_bucketize(build_seconds_int, (10, 20, 40, 60))}")

    for candidate in candidates:
        tokens.append(f"rule:{candidate.rule_id}")
        for rationale in candidate.rationale:
            tokens.append(f"rationale:{_normalize_phrase(rationale)}")
        for note in candidate.policy_notes:
            tokens.append(f"policy:{_normalize_phrase(note)}")

    # Ensure determinism by sorting tokens with duplicates preserved based on their original order.
    return tokens


def _build_assist_context(
    *,
    project_name: str,
    detection: DetectionResult,
    render_context: RenderContext,
    original_metrics: BuildMetrics,
    candidates: Sequence[AssistCandidate],
    rag_matches: Sequence[RAGMatch],
) -> AssistContext:
    detection_snapshot = AssistDetection(
        stack=detection.stack,
        confidence=detection.confidence,
        evidence=detection.evidence,
    )

    original_snapshot = ImageMetricsSnapshot(
        size_bytes=original_metrics.size_bytes,
        layers=original_metrics.layers,
        build_seconds=original_metrics.build_seconds,
    )

    rag_references: list[RAGMatchReference] = []
    for match in rag_matches:
        candidate_rules = (
            match.payload.get("candidate_rules") if isinstance(match.payload, dict) else None
        )
        rules_tuple = tuple(candidate_rules) if candidate_rules else ()
        rag_references.append(
            RAGMatchReference(
                run_id=match.run_id,
                score=match.score,
                label=match.label,
                candidate_rules=rules_tuple,
            )
        )

    return AssistContext(
        project_name=project_name,
        detection=detection_snapshot,
        features=tuple(sorted(render_context.features)),
        files=tuple(sorted(render_context.files)),
        lockfiles=tuple(sorted(render_context.lockfiles)),
        original=original_snapshot,
        candidates=tuple(candidates),
        rag_matches=tuple(rag_references),
    )


def _bucketize(value: int, thresholds: Sequence[int]) -> str:
    for threshold in thresholds:
        if value <= threshold:
            return f"<= {threshold}"
    return f"> {thresholds[-1]}"


def _normalize_phrase(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    return cleaned.strip("-") or "na"
