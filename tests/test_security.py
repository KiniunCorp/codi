from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from core.build import BuildRunner, BuildRunnerError
from core.parse import parse_dockerfile
from core.security import (
    AirgapViolation,
    SecurityPolicyError,
    disable_airgap_guard,
    enforce_airgap_guard,
    ensure_instruction_allowlist,
    ensure_model_mount_path,
    ensure_outbound_url_allowed,
    evaluate_policy,
    get_model_mount_path,
    scrub_docker_tokens,
    validate_or_raise,
)


def test_reject_add_from_url_and_privileged_and_sudo() -> None:
    document = parse_dockerfile("""
        FROM python:3.12-slim
        RUN apt-get update && sudo apt-get install -y curl
        ADD https://example.com/file.tar.gz /tmp/
        RUN echo hello --privileged
        """.strip())

    violations = evaluate_policy(document)
    messages = [v.message for v in violations]
    assert any("ADD" in m for m in messages)
    assert any("--privileged" in m for m in messages)
    assert any("sudo" in m for m in messages)

    with pytest.raises(SecurityPolicyError):
        validate_or_raise(document)


def test_reject_disallowed_base_images() -> None:
    document = parse_dockerfile("""
        FROM ubuntu:22.04
        RUN echo ok
        """.strip())

    with pytest.raises(SecurityPolicyError):
        validate_or_raise(document)


def test_allow_listed_bases_and_non_root() -> None:
    document = parse_dockerfile("""
        FROM node:20-slim as builder
        RUN npm ci && npm run build
        FROM node:20-alpine
        USER node
        CMD ["node", "server.js"]
        """.strip())

    # Should not raise
    validate_or_raise(document)


def test_airgap_guard_blocks_remote_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRGAP", "true")
    disable_airgap_guard()
    enforce_airgap_guard()

    with pytest.raises(AirgapViolation):
        httpx.get("https://example.com")

    disable_airgap_guard()


def test_airgap_guard_blocks_async_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRGAP", "true")
    disable_airgap_guard()
    enforce_airgap_guard()

    async def _request() -> None:
        async with httpx.AsyncClient() as client:
            await client.get("https://example.com")

    with pytest.raises(AirgapViolation):
        asyncio.run(_request())

    disable_airgap_guard()


def test_airgap_allowlist_and_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRGAP", "true")
    monkeypatch.setenv("AIRGAP_ALLOWLIST", "internal.example.com,*.corp.local")

    ensure_outbound_url_allowed("https://internal.example.com/api")
    ensure_outbound_url_allowed("http://service.corp.local/status")
    ensure_outbound_url_allowed("http://127.0.0.1:8080")

    with pytest.raises(AirgapViolation):
        ensure_outbound_url_allowed("https://public.example.net")


def test_model_mount_path_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_MOUNT_PATH", raising=False)
    monkeypatch.delenv("CODI_MODEL_PATH", raising=False)

    default_path = get_model_mount_path()
    assert str(default_path) == "/models"

    custom_path = tmp_path / "weights"
    monkeypatch.setenv("MODEL_MOUNT_PATH", str(custom_path))
    resolved = get_model_mount_path()
    assert resolved == custom_path.resolve()

    created = ensure_model_mount_path(create=True)
    assert created.exists()


def test_build_runner_rejects_disallowed_project(tmp_path: Path) -> None:
    project_root = tmp_path / "app"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "Dockerfile").write_text("""
        FROM ubuntu:22.04
        RUN echo unsafe
        """.strip())

    output_root = tmp_path / "runs"

    runner = BuildRunner(project_root, output_root)
    with pytest.raises(BuildRunnerError) as excinfo:
        runner.run()

    assert "Disallowed base image" in str(excinfo.value)


def test_instruction_allowlist_enforces_known_tokens() -> None:
    ensure_instruction_allowlist(
        ["RUN npm ci --prefer-offline --no-audit", "ENV NODE_ENV=production"]
    )

    with pytest.raises(ValueError):
        ensure_instruction_allowlist(["INSTALL curl"])


def test_scrub_docker_tokens_removes_keywords() -> None:
    raw = "Ranking says FROM base but RUN npm install should be avoided."
    cleaned = scrub_docker_tokens(raw)
    assert "FROM" not in cleaned.upper()
    assert "RUN" not in cleaned.upper()
