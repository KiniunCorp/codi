from __future__ import annotations

from pathlib import Path

from eval.build_and_measure import (
    EvaluationResults,
    EvaluationSample,
    render_html_report,
    summarise_samples,
    write_samples_csv,
)


def _make_sample(
    project: str, confidence: float | None, llm_win: bool, mode: str
) -> EvaluationSample:
    return EvaluationSample(
        project=project,
        stack="node",
        run_id=f"{project}-run",
        run_dir=Path(f"/tmp/{project}"),
        llm_rule="rule_a",
        best_rule="rule_b",
        llm_rank=1,
        mode=mode,
        confidence=confidence,
        llm_win=llm_win,
        llm_size_delta_mb=12.5,
        best_size_delta_mb=14.0,
        llm_layers_delta=1,
        best_layers_delta=2,
        llm_build_delta_s=0.5,
        best_build_delta_s=1.2,
    )


def test_summary_statistics_and_histogram() -> None:
    samples = [
        _make_sample("proj1", confidence=0.15, llm_win=True, mode="llm"),
        _make_sample("proj2", confidence=0.45, llm_win=False, mode="heuristic"),
    ]
    summary = summarise_samples(samples)
    assert summary["llm_wins"] == 1
    assert summary["total_runs"] == 2
    assert summary["mode_counts"]["llm"] == 1
    assert summary["mode_counts"]["heuristic"] == 1
    histogram = summary["confidence_histogram"]
    assert histogram["0-0.2"] == 1
    assert histogram["0.4-0.6"] == 1


def test_render_html_report_contains_projects(tmp_path) -> None:
    samples = [_make_sample("proj-html", confidence=0.9, llm_win=True, mode="llm")]
    summary = summarise_samples(samples)
    results = EvaluationResults(generated_at="now", samples=samples, summary=summary)
    html = render_html_report(results)
    assert "proj-html" in html
    assert "LLM Evaluation" in html

    csv_path = tmp_path / "samples.csv"
    write_samples_csv(samples, csv_path)
    content = csv_path.read_text()
    assert "proj-html" in content
