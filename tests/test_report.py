from __future__ import annotations

from pathlib import Path

from core.build import BuildRunner
from core.report import generate_report


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
        '{"name": "demo", "version": "0.1.0", "dependencies": {"next": "13.4.0"}}'
    )
    (root / "package-lock.json").write_text("{}")


def test_generate_report_produces_markdown_and_html(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_node_project(project)
    runs_dir = tmp_path / "runs"

    runner = BuildRunner(project, runs_dir, candidate_limit=1)
    result = runner.run()

    artefacts = generate_report(result.run_dir)

    assert artefacts.markdown_path.exists()
    assert artefacts.html_path.exists()

    markdown_content = artefacts.markdown_path.read_text()
    html_content = artefacts.html_path.read_text()

    assert "CODI Optimisation Report" in markdown_content
    assert "```diff" in markdown_content
    assert "CMD/ENTRYPOINT Analysis" in markdown_content
    assert "LLM Assist" in markdown_content
    assert "LLM Rationale & Ranking" in markdown_content
    assert "Environment Configuration" in markdown_content
    assert "<!DOCTYPE html>" in html_content
    assert "LLM Assist" in html_content
    assert "LLM Rationale & Ranking" in html_content
    assert "Environment Configuration" in html_content
    assert "CMD/ENTRYPOINT Analysis" in html_content
