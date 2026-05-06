"""Lightweight stack detector for CODI.

Heuristics-based identification of the primary technology stack for a given
project. Designed to be deterministic and simple: we aggregate evidence from
lockfiles, Dockerfile base images, and common tooling commands, then compute a
confidence score.

Stacks: "node" | "python" | "java" | "unknown".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cmd_parser import extract_cmd_analysis
from .parse import DockerfileDocument, parse_dockerfile

__all__ = ["DetectionResult", "detect_stack", "detect_stack_from_dir"]


SUPPORTED_STACKS = ("node", "python", "java")


@dataclass(slots=True)
class DetectionResult:
    stack: str
    confidence: float  # 0.0 .. 1.0
    evidence: dict[str, list[str]]  # category -> list of matched signals


def _score(evidence: dict[str, list[str]]) -> tuple[str, float]:
    weights = {"lockfiles": 0.5, "docker_base": 0.35, "commands": 0.15}
    totals = {"node": 0.0, "python": 0.0, "java": 0.0}

    for category, items in evidence.items():
        weight = weights.get(category, 0.0)
        for item in items:
            if item.startswith("node:"):
                totals["node"] += weight
            elif item.startswith("python:"):
                totals["python"] += weight
            elif item.startswith("java:"):
                totals["java"] += weight

    best_stack = max(totals.items(), key=lambda kv: kv[1])
    if best_stack[1] <= 0.0:
        return "unknown", 0.0
    # Cap to 1.0, typical ranges fall below 1.0 unless all categories agree
    return best_stack[0], min(1.0, best_stack[1])


def _evidence_from_dockerfile(document: DockerfileDocument) -> list[str]:
    signals: list[str] = []
    for stage in document.stages:
        base = stage.base_image.lower()
        if base.startswith("node:"):
            signals.append("node:base")
        if base.startswith("python:"):
            signals.append("python:base")
        if (
            base.startswith("maven:")
            or base.startswith("eclipse-temurin:")
            or base.startswith("adoptopenjdk:")
        ):
            signals.append("java:base")
        # Simple command hints
        for instr in stage.instructions:
            text = f"{instr.keyword} {instr.arguments}".lower()
            if "npm " in text or "yarn " in text or "pnpm " in text:
                signals.append("node:cmd")
            if "pip " in text or "uvicorn" in text or "python -m" in text:
                signals.append("python:cmd")
            if "mvn " in text or "gradle" in text or "java -jar" in text:
                signals.append("java:cmd")
    return signals


def _evidence_from_fs(root: Path) -> list[str]:
    signals: list[str] = []
    # Lockfiles / manifests
    if (
        (root / "package.json").exists()
        or (root / "yarn.lock").exists()
        or (root / "pnpm-lock.yaml").exists()
    ):
        signals.append("node:lock")
    if (
        (root / "requirements.txt").exists()
        or (root / "pyproject.toml").exists()
        or (root / "poetry.lock").exists()
    ):
        signals.append("python:lock")
    if (
        (root / "pom.xml").exists()
        or (root / "build.gradle").exists()
        or (root / "build.gradle.kts").exists()
    ):
        signals.append("java:lock")
    return signals


def detect_stack(
    dockerfile: str | Path | DockerfileDocument,
    context_dir: Path | None = None,
) -> DetectionResult:
    """Detect stack using Dockerfile + optional filesystem context.

    If ``dockerfile`` is a path or source text, it is parsed first.
    """

    document = (
        dockerfile if isinstance(dockerfile, DockerfileDocument) else parse_dockerfile(dockerfile)
    )

    evidence: dict[str, list[str]] = {"lockfiles": [], "docker_base": [], "commands": []}

    docker_signals = _evidence_from_dockerfile(document)
    for sig in docker_signals:
        if sig.endswith(":base"):
            evidence["docker_base"].append(sig)
        else:
            evidence["commands"].append(sig)

    cmd_analysis = (
        extract_cmd_analysis(document, context_dir=context_dir)
        if context_dir
        else extract_cmd_analysis(document)
    )
    if cmd_analysis and cmd_analysis.dominant is not None:
        normalized_tokens = _tokens_from_cmd(cmd_analysis.dominant.parsed)
        evidence["commands"].extend(_signals_from_tokens(normalized_tokens))
        if cmd_analysis.entrypoint and cmd_analysis.entrypoint is not cmd_analysis.dominant:
            entry_tokens = _tokens_from_cmd(cmd_analysis.entrypoint.parsed)
            evidence["commands"].extend(_signals_from_tokens(entry_tokens))

    if context_dir is not None:
        fs_signals = _evidence_from_fs(context_dir)
        evidence["lockfiles"].extend(fs_signals)

    # Normalize to the "stack:" prefix scheme used above
    normalized: dict[str, list[str]] = {k: [] for k in evidence}
    for category, items in evidence.items():
        for item in items:
            if item.startswith("node"):
                normalized[category].append("node:" + category)
            elif item.startswith("python"):
                normalized[category].append("python:" + category)
            elif item.startswith("java"):
                normalized[category].append("java:" + category)

    stack, confidence = _score(normalized)
    return DetectionResult(stack=stack, confidence=round(confidence, 2), evidence=normalized)


def detect_stack_from_dir(root: Path) -> DetectionResult:
    """Convenience helper: auto-locate a Dockerfile under ``root`` and detect.

    Prefers a file named exactly ``Dockerfile`` in ``root``.
    """

    dockerfile_path = root / "Dockerfile"
    if not dockerfile_path.exists():
        # Fallback: try common path names
        for candidate in ("docker/Dockerfile", "Dockerfile.dev", "Dockerfile.release"):
            path = root / candidate
            if path.exists():
                dockerfile_path = path
                break
    return detect_stack(dockerfile_path, context_dir=root)


def _tokens_from_cmd(parsed: dict[str, Any]) -> list[str]:
    argv = parsed.get("argv")
    if isinstance(argv, list):
        return [str(token).lower() for token in argv]
    command = parsed.get("command")
    if isinstance(command, str):
        return command.lower().split()
    return []


def _signals_from_tokens(tokens: list[str]) -> list[str]:
    signals: list[str] = []
    for token in tokens:
        if token in {"npm", "node"}:
            signals.append("node:cmd")
        elif token in {"pip", "uvicorn", "gunicorn", "python"}:
            signals.append("python:cmd")
        elif token in {"java", "mvn", "gradle"} or token.endswith(".jar"):
            signals.append("java:cmd")
    return signals
