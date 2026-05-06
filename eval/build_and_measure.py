from __future__ import annotations

import json
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.build import BuildRunner

MB = 1024 * 1024


@dataclass(slots=True)
class EvaluationSample:
    project: str
    stack: str
    run_id: str
    run_dir: Path
    llm_rule: str
    best_rule: str
    llm_rank: int
    mode: str
    confidence: float | None
    llm_win: bool
    llm_size_delta_mb: float
    best_size_delta_mb: float
    llm_layers_delta: float
    best_layers_delta: float
    llm_build_delta_s: float
    best_build_delta_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "stack": self.stack,
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "llm_rule": self.llm_rule,
            "best_rule": self.best_rule,
            "llm_rank": self.llm_rank,
            "mode": self.mode,
            "confidence": self.confidence,
            "llm_win": self.llm_win,
            "llm_size_delta_mb": round(self.llm_size_delta_mb, 3),
            "best_size_delta_mb": round(self.best_size_delta_mb, 3),
            "llm_layers_delta": self.llm_layers_delta,
            "best_layers_delta": self.best_layers_delta,
            "llm_build_delta_s": round(self.llm_build_delta_s, 3),
            "best_build_delta_s": round(self.best_build_delta_s, 3),
        }


@dataclass(slots=True)
class EvaluationResults:
    generated_at: str
    samples: Sequence[EvaluationSample]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "summary": self.summary,
            "samples": [sample.to_dict() for sample in self.samples],
        }


def evaluate_projects(
    projects: Sequence[Path],
    *,
    output_root: Path,
    candidate_limit: int = 2,
) -> EvaluationResults:
    runs_root = output_root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    samples: list[EvaluationSample] = []
    for project in projects:
        project_path = project.expanduser().resolve()
        runner = BuildRunner(project_path, runs_root, candidate_limit=candidate_limit)
        result = runner.run()
        summary = _load_run_summary(result.run_dir)
        sample = _build_sample(project_path.name, result.run_dir, summary)
        samples.append(sample)

    summary_stats = summarise_samples(samples)
    generated_at = datetime.now(UTC).isoformat()
    return EvaluationResults(generated_at=generated_at, samples=samples, summary=summary_stats)


def summarise_samples(samples: Sequence[EvaluationSample]) -> dict[str, Any]:
    total = len(samples)
    wins = sum(1 for sample in samples if sample.llm_win)
    win_rate = wins / total if total else 0.0

    mean_confidence = _safe_mean(
        sample.confidence for sample in samples if sample.confidence is not None
    )
    avg_llm_delta = _safe_mean(sample.llm_size_delta_mb for sample in samples)
    avg_best_delta = _safe_mean(sample.best_size_delta_mb for sample in samples)

    histogram = _confidence_histogram(samples)
    mode_counts: dict[str, int] = {}
    for sample in samples:
        mode_counts[sample.mode] = mode_counts.get(sample.mode, 0) + 1

    return {
        "total_runs": total,
        "llm_wins": wins,
        "win_rate": round(win_rate, 4),
        "mean_confidence": round(mean_confidence, 4) if mean_confidence is not None else None,
        "avg_llm_size_delta_mb": round(avg_llm_delta, 3) if avg_llm_delta is not None else None,
        "avg_best_size_delta_mb": round(avg_best_delta, 3) if avg_best_delta is not None else None,
        "mode_counts": mode_counts,
        "confidence_histogram": histogram,
    }


