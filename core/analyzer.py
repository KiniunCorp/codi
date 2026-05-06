"""High-level utilities for Dockerfile analysis workflows.

This module centralises logic shared by the CLI and API `analyze` operations as
well as the build runner metadata writers. It stitches together signals from
the tolerant Dockerfile parser, stack detector, and CMD/ENTRYPOINT analyzers and
produces deterministic, JSON-serialisable payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .cmd_parser import CmdAnalysisResult, extract_cmd_analysis, serialize_cmd_analysis
from .detect import DetectionResult, detect_stack
from .parse import DockerfileDocument, DockerInstruction, DockerStage, parse_dockerfile
from .script_analyzer import apply_script_heuristics

__all__ = [
    "AnalysisResult",
    "build_analysis_payload",
    "perform_analysis",
]


@dataclass(slots=True)
class AnalysisResult:
    """Structured representation of Dockerfile analysis artefacts."""

    document: DockerfileDocument
    detection: DetectionResult
    cmd: CmdAnalysisResult | None
    summary: dict[str, Any]
    stages: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return build_analysis_payload(self)


def perform_analysis(
    project_root: Path,
    dockerfile_path: Path | None = None,
    *,
    document: DockerfileDocument | None = None,
) -> AnalysisResult:
    """Parse, detect, and analyse a project Dockerfile."""

    dockerfile = dockerfile_path or project_root / "Dockerfile"
    doc = document or parse_dockerfile(dockerfile)
    detection = detect_stack(doc, context_dir=project_root)
    cmd_result = extract_cmd_analysis(doc, context_dir=project_root)
    cmd_result = apply_script_heuristics(cmd_result, context_dir=project_root)

    summary = _build_summary(doc)
    stages = [_stage_snapshot(stage, index) for index, stage in enumerate(doc.stages)]

    return AnalysisResult(
        document=doc,
        detection=detection,
        cmd=cmd_result,
        summary=summary,
        stages=stages,
    )


def build_analysis_payload(result: AnalysisResult) -> dict[str, Any]:
    """Convert an :class:`AnalysisResult` into JSON-friendly metadata."""

    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "detection": {
            "stack": result.detection.stack,
            "confidence": result.detection.confidence,
            "evidence": result.detection.evidence,
        },
        "summary": result.summary,
        "stages": result.stages,
    }

    cmd_payload = serialize_cmd_analysis(result.cmd)
    if cmd_payload:
        payload["cmd_analysis"] = cmd_payload

    return payload


def _build_summary(document: DockerfileDocument) -> dict[str, Any]:
    exposed_ports = sorted({port for stage in document.stages for port in stage.exposes})
    entrypoints = _collect_instruction_values(document, "ENTRYPOINT")
    cmds = _collect_instruction_values(document, "CMD")

    return {
        "stage_count": len(document.stages),
        "bases": [stage.base_image for stage in document.stages],
        "uses_pkg_manager": _uses_pkg_manager(document),
        "runs_as_root": _runs_as_root(document),
        "has_cache_mount": _has_cache_mount(document),
        "exposed_ports": exposed_ports,
        "entrypoints": entrypoints,
        "cmds": cmds,
    }


def _stage_snapshot(stage: DockerStage, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "from": stage.base_image,
        "name": stage.name,
        "commands": [instruction.original for instruction in stage.instructions],
        "workdirs": list(stage.workdirs),
        "copied_sources": list(stage.copied_sources),
    }


def _collect_instruction_values(document: DockerfileDocument, keyword: str) -> list[str]:
    keyword_upper = keyword.upper()
    values: list[str] = []
    for instruction in _iterate_instructions(document):
        if instruction.keyword == keyword_upper:
            values.append(instruction.arguments)
    return values


def _iterate_instructions(document: DockerfileDocument):
    for stage in document.stages:
        yield from stage.instructions


def _uses_pkg_manager(document: DockerfileDocument) -> bool:
    keywords = ("npm ", "yarn ", "pnpm ", "pip ", "poetry ", "mvn ", "gradle")
    return any(
        _instruction_contains(instruction, keywords)
        for instruction in _iterate_instructions(document)
    )


def _runs_as_root(document: DockerfileDocument) -> bool:
    users: list[str] = []
    for instruction in _iterate_instructions(document):
        if instruction.keyword == "USER":
            users.append(instruction.arguments.strip().strip("\"'"))
    if not users:
        return True
    return users[-1] in {"root", "0"}


def _has_cache_mount(document: DockerfileDocument) -> bool:
    return any(
        "--mount=type=cache" in instruction.original
        for instruction in _iterate_instructions(document)
    )


def _instruction_contains(instruction: DockerInstruction, phrases: tuple[str, ...]) -> bool:
    text = f"{instruction.keyword} {instruction.arguments}".lower()
    return any(phrase in text for phrase in phrases)
