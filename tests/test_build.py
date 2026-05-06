from __future__ import annotations

import json
from pathlib import Path

import pytest
from core.build import BuildRunner


def _write_node_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Dockerfile").write_text("""
FROM node:20-slim
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
CMD ["npm", "start"]
""".strip())
    (root / "package.json").write_text(
        json.dumps({"name": "demo", "version": "0.1.0", "dependencies": {"next": "13.4.0"}})
    )
    (root / "package-lock.json").write_text("{}")


def test_build_runner_produces_run_directory(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_node_project(project_root)
    output_root = tmp_path / "runs"

    runner = BuildRunner(project_root, output_root, candidate_limit=1)
    result = runner.run()

    assert result.run_dir.exists()
    assert result.timings.analysis_seconds >= 0
    assert result.timings.total_seconds >= result.timings.analysis_seconds
    run_metadata = json.loads((result.run_dir / "metadata" / "run.json").read_text())
    assert run_metadata["stack"] == "node"
    assert run_metadata["original"]["metrics"]["layers"] > 0
    assert run_metadata["candidates"], "Expected at least one candidate to be rendered"
    assert "rag" in run_metadata
    llm_block = run_metadata.get("llm")
    assert llm_block and llm_block["ranking"] is not None
    llm_metrics_path = result.run_dir / "metadata" / "llm_metrics.json"
    assert llm_metrics_path.exists()
    llm_metrics = json.loads(llm_metrics_path.read_text())
    assert llm_metrics["ranking"] == llm_block["ranking"]
    assert llm_metrics["metrics"]["mode"] in {"llm", "heuristic", "empty"}

    assist = run_metadata.get("assist")
    assert assist and assist["summary"], "Expected assist summary to be recorded"
    env_metadata = run_metadata.get("environment")
    assert env_metadata, "Environment metadata should be recorded"
    env_file = json.loads((result.run_dir / "metadata" / "environment.json").read_text())
    assert env_file == env_metadata
    assert env_metadata["output_root"] == str(output_root.resolve())

    rag_data = json.loads((result.run_dir / "metadata" / "rag.json").read_text())
    assert rag_data["matches"] == []
    metrics = run_metadata["metrics"]
    assert metrics["analysis_seconds"] >= 0
    assert metrics["total_seconds"] >= metrics["analysis_seconds"]

    candidate_path = Path(run_metadata["candidates"][0]["dockerfile_path"])
    candidate_content = candidate_path.read_text()
    assert candidate_content.lstrip().startswith("# LLM RANK:")


def test_build_runner_second_run_gets_rag_match(tmp_path: Path) -> None:
    output_root = tmp_path / "runs"

    first_project = tmp_path / "project1"
    _write_node_project(first_project)
    first_run = BuildRunner(first_project, output_root, candidate_limit=1).run()
    first_rag = json.loads((first_run.run_dir / "metadata" / "rag.json").read_text())
    assert first_rag["matches"] == []

    second_project = tmp_path / "project2"
    _write_node_project(second_project)
    second_run = BuildRunner(second_project, output_root, candidate_limit=1).run()
    second_rag = json.loads((second_run.run_dir / "metadata" / "rag.json").read_text())

    assert second_rag["matches"], "Expected the second run to retrieve at least one match"
    assert second_rag["matches"][0]["run_id"] == first_run.run_id
    second_summary = json.loads((second_run.run_dir / "metadata" / "run.json").read_text())
    assert second_summary["assist"][
        "summary"
    ], "Assist summary should be present on subsequent runs"


def test_environment_snapshot_reflects_env_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("AIRGAP", "false")
    monkeypatch.setenv("AIRGAP_ALLOWLIST", "internal.example.com")

    project_root = tmp_path / "project"
    _write_node_project(project_root)
    output_root = tmp_path / "runs"

    runner = BuildRunner(project_root, output_root, candidate_limit=1)
    result = runner.run()

    env_payload = json.loads((result.run_dir / "metadata" / "environment.json").read_text())
    assert env_payload["llm"]["enabled"] is False
    assert env_payload["airgap"]["enabled"] is False
    assert env_payload["airgap"]["allowlist"] == ["internal.example.com"]
