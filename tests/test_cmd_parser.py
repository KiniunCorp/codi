from __future__ import annotations

from pathlib import Path

from core.cmd_parser import extract_cmd_analysis
from core.parse import parse_dockerfile
from core.script_analyzer import apply_script_heuristics


def test_extract_cmd_analysis_exec_form(tmp_path: Path) -> None:
    document = parse_dockerfile("""
        FROM python:3.12-slim
        CMD ["uvicorn", "app:app"]
        """.strip())

    result = extract_cmd_analysis(document)

    assert result is not None
    assert result.dominant is not None
    assert result.dominant.form == "exec"
    assert result.dominant.parsed["argv"] == ["uvicorn", "app:app"]
    assert result.dominant.flags["uses_shell_form"] is False


def test_extract_cmd_analysis_shell_script_flags(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("""
        FROM node:20-alpine
        WORKDIR /app
        CMD ./start.sh
        """.strip())

    script = tmp_path / "start.sh"
    script.write_text("#!/bin/sh\napt-get install -y curl\n")

    document = parse_dockerfile(dockerfile)
    result = extract_cmd_analysis(document, context_dir=tmp_path)
    result = apply_script_heuristics(result, context_dir=tmp_path)

    assert result is not None and result.dominant is not None
    cmd = result.dominant
    assert cmd.form == "shell"
    assert any(script_ref.path == "./start.sh" and script_ref.exists for script_ref in cmd.scripts)
    assert cmd.flags["uses_shell_form"] is True
    assert cmd.flags["installs_packages"] is True
    assert cmd.flags["references_script"] is True


def test_missing_script_emits_warning(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("""
        FROM python:3.12-slim
        CMD ./missing.sh
        """.strip())

    document = parse_dockerfile(dockerfile)
    result = extract_cmd_analysis(document, context_dir=tmp_path)

    assert result is not None and result.dominant is not None
    cmd = result.dominant
    assert cmd.flags["missing_script"] is True
    assert cmd.warnings
