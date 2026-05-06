"""CPU performance sanity suite utilities."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .build import BuildRunner, BuildRunResult
from .config import CodiEnvironment

__all__ = [
    "CPUPerfReport",
    "CPUPerfResult",
    "CPUPerfThresholds",
    "run_cpu_sanity_suite",
    "write_cpu_perf_report",
]


@dataclass(slots=True)
class CPUPerfThresholds:
    """Budget thresholds for CPU-only performance sanity checks."""

    analysis_seconds: float = 3.0
    total_seconds: float = 300.0  # 5 minutes

    def to_dict(self) -> dict[str, float]:
        return {
            "analysis_seconds": self.analysis_seconds,
            "total_seconds": self.total_seconds,
        }


@dataclass(slots=True)
class CPUPerfResult:
    """Outcome of running the CODI pipeline against a demo project."""

    stack: str
    project: str
    run_id: str
    run_dir: Path
    analysis_seconds: float
    render_seconds: float
    total_seconds: float
    original_build_seconds: float
    status: str
    message: str | None = None

    def to_dict(self) -> dict[str, str | float]:
        payload: dict[str, str | float] = {
            "stack": self.stack,
            "project": self.project,
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "analysis_seconds": self.analysis_seconds,
            "render_seconds": self.render_seconds,
            "total_seconds": self.total_seconds,
            "original_build_seconds": self.original_build_seconds,
            "status": self.status,
        }
        if self.message:
            payload["message"] = self.message
        return payload


@dataclass(slots=True)
class CPUPerfReport:
    """Aggregated performance results for a CPU-only sanity run."""

    generated_at: str
    output_root: Path
    thresholds: CPUPerfThresholds
    results: Sequence[CPUPerfResult] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return all(result.status == "passed" for result in self.results)

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "output_root": str(self.output_root),
            "thresholds": self.thresholds.to_dict(),
            "passed": self.passed,
            "results": [result.to_dict() for result in self.results],
        }


def _evaluate_thresholds(
    result: BuildRunResult, thresholds: CPUPerfThresholds
) -> tuple[str, str | None]:
    analysis = result.timings.analysis_seconds
    total = result.timings.total_seconds

    if analysis > thresholds.analysis_seconds:
        return (
            "failed",
            f"analysis window exceeded: {analysis:.2f}s > {thresholds.analysis_seconds:.2f}s",
        )

    if total > thresholds.total_seconds:
        return (
            "failed",
            f"total runtime exceeded: {total:.2f}s > {thresholds.total_seconds:.2f}s",
        )

    return ("passed", None)


def _normalize_project_name(path: Path) -> str:
    return path.name


def run_cpu_sanity_suite(
    project_roots: Sequence[Path],
    output_root: Path,
    *,
    thresholds: CPUPerfThresholds | None = None,
    environment: CodiEnvironment | None = None,
) -> CPUPerfReport:
    """Execute the CPU-only sanity workflow across the requested projects.

    Parameters
    ----------
    project_roots:
        A sequence of project roots containing Dockerfiles to exercise.
    output_root:
        The directory where run artefacts are collected.
    thresholds:
        Optional performance budgets. Defaults to the built-in acceptance criteria.
    environment:
        Optional baseline environment snapshot to reuse between runs.
    """

    if not project_roots:
        raise ValueError("At least one project root must be provided for performance runs.")

    thresholds = thresholds or CPUPerfThresholds()
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    base_environment = environment or CodiEnvironment.from_env()

    results: list[CPUPerfResult] = []
    for project_root in project_roots:
        project_root = project_root.expanduser().resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Project root does not exist: {project_root}")

        runner = BuildRunner(project_root, output_root, environment=base_environment)
        run_result = runner.run()
        status, message = _evaluate_thresholds(run_result, thresholds)

        original_metrics = run_result.original.metrics
        results.append(
            CPUPerfResult(
                stack=run_result.stack,
                project=_normalize_project_name(project_root),
                run_id=run_result.run_id,
                run_dir=run_result.run_dir,
                analysis_seconds=run_result.timings.analysis_seconds,
                render_seconds=run_result.timings.render_seconds,
                total_seconds=run_result.timings.total_seconds,
                original_build_seconds=original_metrics.build_seconds,
                status=status,
                message=message,
            )
        )

    generated_at = datetime.now(UTC).isoformat()
    return CPUPerfReport(
        generated_at=generated_at,
        output_root=output_root,
        thresholds=thresholds,
        results=tuple(results),
    )


def write_cpu_perf_report(report: CPUPerfReport, path: Path) -> Path:
    """Persist a performance report to a JSON file."""

    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
