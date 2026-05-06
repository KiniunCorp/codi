from __future__ import annotations

import os
from pathlib import Path

from api.server import AppConfig, create_app
from core.config import CodiEnvironment
from fastapi.testclient import TestClient


def _write_node_project(root: Path) -> None:
    (root / "Dockerfile").write_text(
        (
            "FROM node:20-slim\n"
            "WORKDIR /app\n"
            "COPY package.json ./\n"
            "RUN npm install\n"
            "COPY . .\n"
            'CMD ["npm", "start"]\n'
        ).strip()
    )
    (root / "package.json").write_text(
        '{"name": "demo", "version": "0.1.0", "dependencies": {"next": "13.4.0"}}'
    )
    (root / "package-lock.json").write_text("{}")


def _make_client(tmp_path: Path) -> TestClient:
    os.environ.setdefault("AIRGAP_ALLOWLIST", "testserver")
    env = CodiEnvironment.from_env().with_output_root(tmp_path / "runs")
    config = AppConfig(env=env)
    app = create_app(config)
    return TestClient(app)


def test_analyze_endpoint_returns_stack_and_summary(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_node_project(project)

    with _make_client(tmp_path) as client:
        response = client.post("/analyze", json={"project_path": str(project)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["stack"] == "node"
    assert payload["summary"]["stage_count"] == 1
    assert payload["summary"]["uses_pkg_manager"] is True
    assert payload["stages"][0]["from"] == "node:20-slim"
    assert payload["cmd_analysis"]["parsed"]["argv"][0] == "npm"
    assert payload["cmd_analysis"]["flags"]["uses_shell_form"] is False


def test_rewrite_endpoint_returns_candidates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_node_project(project)

    with _make_client(tmp_path) as client:
        response = client.post("/rewrite", json={"project_path": str(project)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["stack"] == "node"
    assert payload["candidates"], "Expected at least one candidate"
    first = payload["candidates"][0]
    assert "dockerfile" in first and "FROM" in first["dockerfile"]
    assert payload["cmd_analysis"]
    assert payload["cmd_analysis"]["form"] == "exec"
    assert payload["cmd_runtime"]


def test_run_endpoint_creates_run_directory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_node_project(project)

    with _make_client(tmp_path) as client:
        response = client.post("/run", json={"project_path": str(project)})

    assert response.status_code == 200
    payload = response.json()
    run_dir = Path(payload["run_dir"])
    assert run_dir.exists()
    assert payload["results"], "Expected run variants to be returned"
    assert payload["results"][0]["kind"] == "original"
    assert payload["assist"]["summary"]
    assert payload["environment"]["output_root"] == str((tmp_path / "runs").resolve())
    assert payload["cmd"]
    assert payload["cmd"]["analysis"]["instruction"] == "CMD"


def test_report_endpoint_returns_markdown_and_html(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_node_project(project)

    with _make_client(tmp_path) as client:
        run_response = client.post("/run", json={"project_path": str(project)})
        assert run_response.status_code == 200
        run_payload = run_response.json()
        report_response = client.post("/report", json={"run_id": run_payload["run_id"]})

    assert report_response.status_code == 200
    payload = report_response.json()
    assert payload["markdown"].startswith("# CODI")
    assert payload["html"].startswith("<!DOCTYPE html>")
    assert payload["cmd"]
    assert payload["cmd"]["analysis"]["instruction"] == "CMD"
