from __future__ import annotations

from pathlib import Path

import pytest
from core.parse import DockerfileParseError, parse_dockerfile


def test_parse_single_stage_dockerfile(tmp_path: Path) -> None:
    content = """
    FROM python:3.12-slim
    ARG APP_HOME=/app
    ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
    WORKDIR ${APP_HOME}
    COPY requirements.txt ./
    RUN pip install --no-cache-dir -r requirements.txt
    COPY . .
    CMD ["python", "main.py"]
    """.strip()

    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(content)

    document = parse_dockerfile(dockerfile)

    assert document.args == {"APP_HOME": "/app"}
    assert document.env == {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
    assert len(document.stages) == 1

    stage = document.stages[0]
    assert stage.base_image == "python:3.12-slim"
    assert stage.name is None
    assert "WORKDIR ${APP_HOME}" in [instr.original for instr in stage.instructions]
    assert stage.workdirs == ["${APP_HOME}"]
    assert stage.cmds == ['["python", "main.py"]']


def test_parse_multi_stage_dockerfile_handles_copy_from() -> None:
    content = """
    ARG PYTHON_VERSION=3.12
    FROM python:${PYTHON_VERSION}-slim AS builder
    WORKDIR /workspace
    COPY pyproject.toml ./
    RUN pip install --no-cache-dir build \
        && python -m build

    FROM python:${PYTHON_VERSION}-slim
    COPY --from=builder /workspace/dist/*.whl /tmp/app.whl
    RUN pip install /tmp/app.whl
    ENTRYPOINT ["app"]
    """.strip()

    document = parse_dockerfile(content)

    assert document.args == {"PYTHON_VERSION": "3.12"}
    assert len(document.stages) == 2

    builder, runtime = document.stages
    assert builder.name == "builder"
    assert "pip install --no-cache-dir build && python -m build" in [
        instr.arguments for instr in builder.instructions
    ]
    assert runtime.copied_sources == ["builder"]
    assert runtime.entrypoints == ['["app"]']


def test_parse_requires_stage() -> None:
    with pytest.raises(DockerfileParseError):
        parse_dockerfile("RUN echo 'missing FROM'")
