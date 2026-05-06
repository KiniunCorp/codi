"""End-to-end smoke tests exercising the demo applications."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core.build import BuildRunner
from core.report import generate_report

DEMO_ROOT = Path(__file__).resolve().parent.parent / "demo"


@pytest.mark.parametrize(
    ("stack", "relative_path"),
    [
        ("node", "node"),
        ("python", "python"),
        ("java", "java"),
    ],
)
def test_wave10_smoke_runs_pipeline(tmp_path: Path, stack: str, relative_path: str) -> None:
    project_dir = DEMO_ROOT / relative_path
    output_root = tmp_path / "runs"

    runner = BuildRunner(project_dir, output_root)
    result = runner.run()

    assert result.stack == stack
    assert result.candidates, "Expected at least one candidate Dockerfile"

    original_metrics = result.original.metrics
    best_candidate = min(result.candidates, key=lambda candidate: candidate.metrics.size_bytes)

    assert best_candidate.metrics.size_bytes <= int(original_metrics.size_bytes * 0.7)
    assert best_candidate.metrics.layers < original_metrics.layers
    assert best_candidate.metrics.build_seconds < original_metrics.build_seconds

    artefacts = generate_report(result.run_dir)
    assert artefacts.markdown_path.exists()
    assert artefacts.html_path.exists()

    summary_path = result.run_dir / "metadata" / "run.json"
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert data["run_id"] == result.run_id
    assert data["original"]["metrics"]["size_bytes"] == original_metrics.size_bytes

    candidate_sizes = [candidate["metrics"]["size_bytes"] for candidate in data["candidates"]]
    assert candidate_sizes, "Run summary missing candidate metrics"
    assert min(candidate_sizes) <= int(original_metrics.size_bytes * 0.7)

    for candidate in result.candidates:
        assert candidate.rationale, "Candidate should include rationale entries"
        assert candidate.policy_notes, "Candidate should include policy notes"
