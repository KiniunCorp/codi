from __future__ import annotations

import shutil
from pathlib import Path

from core.perf import CPUPerfThresholds, run_cpu_sanity_suite


def _copy_demo(stack: str, destination_root: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "demo" / stack
    target = destination_root / stack
    shutil.copytree(source, target)
    return target


def test_cpu_perf_suite_covers_three_stacks(tmp_path: Path) -> None:
    projects = [_copy_demo(stack, tmp_path / "projects") for stack in ("node", "python", "java")]
    output_root = tmp_path / "runs"
    thresholds = CPUPerfThresholds(analysis_seconds=5.0, total_seconds=180.0)

    report = run_cpu_sanity_suite(projects, output_root, thresholds=thresholds)

    assert report.passed is True
    assert len(report.results) == 3
    for result in report.results:
        assert result.status == "passed"
        assert result.analysis_seconds <= thresholds.analysis_seconds
        assert result.total_seconds <= thresholds.total_seconds
        assert result.run_dir.exists()
