"""Unit tests for the lightweight local LLM server integration."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.llm import (
    AssistCandidate,
    AssistContext,
    AssistDetection,
    ImageMetricsSnapshot,
    LLMAssist,
    LocalLLMClient,
    LocalLLMConfig,
    LocalLLMServer,
    RAGMatchReference,
    read_adapter_metadata,
)


def test_llm_server_health_and_completion() -> None:
    config = LocalLLMConfig(port=0)
    with LocalLLMServer(config) as server:
        health = server.health_check()
        assert health["status"] == "ok"
        assert health["model_id"] == config.model_id

        client = LocalLLMClient(server.base_url)
        prompt = "Summarise Docker policy improvements for a Next.js service."
        response = client.complete(prompt)

        assert "Key prompt:" in response
        assert "deterministic templates" in response.lower()
        assert "next" in response.lower()


@pytest.mark.parametrize("payload", ["", "\n  \n"])
def test_llm_server_handles_empty_prompt(payload: str) -> None:
    config = LocalLLMConfig(port=0)
    with LocalLLMServer(config) as server:
        client = LocalLLMClient(server.base_url)
        response = client.complete(payload)
        assert "no prompt" in response.lower()


def _assist_context() -> AssistContext:
    detection = AssistDetection(
        stack="node", confidence=0.92, evidence={"files": ["Dockerfile", "package.json"]}
    )
    original = ImageMetricsSnapshot(size_bytes=520 * 1024 * 1024, layers=12, build_seconds=118.0)
    candidate_metrics = ImageMetricsSnapshot(
        size_bytes=180 * 1024 * 1024, layers=8, build_seconds=58.5
    )
    candidate = AssistCandidate(
        rule_id="node_nextjs_alpine_runtime",
        name="Next.js multi-stage",
        description="",
        rationale=("Multi-stage build reduces runtime footprint.",),
        policy_notes=("Pinned base images.",),
        metrics=candidate_metrics,
    )
    rag_match = RAGMatchReference(
        run_id="20251030T120000Z-node",
        score=0.83,
        label="demo",
        candidate_rules=("node_nextjs_alpine_runtime",),
    )
    return AssistContext(
        project_name="demo-next",
        detection=detection,
        features=("nextjs",),
        files=("Dockerfile", "package.json"),
        lockfiles=("package-lock.json",),
        original=original,
        candidates=(candidate,),
        rag_matches=(rag_match,),
    )


def test_llm_assist_summary_and_recommendation_fallback() -> None:
    context = _assist_context()
    assist = LLMAssist(client=None)

    summary = assist.summarise(context)
    assert summary
    assert "node" in summary.lower()
    assert "template" in summary.lower()
    assert "FROM" not in summary.upper()

    recommendation = assist.recommend_template(context)
    assert recommendation is not None
    assert recommendation.rule_id == "node_nextjs_alpine_runtime"
    assert recommendation.source == "heuristic"
    assert "FROM" not in recommendation.reason.upper()


def test_llm_assist_uses_local_server_when_available() -> None:
    context = _assist_context()
    config = LocalLLMConfig(port=0)
    with LocalLLMServer(config) as server:
        client = LocalLLMClient(server.base_url)
        assist = LLMAssist(client=client)

        summary = assist.summarise(context)
        assert summary
        assert "deterministic" in summary.lower() or "policy" in summary.lower()

        recommendation = assist.recommend_template(context)
        assert recommendation is not None
        assert recommendation.rule_id == "node_nextjs_alpine_runtime"
        assert recommendation.source in {"llm", "heuristic"}
        assert "FROM" not in recommendation.reason.upper()


# ----------------------------------------------------------------------
# Adapter configuration and loading tests
# ----------------------------------------------------------------------


def test_llm_config_with_adapter_parameters() -> None:
    """Test that LocalLLMConfig accepts and stores adapter parameters."""
    adapter_path = Path("models/adapters/qwen15b-lora-v0.1")
    config = LocalLLMConfig(
        host="127.0.0.1",
        port=8081,
        code_model="qwen2.5-coder-1.5b",
        adapter_path=adapter_path,
        adapter_version="v0.1.0-dev",
    )

    assert config.code_model == "qwen2.5-coder-1.5b"
    assert config.adapter_path == adapter_path
    assert config.adapter_version == "v0.1.0-dev"


def test_read_adapter_metadata_with_valid_directory() -> None:
    """Test reading adapter metadata from the stub adapter directory."""
    adapter_path = Path("models/adapters/qwen15b-lora-v0.1")

    if not adapter_path.exists():
        pytest.skip(f"Adapter directory not found: {adapter_path}")

    metadata = read_adapter_metadata(adapter_path)

    assert metadata["status"] == "loaded"
    assert "version" in metadata
    assert "model" in metadata


def test_read_adapter_metadata_missing_directory() -> None:
    """Test handling of missing adapter directory."""
    adapter_path = Path("models/adapters/nonexistent")
    metadata = read_adapter_metadata(adapter_path)

    assert metadata["status"] == "not_mounted"
    assert metadata["version"] == "unknown"


def test_read_adapter_metadata_missing_metadata_file() -> None:
    """Test handling of adapter directory without metadata.json."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        adapter_path = Path(tmpdir)
        metadata = read_adapter_metadata(adapter_path)

        assert metadata["status"] == "no_metadata"
        assert metadata["version"] == "unknown"


def test_llm_server_logs_adapter_info_on_startup() -> None:
    """Test that adapter information is logged when server starts."""
    adapter_path = Path("models/adapters/qwen15b-lora-v0.1")
    config = LocalLLMConfig(
        port=0,
        code_model="qwen2.5-coder-1.5b",
        adapter_path=adapter_path if adapter_path.exists() else None,
        adapter_version="v0.1.0-dev",
    )

    # Server should start successfully even without actual adapter weights
    with LocalLLMServer(config) as server:
        assert server.is_running
        health = server.health_check()
        assert health["status"] == "ok"


def test_llm_server_works_without_adapter() -> None:
    """Test that LLM server works when no adapter is configured."""
    config = LocalLLMConfig(
        port=0,
        code_model="qwen2.5-coder-1.5b",
        adapter_path=None,
        adapter_version="none",
    )

    with LocalLLMServer(config) as server:
        assert server.is_running
        client = LocalLLMClient(server.base_url)
        response = client.complete("Test prompt")
        assert response
        assert "Key prompt:" in response
