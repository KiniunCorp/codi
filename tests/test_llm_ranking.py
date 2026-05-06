"""Tests for LLM ranking and rationale service."""

from __future__ import annotations

import pytest
from core.llm import (
    AssistCandidate,
    AssistContext,
    AssistDetection,
    ImageMetricsSnapshot,
    LLMRankingService,
    LocalLLMClient,
    RankedCandidate,
)


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch) -> LocalLLMClient:
    """Create a mock LLM client that returns deterministic responses."""

    class MockClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        def complete(self, prompt: str, *, timeout: float = 5.0) -> str:
            if "rank" in prompt.lower():
                return """
                RANKING: 2,1
                RATIONALE: Candidate 2 (python_fastapi_wheels) offers better size reduction
                and uses exec-form CMD with proper signal handling.
                """
            elif "explain" in prompt.lower():
                return """
                This project can benefit from multi-stage builds and optimized base images.
                The FastAPI application will see significant size reduction through wheel-based installs.
                """
            return "Mock LLM response"

    monkeypatch.setattr("core.llm.LocalLLMClient", MockClient)
    return MockClient("http://localhost:8081")


@pytest.fixture
def sample_context() -> AssistContext:
    """Create a sample AssistContext for testing."""
    original = ImageMetricsSnapshot(
        size_bytes=500_000_000,
        layers=12,
        build_seconds=60.0,
    )

    candidate1 = AssistCandidate(
        rule_id="node_nextjs_alpine_runtime",
        name="Next.js alpine runtime",
        description="Multi-stage with alpine",
        rationale=["Reduced layers", "Smaller base image"],
        policy_notes=["Non-root user"],
        metrics=ImageMetricsSnapshot(
            size_bytes=180_000_000,
            layers=8,
            build_seconds=45.0,
        ),
    )

    candidate2 = AssistCandidate(
        rule_id="python_fastapi_wheels",
        name="FastAPI wheels",
        description="Wheel-based installs",
        rationale=["Cached wheels", "Exec-form CMD"],
        policy_notes=["Non-root user"],
        metrics=ImageMetricsSnapshot(
            size_bytes=150_000_000,
            layers=7,
            build_seconds=40.0,
        ),
    )

    detection = AssistDetection(
        stack="python",
        confidence=0.95,
        evidence={"files": ["requirements.txt"], "features": ["fastapi"]},
    )

    return AssistContext(
        project_name="test-project",
        detection=detection,
        features=["fastapi"],
        files=["requirements.txt"],
        lockfiles=["requirements.txt"],
        original=original,
        candidates=[candidate1, candidate2],
        rag_matches=(),
    )


def test_ranking_service_initialization():
    """Test LLMRankingService can be initialized."""
    service = LLMRankingService(enabled=False)
    assert service._enabled is False
    assert service._client is None


def test_ranking_with_llm_enabled(mock_client: LocalLLMClient, sample_context: AssistContext):
    """Test ranking candidates with LLM enabled."""
    service = LLMRankingService(
        client=mock_client,
        enabled=True,
        adapter_version="test-v1",
    )

    result = service.rank_candidates(sample_context)

    assert result is not None
    assert len(result.ranking) == 2
    assert result.adapter_version == "test-v1"
    assert (
        "python_fastapi_wheels" in result.rationale or "better size reduction" in result.rationale
    )
    assert result.llm_metrics["mode"] == "llm"

    # Check ranking order (should be 2,1 based on mock response)
    assert result.ranking[0].rank == 1
    assert result.ranking[1].rank == 2


def test_ranking_with_llm_disabled(sample_context: AssistContext):
    """Test fallback heuristic ranking when LLM is disabled."""
    service = LLMRankingService(enabled=False, adapter_version="test-v1")

    result = service.rank_candidates(sample_context)

    assert result is not None
    assert len(result.ranking) == 2
    assert result.adapter_version == "test-v1"
    assert "heuristic" in result.rationale.lower()
    assert result.llm_metrics["mode"] == "heuristic"

    # Check that candidates are ranked
    for ranked in result.ranking:
        assert isinstance(ranked, RankedCandidate)
        assert ranked.rank > 0
        assert 0 <= ranked.score <= 1


