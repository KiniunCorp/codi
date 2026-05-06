"""FastAPI service exposing CODI optimisation workflows.

The service offers four endpoints that mirror the CLI verbs:

``/analyze`` → Inspect a project Dockerfile and return structured metadata.
``/rewrite`` → Render deterministic candidate Dockerfiles from rules.yml.
``/run``     → Execute the end-to-end build pipeline and persist artefacts.
``/report``  → Generate Markdown + HTML reports for an existing run.

The implementation wraps existing core modules (parser, detector, renderer,
build runner, reporter) and focuses on translating their Pythonic results into
JSON-friendly response models suitable for clients embedding CODI.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.analyzer import build_analysis_payload, perform_analysis
from core.build import BuildRunner, BuildRunnerError
from core.config import CodiEnvironment
from core.detect import DetectionResult
from core.llm import (
    AssistCandidate,
    AssistContext,
    AssistDetection,
    ImageMetricsSnapshot,
    LLMRankingService,
    LocalLLMError,
)
from core.parse import DockerfileDocument, DockerfileParseError
from core.render import (
    RenderContext,
    RenderError,
    build_cmd_runtime_summary,
    extract_cmd_render_context,
    render_for_stack,
)
from core.report import ReportGenerationError, generate_report
from core.rules import AllowedStack
from core.security import SecurityPolicyError, enforce_airgap_guard, validate_or_raise
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

LOGGER = logging.getLogger("codi.api")


@dataclass
class AppConfig:
    """Runtime configuration for the FastAPI application."""

    env: CodiEnvironment
    default_candidate_limit: int = 2

    @classmethod
    def from_env(cls) -> AppConfig:
        env = CodiEnvironment.from_env()
        return cls(env=env)

    @property
    def output_root(self) -> Path:
        return self.env.output_root


def create_app(config: AppConfig | None = None) -> FastAPI:
    """Instantiate the FastAPI application with the provided configuration."""

    enforce_airgap_guard()
    app = FastAPI(
        title="CODI API",
        version="0.8.0",
        summary="Rules-first Dockerfile optimisation service for the CODI project.",
    )

    app.state.config = config or AppConfig.from_env()

    @app.middleware("http")
    async def _log_requests(request: Request, call_next):  # type: ignore[override]
        LOGGER.info("%s %s", request.method, request.url.path)
        response = await call_next(request)
        LOGGER.info("%s %s → %s", request.method, request.url.path, response.status_code)
        return response

    _register_routes(app)
    return app


def get_config(request: Request) -> AppConfig:
    return request.app.state.config  # type: ignore[attr-defined]


class ProjectRequest(BaseModel):
    """Common payload describing a project directory and optional overrides."""

    project_path: str = Field(
        ..., description="Absolute path to the project root containing a Dockerfile."
    )
    dockerfile_path: str | None = Field(
        default=None,
        description="Optional explicit Dockerfile path. Defaults to <project>/Dockerfile.",
    )
    stack_hint: AllowedStack | None = Field(
        default=None,
        description="Optional override for the detected stack (node|python|java).",
    )
    real_builds: bool = Field(
        default=False,
        description="Execute real container builds instead of dry-run metrics where supported.",
    )
    candidate_limit: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Maximum number of candidates to render for rewrite/run operations.",
    )


class DetectionModel(BaseModel):
    stack: str
    confidence: float
    evidence: dict[str, list[str]]


class AnalyzeSummary(BaseModel):
    stage_count: int
    bases: list[str]
    uses_pkg_manager: bool
    runs_as_root: bool
    has_cache_mount: bool
    exposed_ports: list[str]
    entrypoints: list[str]
    cmds: list[str]


class StageModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_image: str = Field(..., alias="from")
    name: str | None = None
    commands: list[str]
    workdirs: list[str]
    copied_sources: list[str]


class AnalyzeResponse(BaseModel):
    stack: str
    detection: DetectionModel
    summary: AnalyzeSummary
    stages: list[StageModel]
    cmd_analysis: dict[str, Any] | None = Field(default=None)


class RewriteCandidateModel(BaseModel):
    rule_id: str
    name: str | None
    description: str | None
    rationale: list[str]
    policy_notes: list[str]
    dockerfile: str


class RewriteResponse(BaseModel):
    stack: str
    candidates: list[RewriteCandidateModel]
    cmd_analysis: dict[str, Any] | None = None
    cmd_runtime: dict[str, Any] | None = None


class MetricsModel(BaseModel):
    size_bytes: int
    layers: int
    build_seconds: float
    mode: str


class RunVariantModel(BaseModel):
    kind: str
    dockerfile_path: str
    metrics: MetricsModel
    rule_id: str | None = None
    name: str | None = None
    description: str | None = None
    rationale: list[str] | None = None
    policy_notes: list[str] | None = None


class AssistRecommendationModel(BaseModel):
    rule_id: str
    reason: str
    confidence: float | None = None
    source: str | None = None


class AssistModel(BaseModel):
    summary: str
    recommendation: AssistRecommendationModel | None = None


class RunResponse(BaseModel):
    run_id: str
    stack: str
    mode: str
    run_dir: str
    detection: DetectionModel
    results: list[RunVariantModel]
    assist: AssistModel | None = None
    environment: dict[str, Any]
    cmd: dict[str, Any] | None = None


class ReportRequest(BaseModel):
    run_path: str | None = Field(
        default=None, description="Absolute path to an existing run directory."
    )
    run_id: str | None = Field(
        default=None,
        description="Identifier of a run located under the configured output directory.",
    )

    model_config = ConfigDict(extra="forbid")


class ReportResponse(BaseModel):
    run_id: str
    run_dir: str
    markdown_path: str
    html_path: str
    markdown: str
    html: str
    cmd: dict[str, Any] | None = None


class LLMRankRequest(BaseModel):
    """Request for LLM ranking of candidates."""

    project_path: str = Field(..., description="Absolute path to the project root.")
    dockerfile_path: str | None = Field(
        default=None, description="Optional explicit Dockerfile path."
    )
    stack_hint: AllowedStack | None = Field(default=None, description="Optional stack override.")
    candidate_limit: int | None = Field(
        default=None, ge=1, le=5, description="Max candidates to rank."
    )


class LLMRankedCandidateModel(BaseModel):
    """Ranked candidate with score."""

    candidate_id: str
    rule_id: str
    score: float
    rank: int


class LLMRankResponse(BaseModel):
    """Response for LLM ranking."""

    ranking: list[LLMRankedCandidateModel]
    rationale: str
    adapter_version: str
    llm_metrics: dict[str, Any]


class LLMExplainRequest(BaseModel):
    """Request for LLM explanation of analysis."""

    project_path: str = Field(..., description="Absolute path to the project root.")
    dockerfile_path: str | None = Field(
        default=None, description="Optional explicit Dockerfile path."
    )
    stack_hint: AllowedStack | None = Field(default=None, description="Optional stack override.")


class LLMExplainResponse(BaseModel):
    """Response for LLM explanation."""

    summary: str
    rationale: str
    adapter_version: str


def _register_routes(app: FastAPI) -> None:
    @app.post(
        "/analyze",
        response_model=AnalyzeResponse,
        summary="Inspect a project Dockerfile and return structured metadata.",
    )
    def analyze(
        payload: ProjectRequest, config: AppConfig = Depends(get_config)
    ) -> AnalyzeResponse:
        project_root, dockerfile_path = _resolve_paths(payload)
        try:
            analysis = perform_analysis(project_root, dockerfile_path=dockerfile_path)
            validate_or_raise(analysis.document)
        except DockerfileParseError as exc:  # pragma: no cover - consistent error translation
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SecurityPolicyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        detection = analysis.detection
        stack = payload.stack_hint or detection.stack
        summary = AnalyzeSummary(**analysis.summary)
        stages = [
            StageModel(
                from_image=stage.get("from"),
                name=stage.get("name"),
                commands=stage.get("commands", []),
                workdirs=stage.get("workdirs", []),
                copied_sources=stage.get("copied_sources", []),
            )
            for stage in analysis.stages
        ]

        analysis_payload = build_analysis_payload(analysis)
        cmd_analysis = analysis_payload.get("cmd_analysis")

        return AnalyzeResponse(
            stack=stack,
            detection=_detection_model(detection),
            summary=summary,
            stages=stages,
            cmd_analysis=cmd_analysis,
        )

    @app.post(
        "/rewrite",
        response_model=RewriteResponse,
        summary="Render deterministic Dockerfile candidates for the project.",
    )
    def rewrite(
        payload: ProjectRequest, config: AppConfig = Depends(get_config)
    ) -> RewriteResponse:
        project_root, dockerfile_path = _resolve_paths(payload)
        try:
            analysis = perform_analysis(project_root, dockerfile_path=dockerfile_path)
            validate_or_raise(analysis.document)
        except DockerfileParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SecurityPolicyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        detection = analysis.detection
        stack = _ensure_stack(payload.stack_hint or detection.stack)
        analysis_payload = build_analysis_payload(analysis)
        cmd_analysis = (
            analysis_payload.get("cmd_analysis") if isinstance(analysis_payload, dict) else None
        )

        context = _build_render_context(stack, analysis.document, project_root, analysis=analysis)
        limit = payload.candidate_limit or config.default_candidate_limit

        try:
            candidates = render_for_stack(context, limit=limit)
        except RenderError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        cmd_runtime = build_cmd_runtime_summary(context)

        items = [
            RewriteCandidateModel(
                rule_id=candidate.rule_id,
                name=candidate.name,
                description=candidate.description,
                rationale=list(candidate.rationale),
                policy_notes=list(candidate.policy_notes),
                dockerfile=candidate.content,
            )
            for candidate in candidates
        ]

        return RewriteResponse(
            stack=stack, candidates=items, cmd_analysis=cmd_analysis, cmd_runtime=cmd_runtime
        )

    @app.post(
        "/run",
        response_model=RunResponse,
        summary="Execute the full CODI pipeline (render + metrics + persistence).",
    )
    def run(payload: ProjectRequest, config: AppConfig = Depends(get_config)) -> RunResponse:
        project_root, _ = _resolve_paths(payload)

        runner = BuildRunner(
            project_root,
            config.output_root,
            real_builds=payload.real_builds,
            candidate_limit=payload.candidate_limit or config.default_candidate_limit,
            environment=config.env,
        )

        try:
            result = runner.run()
        except (BuildRunnerError, SecurityPolicyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        detection_model = DetectionModel(
            stack=result.detection.stack,
            confidence=result.detection.confidence,
            evidence=result.detection.evidence,
        )

        variants: list[RunVariantModel] = [
            RunVariantModel(
                kind="original",
                dockerfile_path=result.original.dockerfile_path,
                metrics=MetricsModel(
                    size_bytes=result.original.metrics.size_bytes,
                    layers=result.original.metrics.layers,
                    build_seconds=result.original.metrics.build_seconds,
                    mode=result.original.metrics.mode,
                ),
            )
        ]

        for index, candidate in enumerate(result.candidates, start=1):
            variants.append(
                RunVariantModel(
                    kind=f"candidate_{index}",
                    rule_id=candidate.rule_id,
                    name=candidate.name,
                    description=candidate.description,
                    rationale=list(candidate.rationale),
                    policy_notes=list(candidate.policy_notes),
                    dockerfile_path=candidate.dockerfile_path,
                    metrics=MetricsModel(
                        size_bytes=candidate.metrics.size_bytes,
                        layers=candidate.metrics.layers,
                        build_seconds=candidate.metrics.build_seconds,
                        mode=candidate.metrics.mode,
                    ),
                )
            )

        assist_model: AssistModel | None = None
        if result.assist:
            recommendation_model: AssistRecommendationModel | None = None
            if result.assist.recommendation:
                recommendation_model = AssistRecommendationModel(
                    rule_id=result.assist.recommendation.rule_id,
                    reason=result.assist.recommendation.reason,
                    confidence=result.assist.recommendation.confidence,
                    source=result.assist.recommendation.source,
                )
            assist_model = AssistModel(
                summary=result.assist.summary, recommendation=recommendation_model
            )

        cmd_payload = result.cmd.to_dict() if result.cmd else None

        return RunResponse(
            run_id=result.run_id,
            stack=result.stack,
            mode=result.mode,
            run_dir=str(result.run_dir),
            detection=detection_model,
            results=variants,
            assist=assist_model,
            environment=result.environment.to_metadata(),
            cmd=cmd_payload,
        )

    @app.post(
        "/report",
        response_model=ReportResponse,
        summary="Generate Markdown and HTML reports for an existing run directory.",
    )
    def report(payload: ReportRequest, config: AppConfig = Depends(get_config)) -> ReportResponse:
        run_dir = _resolve_run_dir(payload, config)

        try:
            artefacts = generate_report(run_dir)
        except ReportGenerationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        markdown = artefacts.markdown_path.read_text(encoding="utf-8")
        html = artefacts.html_path.read_text(encoding="utf-8")
        cmd_payload = None
        run_summary_path = run_dir / "metadata" / "run.json"
        if run_summary_path.exists():
            try:
                run_payload = json.loads(run_summary_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                run_payload = {}
            cmd_section = run_payload.get("cmd")
            if isinstance(cmd_section, dict):
                cmd_payload = cmd_section
            else:
                analysis_section = run_payload.get("analysis")
                if isinstance(analysis_section, dict):
                    fallback = analysis_section.get("cmd_analysis")
                    if isinstance(fallback, dict):
                        cmd_payload = {"analysis": fallback}

        return ReportResponse(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            markdown_path=str(artefacts.markdown_path),
            html_path=str(artefacts.html_path),
            markdown=markdown,
            html=html,
            cmd=cmd_payload,
        )

    @app.post(
        "/llm/rank",
        response_model=LLMRankResponse,
        summary="Rank optimization candidates using LLM assistance.",
    )
    def llm_rank(
        payload: LLMRankRequest, config: AppConfig = Depends(get_config)
    ) -> LLMRankResponse:
        """Rank Dockerfile optimization candidates using local LLM assistance.

        Returns ordered candidates with confidence scores and rationale.
        """
        if not config.env.llm.enabled:
            raise HTTPException(
                status_code=503,
                detail="LLM ranking is disabled. Set LLM_ENABLED=true to enable.",
            )

        project_root, dockerfile_path = _resolve_paths_from_llm_request(payload)

        try:
            analysis = perform_analysis(project_root, dockerfile_path=dockerfile_path)
            validate_or_raise(analysis.document)
        except DockerfileParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SecurityPolicyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        detection = analysis.detection
        stack = _ensure_stack(payload.stack_hint or detection.stack)

        # Build render context to get candidates
        context_for_render = _build_render_context(
            stack, analysis.document, project_root, analysis=analysis
        )
        limit = payload.candidate_limit or config.default_candidate_limit

        try:
            candidates = render_for_stack(context_for_render, limit=limit)
        except RenderError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # Build assist context for ranking
        assist_context = _build_assist_context(
            project_root=project_root,
            detection=detection,
            analysis=analysis,
            candidates=candidates,
        )

        # Create ranking service and rank candidates
        ranking_service = LLMRankingService.from_settings(config.env)

        try:
            result = ranking_service.rank_candidates(assist_context)
        except LocalLLMError as exc:
            raise HTTPException(status_code=503, detail=f"LLM ranking failed: {exc}") from exc

        return LLMRankResponse(
            ranking=[
                LLMRankedCandidateModel(
                    candidate_id=rc.candidate_id,
                    rule_id=rc.rule_id,
                    score=rc.score,
                    rank=rc.rank,
                )
                for rc in result.ranking
            ],
            rationale=result.rationale,
            adapter_version=result.adapter_version,
            llm_metrics=result.llm_metrics,
        )

    @app.post(
        "/llm/explain",
        response_model=LLMExplainResponse,
        summary="Generate explanation for Dockerfile analysis using LLM.",
    )
    def llm_explain(
        payload: LLMExplainRequest, config: AppConfig = Depends(get_config)
    ) -> LLMExplainResponse:
        """Generate human-friendly explanation of Dockerfile analysis and optimization opportunities.

        Returns summary and rationale referencing detected issues and recommendations.
        """
        if not config.env.llm.enabled:
            raise HTTPException(
                status_code=503,
                detail="LLM explanation is disabled. Set LLM_ENABLED=true to enable.",
            )

        project_root, dockerfile_path = _resolve_paths_from_llm_request(payload)

        try:
            analysis = perform_analysis(project_root, dockerfile_path=dockerfile_path)
            validate_or_raise(analysis.document)
        except DockerfileParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SecurityPolicyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        detection = analysis.detection
        stack = _ensure_stack(payload.stack_hint or detection.stack)

        # Build render context to get candidates
        context_for_render = _build_render_context(
            stack, analysis.document, project_root, analysis=analysis
        )

        try:
            candidates = render_for_stack(context_for_render, limit=config.default_candidate_limit)
        except RenderError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # Build assist context
        assist_context = _build_assist_context(
            project_root=project_root,
            detection=detection,
            analysis=analysis,
            candidates=candidates,
        )

        # Create ranking service and generate explanation
        ranking_service = LLMRankingService.from_settings(config.env)

        try:
            result = ranking_service.explain_analysis(assist_context)
        except LocalLLMError as exc:
            raise HTTPException(status_code=503, detail=f"LLM explanation failed: {exc}") from exc

        return LLMExplainResponse(
            summary=result.summary,
            rationale=result.rationale,
            adapter_version=result.adapter_version,
        )


def _resolve_paths(payload: ProjectRequest) -> tuple[Path, Path]:
    project_root = Path(payload.project_path).expanduser().resolve()
    if not project_root.exists() or not project_root.is_dir():
        raise HTTPException(status_code=404, detail=f"Project directory not found: {project_root}")

    dockerfile_path = (
        Path(payload.dockerfile_path).expanduser().resolve()
        if payload.dockerfile_path
        else _locate_dockerfile(project_root)
    )

    if not dockerfile_path.exists() or not dockerfile_path.is_file():
        raise HTTPException(status_code=404, detail=f"Dockerfile not found at: {dockerfile_path}")

    return project_root, dockerfile_path


def _locate_dockerfile(project_root: Path) -> Path:
    default_path = project_root / "Dockerfile"
    if default_path.exists():
        return default_path
    for candidate in ("docker/Dockerfile", "Dockerfile.dev", "Dockerfile.release"):
        path = project_root / candidate
        if path.exists():
            return path
    raise HTTPException(
        status_code=404, detail="Unable to locate a Dockerfile in the project directory."
    )


def _detection_model(result: DetectionResult) -> DetectionModel:
    return DetectionModel(
        stack=result.stack, confidence=result.confidence, evidence=result.evidence
    )


def _ensure_stack(stack: str) -> AllowedStack:
    allowed: Sequence[str] = ("node", "python", "java")
    if stack not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported stack: {stack}. Expected one of {', '.join(allowed)}",
        )
    return stack  # type: ignore[return-value]


def _build_render_context(
    stack: AllowedStack,
    document: DockerfileDocument,
    project_root: Path,
    *,
    analysis: Any,
) -> RenderContext:
    context = RenderContext(stack=stack)
    for path in _collect_files(project_root):
        context.add_file(path)
    for path in _collect_lockfiles(project_root):
        context.add_lockfile(path)
    for feature in _collect_features(stack, project_root):
        context.add_feature(feature)
    context.variables.update(
        {"project_name": project_root.name, "stage_count": len(document.stages)}
    )

    cmd_context = extract_cmd_render_context(getattr(analysis, "cmd", None))
    if cmd_context:
        context.cmd = cmd_context
        context.variables.setdefault(
            "cmd_flags",
            {key: bool(value) for key, value in cmd_context.flags.items()},
        )

    return context


def _collect_files(root: Path) -> Iterable[str]:
    wanted = ["package.json", "requirements.txt", "pyproject.toml", "pom.xml", "Dockerfile"]
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
                import json

                data = json.loads(package_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            dependencies: dict[str, Any] = {}
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


def _resolve_run_dir(payload: ReportRequest, config: AppConfig) -> Path:
    if payload.run_path:
        run_dir = Path(payload.run_path).expanduser().resolve()
    elif payload.run_id:
        run_dir = (config.output_root / payload.run_id).expanduser().resolve()
    else:
        raise HTTPException(status_code=400, detail="Provide either run_path or run_id.")

    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Run directory not found: {run_dir}")

    return run_dir


def _resolve_paths_from_llm_request(
    payload: LLMRankRequest | LLMExplainRequest,
) -> tuple[Path, Path]:
    """Resolve paths from LLM request payload."""
    project_root = Path(payload.project_path).expanduser().resolve()
    if not project_root.exists() or not project_root.is_dir():
        raise HTTPException(status_code=404, detail=f"Project directory not found: {project_root}")

    dockerfile_path = (
        Path(payload.dockerfile_path).expanduser().resolve()
        if payload.dockerfile_path
        else _locate_dockerfile(project_root)
    )

    if not dockerfile_path.exists() or not dockerfile_path.is_file():
        raise HTTPException(status_code=404, detail=f"Dockerfile not found at: {dockerfile_path}")

    return project_root, dockerfile_path


def _build_assist_context(
    *,
    project_root: Path,
    detection: Any,
    analysis: Any,
    candidates: Sequence[Any],
) -> AssistContext:
    """Build AssistContext from analysis and candidates."""
    from core.build import heuristic_metrics

    # Create original metrics snapshot (using heuristics since we don't have real build)
    original_metrics_dict = heuristic_metrics(
        stage_count=len(analysis.document.stages),
        features=[],
    )
    original = ImageMetricsSnapshot(
        size_bytes=original_metrics_dict["size_bytes"],
        layers=original_metrics_dict["layers"],
        build_seconds=original_metrics_dict["build_seconds"],
    )

    # Convert candidates to AssistCandidate
    assist_candidates: list[AssistCandidate] = []
    for candidate in candidates:
        # Use heuristic metrics for candidates
        candidate_metrics_dict = heuristic_metrics(
            stage_count=2,  # Most optimized candidates have 2 stages
            features=[],
        )
        metrics = ImageMetricsSnapshot(
            size_bytes=candidate_metrics_dict["size_bytes"],
            layers=candidate_metrics_dict["layers"],
            build_seconds=candidate_metrics_dict["build_seconds"],
        )

        assist_candidates.append(
            AssistCandidate(
                rule_id=candidate.rule_id,
                name=candidate.name,
                description=candidate.description,
                rationale=list(candidate.rationale),
                policy_notes=list(candidate.policy_notes),
                metrics=metrics,
            )
        )

    # Build detection snapshot
    assist_detection = AssistDetection(
        stack=detection.stack,
        confidence=detection.confidence,
        evidence=detection.evidence,
    )

    # Collect features, files, lockfiles
    features = list(_collect_features(detection.stack, project_root))
    files = list(_collect_files(project_root))
    lockfiles = list(_collect_lockfiles(project_root))

    return AssistContext(
        project_name=project_root.name,
        detection=assist_detection,
        features=features,
        files=files,
        lockfiles=lockfiles,
        original=original,
        candidates=assist_candidates,
        rag_matches=(),
    )


# Export a module-level app instance for ASGI servers.
app = create_app()

__all__ = [
    "AppConfig",
    "app",
    "create_app",
]
