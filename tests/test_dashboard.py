from __future__ import annotations

import json
from pathlib import Path

from core.dashboard import collect_dashboard_data, load_dashboard_run


def _write_run_summary(run_dir: Path, *, stack: str, run_id: str) -> None:
    metadata_dir = run_dir / "metadata"
    reports_dir = run_dir / "reports"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "run_id": run_id,
        "stack": stack,
        "mode": "dry_run",
        "project_root": "demo/project",
        "created_at": run_id.split("-")[0],
        "original": {
            "dockerfile_path": "inputs/Dockerfile",
            "metrics": {
                "size_bytes": 320 * 1024 * 1024,
                "layers": 18,
                "build_seconds": 64.0,
            },
        },
        "candidates": [
            {
                "rule_id": "rule.alpine-runtime",
                "name": "Alpine runtime",
                "description": "Switch runtime stage to Alpine base.",
                "dockerfile_path": "candidates/001-rule.alpine-runtime.Dockerfile",
                "metrics": {
                    "size_bytes": 210 * 1024 * 1024,
                    "layers": 14,
                    "build_seconds": 52.0,
                },
                "rationale": [
                    "Swap to alpine runtime",
                ],
                "policy_notes": [],
            }
        ],
        "assist": {
            "summary": "Recommend alpine runtime to reduce image footprint.",
            "recommendation": {
                "rule_id": "rule.alpine-runtime",
                "reason": "High impact on size",
                "confidence": 0.82,
                "source": "rag",
            },
        },
        "environment": {
            "airgap": {"enabled": True, "allowlist": []},
            "llm": {"enabled": True, "endpoint": "http://127.0.0.1:8081"},
        },
    }

    (metadata_dir / "run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (reports_dir / "report.md").write_text("# Sample report", encoding="utf-8")
    (reports_dir / "report.html").write_text("<html></html>", encoding="utf-8")


def test_load_dashboard_run(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "20250101T120000Z-node-demo"
    _write_run_summary(run_root, stack="node", run_id="20250101T120000Z-node-demo")

    summary = load_dashboard_run(run_root)

    assert summary.run_id == "20250101T120000Z-node-demo"
    assert summary.stack == "node"
    assert summary.project_name == "project"
    assert summary.original_layers == 18
    assert summary.best_candidate is not None
    assert summary.best_candidate.rule_id == "rule.alpine-runtime"
    assert summary.best_candidate.size_delta_mb < 0
    assert summary.assist_summary is not None
    assert summary.airgap_enabled is True
    assert summary.llm_enabled is True
    assert summary.report_markdown is not None
    assert summary.report_html is not None


def test_collect_dashboard_data(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    first_run = runs_root / "20250101T120000Z-node-demo"
    second_run = runs_root / "20250101T120500Z-python-demo"

    _write_run_summary(first_run, stack="node", run_id="20250101T120000Z-node-demo")
    _write_run_summary(second_run, stack="python", run_id="20250101T120500Z-python-demo")

    data = collect_dashboard_data(runs_root)

    assert data["run_count"] == 2
    runs = {item["run_id"]: item for item in data["runs"]}
    assert "20250101T120000Z-node-demo" in runs
    assert runs["20250101T120000Z-node-demo"]["best_candidate"]["rule_id"] == "rule.alpine-runtime"

    stacks = {item["stack"]: item for item in data["stacks"]}
    assert stacks["node"]["run_count"] == 1
    assert stacks["node"]["best_run_id"] == "20250101T120000Z-node-demo"


def test_collect_dashboard_data_with_relative_paths(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    first_run = runs_root / "20250101T120000Z-node-demo"
    _write_run_summary(first_run, stack="node", run_id="20250101T120000Z-node-demo")

    data = collect_dashboard_data(runs_root, relative_to=runs_root)

    run_entry = data["runs"][0]
    assert run_entry["paths"]["run_dir"] == "20250101T120000Z-node-demo"
    assert run_entry["paths"]["report_markdown"].endswith("reports/report.md")
