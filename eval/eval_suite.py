from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from eval.build_and_measure import evaluate_projects, render_html_report, write_samples_csv

DEFAULT_PROJECTS = [
    Path("demo/node"),
    Path("demo/python"),
    Path("demo/java"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CODI LLM evaluation harness.")
    parser.add_argument(
        "--project",
        action="append",
        help="Path to a project to evaluate (defaults to demo stacks). Can be specified multiple times.",
    )
    parser.add_argument(
        "--output",
        default="eval",
        help="Directory for evaluation outputs (metrics/, reports/, runs/).",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=2,
        help="Maximum number of candidates to render per project.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    project_paths = _resolve_projects(args.project, repo_root)
    output_root = Path(args.output).expanduser().resolve()
    metrics_dir = output_root / "metrics"
    reports_dir = output_root / "reports"
    for directory in (metrics_dir, reports_dir):
        directory.mkdir(parents=True, exist_ok=True)

    results = evaluate_projects(
        project_paths, output_root=output_root, candidate_limit=args.candidate_limit
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    metrics_json = metrics_dir / f"llm_eval_{timestamp}.json"
    metrics_csv = metrics_dir / f"llm_eval_{timestamp}.csv"
    report_html = reports_dir / "llm_eval.html"

    metrics_json.write_text(json.dumps(results.to_dict(), indent=2), encoding="utf-8")
    write_samples_csv(results.samples, metrics_csv)
    report_html.write_text(render_html_report(results), encoding="utf-8")

    print(f"[eval-llm] Metrics JSON: {metrics_json}")
    print(f"[eval-llm] Metrics CSV: {metrics_csv}")
    print(f"[eval-llm] Report HTML: {report_html}")


def _resolve_projects(project_args: Iterable[str] | None, repo_root: Path) -> list[Path]:
    if project_args:
        paths = [Path(arg).expanduser().resolve() for arg in project_args]
    else:
        paths = [(repo_root / default).resolve() for default in DEFAULT_PROJECTS]

    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Project paths not found: {', '.join(missing)}")
    return paths


if __name__ == "__main__":
    main()
