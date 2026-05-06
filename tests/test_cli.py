from __future__ import annotations

import json
from pathlib import Path

import pytest
from cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_cli_help_lists_core_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("analyze", "rewrite", "run", "report", "all"):
        assert command in result.stdout


@pytest.mark.parametrize("command", ["rewrite"])
def test_stubbed_commands_still_acknowledge_future_work(tmp_path: Path, command: str) -> None:
    out_dir = tmp_path / "artifacts"
    args = [f"--out={out_dir}"]
    args.extend([command, "."])

    result = runner.invoke(app, args, catch_exceptions=False)

    assert result.exit_code == 0
    assert "scaffolded" in result.stdout
    assert out_dir.exists()


def test_analyze_command_generates_metadata(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_node_project(project)
    out_dir = tmp_path / "analysis"

    result = runner.invoke(
        app, [f"--out={out_dir}", "analyze", str(project)], catch_exceptions=False
    )

    assert result.exit_code == 0
    assert "Analysis completed successfully" in result.stdout

    run_dirs = list(out_dir.iterdir())
    assert run_dirs, "Expected analysis artefacts to be created"
    analysis_dir = run_dirs[0]
    analysis_path = analysis_dir / "metadata" / "analysis.json"
    assert analysis_path.exists()

    payload = json.loads(analysis_path.read_text())
    assert payload["detection"]["stack"] == "node"
    assert payload["summary"]["stage_count"] == 1
    assert payload.get("cmd_analysis")
    assert payload["cmd_analysis"]["parsed"]["argv"][0] == "npm"


def _write_node_project(root: Path) -> None:
    (root / "Dockerfile").write_text("""
FROM node:20-slim
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
CMD [\"npm\", \"start\"]
""".strip())
    (root / "package.json").write_text(
        '{"name": "demo", "version": "0.1.0", "dependencies": {"next": "13.4.0"}}'
    )
    (root / "package-lock.json").write_text("{}")


def test_run_command_executes_pipeline(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_node_project(project)
    out_dir = tmp_path / "artifacts"

    result = runner.invoke(app, [f"--out={out_dir}", "run", str(project)], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Run completed" in result.stdout
    assert any(out_dir.iterdir())
    run_dirs = [path for path in out_dir.iterdir() if (path / "metadata" / "run.json").exists()]
    assert run_dirs, "Expected run metadata directory"
    run_dir = run_dirs[0]
    assert (run_dir / "metadata" / "cmd_analysis.json").exists()
    assert (run_dir / "metadata" / "cmd_runtime.json").exists()


def test_cli_uses_environment_output_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_node_project(project)
    env_out = tmp_path / "env-artifacts"

    result = runner.invoke(
        app,
        ["run", str(project)],
        catch_exceptions=False,
        env={"CODI_OUTPUT_ROOT": str(env_out)},
    )

    assert result.exit_code == 0
    assert env_out.exists()
    assert any(env_out.iterdir())


def test_report_command_generates_outputs(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_node_project(project)
    out_dir = tmp_path / "artifacts"

    run_result = runner.invoke(
        app, [f"--out={out_dir}", "run", str(project)], catch_exceptions=False
    )
    assert run_result.exit_code == 0

    run_dirs = list(out_dir.iterdir())
    assert run_dirs, "Expected run directory to be created"
    run_dir = next((p for p in run_dirs if (p / "metadata" / "run.json").exists()), None)
    assert run_dir is not None, "Expected at least one run directory with metadata"

    report_result = runner.invoke(
        app, [f"--out={out_dir}", "report", str(run_dir)], catch_exceptions=False
    )

    assert report_result.exit_code == 0
    assert "Report generated successfully" in report_result.stdout
    assert (run_dir / "reports" / "report.md").exists()
    assert (run_dir / "reports" / "report.html").exists()


def test_all_command_executes_pipeline(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_node_project(project)
    out_dir = tmp_path / "artifacts"

    result = runner.invoke(app, [f"--out={out_dir}", "all", str(project)], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Pipeline completed successfully" in result.stdout
    assert any(out_dir.iterdir())