def render_html_report(results: EvaluationResults) -> str:
    summary = results.summary
    lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "  <meta charset='utf-8' />",
        "  <title>CODI LLM Evaluation</title>",
        "  <style>body{font-family:Arial,Helvetica,sans-serif;background:#0f172a;color:#e2e8f0;padding:2rem;}table{border-collapse:collapse;width:100%;margin-bottom:1.5rem;}th,td{border:1px solid #334155;padding:0.4rem;}th{background:#1e293b;}code{background:#1e293b;padding:0.15rem 0.35rem;border-radius:4px;}</style>",
        "</head>",
        "<body>",
        "  <h1>CODI LLM Evaluation</h1>",
        f"  <p>Generated at {results.generated_at}</p>",
        "  <h2>Summary</h2>",
        "  <ul>",
        f"    <li>Total runs: {summary.get('total_runs', 0)}</li>",
        f"    <li>LLM wins: {summary.get('llm_wins', 0)} ({summary.get('win_rate', 0)*100:.1f}%)</li>",
    ]

    mean_conf = summary.get("mean_confidence")
    if mean_conf is not None:
        lines.append(f"    <li>Mean confidence: {mean_conf:.2f}</li>")
    avg_llm = summary.get("avg_llm_size_delta_mb")
    avg_best = summary.get("avg_best_size_delta_mb")
    if avg_llm is not None and avg_best is not None:
        lines.append(
            f"    <li>Average size delta (LLM vs best): {avg_llm:.2f} MB vs {avg_best:.2f} MB</li>"
        )

    lines.append("  </ul>")

    histogram = summary.get("confidence_histogram") or {}
    if histogram:
        lines.append("  <h3>Confidence histogram</h3>")
        lines.append("  <ul>")
        for label, count in histogram.items():
            lines.append(f"    <li>{label}: {count}</li>")
        lines.append("  </ul>")

    lines.append("  <h2>Per-project results</h2>")
    lines.append("  <table>")
    lines.append(
        "    <thead><tr><th>Project</th><th>Stack</th><th>LLM rule</th><th>Best rule</th>"
        "<th>Rank</th><th>Confidence</th><th>Mode</th><th>LLM win?</th><th>LLM size Δ (MB)</th>"
        "<th>Best size Δ (MB)</th></tr></thead>"
    )
    lines.append("    <tbody>")
    for sample in results.samples:
        conf = f"{sample.confidence:.2f}" if isinstance(sample.confidence, float) else "—"
        lines.append(
            "      <tr>"
            f"<td>{sample.project}</td>"
            f"<td>{sample.stack}</td>"
            f"<td><code>{sample.llm_rule}</code></td>"
            f"<td><code>{sample.best_rule}</code></td>"
            f"<td>{sample.llm_rank}</td>"
            f"<td>{conf}</td>"
            f"<td>{sample.mode}</td>"
            f"<td>{'yes' if sample.llm_win else 'no'}</td>"
            f"<td>{sample.llm_size_delta_mb:.2f}</td>"
            f"<td>{sample.best_size_delta_mb:.2f}</td>"
            "</tr>"
        )
    lines.append("    </tbody>")
    lines.append("  </table>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


def write_samples_csv(samples: Sequence[EvaluationSample], path: Path) -> None:
    headers = [
        "project",
        "stack",
        "run_id",
        "llm_rule",
        "best_rule",
        "llm_rank",
        "mode",
        "confidence",
        "llm_win",
        "llm_size_delta_mb",
        "best_size_delta_mb",
        "llm_layers_delta",
        "best_layers_delta",
        "llm_build_delta_s",
        "best_build_delta_s",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(",".join(headers) + "\n")
        for sample in samples:
            row = [
                sample.project,
                sample.stack,
                sample.run_id,
                sample.llm_rule,
                sample.best_rule,
                str(sample.llm_rank),
                sample.mode,
                f"{sample.confidence:.4f}" if isinstance(sample.confidence, float) else "",
                "1" if sample.llm_win else "0",
                f"{sample.llm_size_delta_mb:.4f}",
                f"{sample.best_size_delta_mb:.4f}",
                f"{sample.llm_layers_delta:.0f}",
                f"{sample.best_layers_delta:.0f}",
                f"{sample.llm_build_delta_s:.4f}",
                f"{sample.best_build_delta_s:.4f}",
            ]
            handle.write(",".join(row) + "\n")


def _build_sample(project_name: str, run_dir: Path, summary: dict[str, Any]) -> EvaluationSample:
    original_metrics = summary["original"]["metrics"]
    candidates = summary.get("candidates") or []
    if not candidates:
        raise RuntimeError("Evaluation requires at least one candidate")

    llm_payload = summary.get("llm") or {}
    ranking = llm_payload.get("ranking") or []
    ranking_entry = ranking[0] if ranking else {}
    llm_candidate = _candidate_from_summary(candidates, ranking_entry.get("candidate_id"))
    if llm_candidate is None:
        llm_candidate = candidates[0]

    best_candidate = _select_best_candidate(candidates, original_metrics)

    llm_metrics = llm_candidate["metrics"]
    best_metrics = best_candidate["metrics"]

    return EvaluationSample(
        project=project_name,
        stack=summary.get("stack", "unknown"),
        run_id=summary.get("run_id", run_dir.name),
        run_dir=run_dir,
        llm_rule=llm_candidate.get("rule_id", "unknown"),
        best_rule=best_candidate.get("rule_id", "unknown"),
        llm_rank=int(ranking_entry.get("rank", 1) or 1),
        mode=(llm_payload.get("metrics") or {}).get("mode", "unknown"),
        confidence=_safe_float(ranking_entry.get("score")),
        llm_win=llm_candidate.get("rule_id") == best_candidate.get("rule_id"),
        llm_size_delta_mb=_size_delta_mb(original_metrics, llm_metrics),
        best_size_delta_mb=_size_delta_mb(original_metrics, best_metrics),
        llm_layers_delta=original_metrics["layers"] - llm_metrics["layers"],
        best_layers_delta=original_metrics["layers"] - best_metrics["layers"],
        llm_build_delta_s=original_metrics["build_seconds"] - llm_metrics["build_seconds"],
        best_build_delta_s=original_metrics["build_seconds"] - best_metrics["build_seconds"],
    )


def _load_run_summary(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "metadata" / "run.json"
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _size_delta_mb(original_metrics: dict[str, Any], candidate_metrics: dict[str, Any]) -> float:
    delta = original_metrics["size_bytes"] - candidate_metrics["size_bytes"]
    return delta / MB


def _candidate_from_summary(
    candidates: Sequence[dict[str, Any]], candidate_id: Any
) -> dict[str, Any] | None:
    if not isinstance(candidate_id, str):
        return None
    if not candidate_id.startswith("candidate_"):
        return None
    try:
        index = int(candidate_id.split("_", 1)[1]) - 1
    except (ValueError, IndexError):
        return None
    if 0 <= index < len(candidates):
        return candidates[index]
    return None


def _select_best_candidate(
    candidates: Sequence[dict[str, Any]],
    original_metrics: dict[str, Any],
) -> dict[str, Any]:
    def _score(candidate: dict[str, Any]) -> tuple[float, float, float]:
        metrics = candidate["metrics"]
        delta_size = original_metrics["size_bytes"] - metrics["size_bytes"]
        delta_layers = original_metrics["layers"] - metrics["layers"]
        delta_seconds = original_metrics["build_seconds"] - metrics["build_seconds"]
        return delta_size, delta_layers, delta_seconds

    best = candidates[0]
    best_score = _score(best)
    for candidate in candidates[1:]:
        score = _score(candidate)
        if score > best_score:
            best = candidate
            best_score = score
    return best


def _safe_mean(values: Iterable[float]) -> float | None:
    values = list(values)
    if not values:
        return None
    return statistics.mean(values)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _confidence_histogram(samples: Sequence[EvaluationSample]) -> dict[str, int]:
    bins = ["0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]
    counts = {label: 0 for label in bins}
    for sample in samples:
        value = sample.confidence
        if value is None:
            continue
        if value < 0.2:
            counts["0-0.2"] += 1
        elif value < 0.4:
            counts["0.2-0.4"] += 1
        elif value < 0.6:
            counts["0.4-0.6"] += 1
        elif value < 0.8:
            counts["0.6-0.8"] += 1
        else:
            counts["0.8-1.0"] += 1
    return counts
