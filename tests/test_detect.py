from __future__ import annotations

from pathlib import Path

from core.detect import DetectionResult, detect_stack
from core.parse import parse_dockerfile


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


def test_detect_from_lockfiles_and_base_images(tmp_path: Path) -> None:
    _write(tmp_path, "package.json", "{}")
    dockerfile = _write(
        tmp_path,
        "Dockerfile",
        """
        FROM node:20-slim AS builder
        RUN npm ci && npm run build
        FROM node:20-alpine
        CMD ["node", "server.js"]
        """.strip(),
    )

    result = detect_stack(dockerfile, context_dir=tmp_path)
    assert isinstance(result, DetectionResult)
    assert result.stack == "node"
    assert result.confidence >= 0.5
    assert "node:lockfiles" in result.evidence or "node:lock" in str(result.evidence)


def test_detect_python_heuristics(tmp_path: Path) -> None:
    _write(tmp_path, "requirements.txt", "fastapi==0.112.0\nuvicorn==0.30.0")
    document = parse_dockerfile("""
        FROM python:3.12-slim
        RUN pip install --no-cache-dir -r requirements.txt
        CMD ["uvicorn", "app:app"]
        """.strip())

    result = detect_stack(document, context_dir=tmp_path)
    assert result.stack == "python"
    assert result.confidence > 0


def test_detect_java_when_maven_used(tmp_path: Path) -> None:
    _write(tmp_path, "pom.xml", "<project></project>")
    document = parse_dockerfile("""
        FROM maven:3.9-eclipse-temurin-21 AS builder
        RUN mvn -q -DskipTests package
        FROM eclipse-temurin:21-jre
        CMD ["java", "-jar", "app.jar"]
        """.strip())

    result = detect_stack(document, context_dir=tmp_path)
    assert result.stack == "java"
    assert result.confidence >= 0.35


def test_detect_unknown_when_no_signals(tmp_path: Path) -> None:
    dockerfile = _write(tmp_path, "Dockerfile", "FROM scratch")
    result = detect_stack(dockerfile, context_dir=tmp_path)
    assert result.stack == "unknown"
    assert result.confidence == 0.0