def test_ranking_with_empty_candidates():
    """Test ranking with no candidates returns empty result."""
    service = LLMRankingService(enabled=False)

    original = ImageMetricsSnapshot(size_bytes=500_000_000, layers=12, build_seconds=60.0)
    detection = AssistDetection(stack="python", confidence=0.95, evidence={})

    context = AssistContext(
        project_name="test-project",
        detection=detection,
        features=[],
        files=[],
        lockfiles=[],
        original=original,
        candidates=[],
        rag_matches=(),
    )

    result = service.rank_candidates(context)

    assert result is not None
    assert len(result.ranking) == 0
    assert "no candidates" in result.rationale.lower()
    assert result.llm_metrics["mode"] == "empty"


def test_explanation_with_llm_enabled(mock_client: LocalLLMClient, sample_context: AssistContext):
    """Test generating explanation with LLM enabled."""
    service = LLMRankingService(
        client=mock_client,
        enabled=True,
        adapter_version="test-v1",
    )

    result = service.explain_analysis(sample_context)

    assert result is not None
    assert result.adapter_version == "test-v1"
    assert len(result.summary) > 0
    # Check that explanation references the project context
    assert "multi-stage" in result.summary.lower() or "optimized" in result.summary.lower()


def test_explanation_with_llm_disabled(sample_context: AssistContext):
    """Test fallback heuristic explanation when LLM is disabled."""
    service = LLMRankingService(enabled=False, adapter_version="test-v1")

    result = service.explain_analysis(sample_context)

    assert result is not None
    assert result.adapter_version == "test-v1"
    assert "test-project" in result.summary
    assert "python" in result.summary.lower()
    assert "enable llm" in result.rationale.lower()


def test_rationale_validation_removes_dockerfile_tokens():
    """Test that rationale validation removes forbidden Dockerfile tokens."""
    service = LLMRankingService(enabled=False)

    # Test with Dockerfile instructions
    text_with_instructions = "This uses FROM alpine and RUN npm install with COPY package.json"
    cleaned = service._validate_rationale(text_with_instructions)

    # Uppercase Dockerfile instructions should be removed
    assert "FROM" not in cleaned
    assert "RUN" not in cleaned
    assert "COPY" not in cleaned

    # Other text should remain
    assert "alpine" in cleaned
    assert "npm" in cleaned
    assert "package.json" in cleaned


def test_rationale_validation_preserves_normal_text():
    """Test that rationale validation preserves normal text."""
    service = LLMRankingService(enabled=False)

    normal_text = "Multi-stage builds improve efficiency by separating build and runtime stages."
    cleaned = service._validate_rationale(normal_text)

    assert cleaned == normal_text


def test_ranking_prompt_includes_context(sample_context: AssistContext):
    """Test that ranking prompt includes relevant context."""
    service = LLMRankingService(enabled=False)

    prompt = service._build_ranking_prompt(sample_context)

    # Check key context elements are present
    assert "test-project" in prompt
    assert "python" in prompt
    assert "fastapi" in prompt
    assert "requirements.txt" in prompt
    assert "node_nextjs_alpine_runtime" in prompt
    assert "python_fastapi_wheels" in prompt
    # Check instructions are present
    assert "RANKING:" in prompt
    assert "RATIONALE:" in prompt


def test_explanation_prompt_includes_context(sample_context: AssistContext):
    """Test that explanation prompt includes relevant context."""
    service = LLMRankingService(enabled=False)

    prompt = service._build_explanation_prompt(sample_context)

    # Check key context elements are present
    assert "test-project" in prompt
    assert "python" in prompt
    assert "fastapi" in prompt
    assert "requirements.txt" in prompt
    # Check candidate info is present
    assert "node_nextjs_alpine_runtime" in prompt or "python_fastapi_wheels" in prompt


def test_ranking_response_parsing():
    """Test parsing of LLM ranking response."""
    service = LLMRankingService(enabled=False)

    original = ImageMetricsSnapshot(size_bytes=500_000_000, layers=12, build_seconds=60.0)
    detection = AssistDetection(stack="python", confidence=0.95, evidence={})

    candidate1 = AssistCandidate(
        rule_id="rule1",
        name="Candidate 1",
        description="First",
        rationale=[],
        policy_notes=[],
        metrics=ImageMetricsSnapshot(size_bytes=200_000_000, layers=8, build_seconds=45.0),
    )

    candidate2 = AssistCandidate(
        rule_id="rule2",
        name="Candidate 2",
        description="Second",
        rationale=[],
        policy_notes=[],
        metrics=ImageMetricsSnapshot(size_bytes=150_000_000, layers=7, build_seconds=40.0),
    )

    context = AssistContext(
        project_name="test",
        detection=detection,
        features=[],
        files=[],
        lockfiles=[],
        original=original,
        candidates=[candidate1, candidate2],
        rag_matches=(),
    )

    # Test parsing with well-formed response
    response = """
    RANKING: 2,1
    RATIONALE: Candidate 2 is better because it has fewer layers and smaller size.
    """

    ranking, rationale = service._parse_ranking_response(response, context)

    assert len(ranking) == 2
    assert ranking[0].rank == 1
    assert ranking[1].rank == 2
    assert "better" in rationale.lower()
    assert "layers" in rationale.lower()


def test_ranking_response_parsing_fallback():
    """Test that parsing falls back gracefully with malformed response."""
    service = LLMRankingService(enabled=False)

    original = ImageMetricsSnapshot(size_bytes=500_000_000, layers=12, build_seconds=60.0)
    detection = AssistDetection(stack="python", confidence=0.95, evidence={})

    candidate1 = AssistCandidate(
        rule_id="rule1",
        name="Candidate 1",
        description="First",
        rationale=[],
        policy_notes=[],
        metrics=ImageMetricsSnapshot(size_bytes=200_000_000, layers=8, build_seconds=45.0),
    )

    context = AssistContext(
        project_name="test",
        detection=detection,
        features=[],
        files=[],
        lockfiles=[],
        original=original,
        candidates=[candidate1],
        rag_matches=(),
    )

    # Test with malformed response (no ranking line)
    response = "This is some random text without proper formatting."

    ranking, rationale = service._parse_ranking_response(response, context)

    # Should fall back to default ordering
    assert len(ranking) == 1
    assert ranking[0].rank == 1
    # Should extract rationale from text
    assert len(rationale) > 0


def test_explanation_response_parsing():
    """Test parsing of LLM explanation response."""
    service = LLMRankingService(enabled=False)

    response = """
    This project can benefit from multi-stage builds.
    The FastAPI application will see size reduction.
    Exec-form CMD improves signal handling.
    """

    summary, rationale = service._parse_explanation_response(response)

    # Summary should be first 2 lines
    assert "multi-stage" in summary.lower()
    assert "fastapi" in summary.lower()

    # Rationale should be remaining lines
    assert "exec-form" in rationale.lower() or "signal" in rationale.lower()


def test_heuristic_ranking_scores_candidates():
    """Test that heuristic ranking properly scores candidates."""
    service = LLMRankingService(enabled=False)

    original = ImageMetricsSnapshot(size_bytes=500_000_000, layers=12, build_seconds=60.0)

    # Create candidates with different improvements
    candidate_best = AssistCandidate(
        rule_id="best_rule",
        name="Best",
        description="Best optimization",
        rationale=[],
        policy_notes=[],
        metrics=ImageMetricsSnapshot(
            size_bytes=100_000_000,  # Best size reduction
            layers=6,  # Best layer reduction
            build_seconds=30.0,  # Best build time
        ),
    )

    candidate_worst = AssistCandidate(
        rule_id="worst_rule",
        name="Worst",
        description="Minimal optimization",
        rationale=[],
        policy_notes=[],
        metrics=ImageMetricsSnapshot(
            size_bytes=450_000_000,  # Minimal size reduction
            layers=11,  # Minimal layer reduction
            build_seconds=58.0,  # Minimal build time improvement
        ),
    )

    detection = AssistDetection(stack="python", confidence=0.95, evidence={})

    context = AssistContext(
        project_name="test",
        detection=detection,
        features=[],
        files=[],
        lockfiles=[],
        original=original,
        candidates=[candidate_worst, candidate_best],  # Intentionally out of order
        rag_matches=(),
    )

    result = service._heuristic_ranking(context)

    # Best candidate should be ranked first
    assert result.ranking[0].rule_id == "best_rule"
    assert result.ranking[1].rule_id == "worst_rule"


def test_from_environment_creates_service(monkeypatch: pytest.MonkeyPatch):
    """Test creating service from environment."""
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("AIRGAP", "true")

    service = LLMRankingService.from_environment()

    assert service is not None
    assert service._enabled is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
