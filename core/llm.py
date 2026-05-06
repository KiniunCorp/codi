"""Lightweight local LLM server for offline LLM integration.

The real CODI project intends to embed an offline model runtime (e.g. llama.cpp
or Ollama) inside the container image. For the MVP programme the objective is to
provide an ergonomic abstraction, health checks, and deterministic behaviour so
that higher layers (CLI, API, future assist functions) can integrate against a
stable contract without shipping large model weights during development.

This module exposes two main primitives:

``LocalLLMServer`` — starts a tiny HTTP server with `/healthz` and
`/v1/completions` endpoints that return deterministic, policy-safe responses.
``LocalLLMClient`` — convenience helper used by tests and future features to
query the server.

The implementation deliberately keeps dependencies minimal by relying on Python's
standard library HTTP server primitives. Responses are intentionally short and
deterministic; they summarise prompts and encourage policies defined elsewhere in
the codebase.
"""

from __future__ import annotations

import json
import logging
import socketserver
import textwrap
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx

from .config import CodiEnvironment
from .security import enforce_airgap_guard, ensure_outbound_url_allowed, scrub_docker_tokens

LOGGER = logging.getLogger(__name__)

__all__ = [
    "AssistCandidate",
    "AssistContext",
    "AssistDetection",
    "ExplanationResult",
    "ImageMetricsSnapshot",
    "LLMAssist",
    "LLMRankingService",
    "LocalLLMClient",
    "LocalLLMConfig",
    "LocalLLMError",
    "LocalLLMServer",
    "RAGMatchReference",
    "RankedCandidate",
    "RankingResult",
    "TemplateRecommendation",
]


class LocalLLMError(RuntimeError):
    """Raised when the local LLM server cannot be started or queried."""


def read_adapter_metadata(adapter_path: Path) -> dict[str, Any]:
    """Read adapter metadata from metadata.json if available.

    Args:
        adapter_path: Path to adapter directory

    Returns:
        Dictionary with adapter metadata, or minimal defaults if not found
    """
    if not adapter_path or not adapter_path.exists():
        return {"version": "unknown", "model": "unknown", "status": "not_mounted"}

    metadata_file = adapter_path / "metadata.json"
    if not metadata_file.exists():
        return {"version": "unknown", "model": "unknown", "status": "no_metadata"}

    try:
        with open(metadata_file) as f:
            metadata = json.load(f)
        metadata["status"] = "loaded"
        return metadata
    except (json.JSONDecodeError, OSError) as e:
        LOGGER.warning("Failed to read adapter metadata from %s: %s", metadata_file, e)
        return {"version": "error", "model": "unknown", "status": "read_error", "error": str(e)}


def log_adapter_info(config: LocalLLMConfig) -> None:
    """Log adapter version and configuration at startup.

    Args:
        config: LLM configuration with adapter details
    """
    LOGGER.info("LLM Runtime Configuration:")
    LOGGER.info("  Code Model: %s", config.code_model)
    LOGGER.info("  Model ID: %s", config.model_id)
    LOGGER.info("  Adapter Version: %s", config.adapter_version)

    if config.adapter_path:
        metadata = read_adapter_metadata(config.adapter_path)
        LOGGER.info("  Adapter Path: %s", config.adapter_path)
        LOGGER.info("  Adapter Status: %s", metadata.get("status", "unknown"))

        if metadata.get("status") == "loaded":
            LOGGER.info("  Adapter Metadata:")
            LOGGER.info("    - Version: %s", metadata.get("version", "unknown"))
            LOGGER.info("    - Model: %s", metadata.get("model", "unknown"))
            if "dataset" in metadata:
                LOGGER.info("    - Dataset: %s", metadata.get("dataset"))
            if "training_date" in metadata:
                LOGGER.info("    - Training Date: %s", metadata.get("training_date"))
    else:
        LOGGER.info("  Adapter Path: Not configured (using base model only)")
        LOGGER.info("  TIP: Set ADAPTER_PATH to enable LoRA adapters")


@dataclass(slots=True)
class LocalLLMConfig:
    """Configuration for the local LLM server."""

    host: str = "127.0.0.1"
    port: int = 8081
    model_id: str = "codi-local-llama"
    max_tokens: int = 256
    code_model: str = "qwen2.5-coder-1.5b"
    adapter_path: Path | None = None
    adapter_version: str = "unknown"


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _handler_factory(config: LocalLLMConfig):  # type: ignore[return-type]
    class _LLMHandler(BaseHTTPRequestHandler):
        server_version = "CODILLM/0.1"
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            # Suppress noisy logging during tests; upstream logging hooks can wrap if needed.
            return

        def do_GET(self) -> None:
            if self.path.rstrip("/") == "/healthz":
                self._respond_json({"status": "ok", "model_id": config.model_id})
                return
            self.send_error(404, "Not Found")

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/v1/completions":
                self.send_error(404, "Not Found")
                return

            try:
                raw_body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._respond_json({"error": "invalid_json"}, status=400)
                return

            prompt = _extract_prompt(payload)
            completion = _generate_response(prompt, config)
            now = int(time.time())

            response = {
                "model": config.model_id,
                "created": now,
                "choices": [
                    {
                        "index": 0,
                        "text": completion,
                        "finish_reason": "stop",
                    }
                ],
                "usage": _usage_stats(prompt, completion),
            }

            self._respond_json(response)

        def _respond_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return _LLMHandler


class LocalLLMServer:
    """Manage the lifecycle of the lightweight local LLM HTTP server."""

    def __init__(self, config: LocalLLMConfig | None = None) -> None:
        self.config = config or LocalLLMConfig()
        self._server: _ThreadedHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._base_url: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------

    def start(self, *, timeout: float = 5.0) -> None:
        if self.is_running:
            return

        # Log adapter information at startup
        log_adapter_info(self.config)

        handler = _handler_factory(self.config)
        server = _ThreadedHTTPServer((self.config.host, self.config.port), handler)
        actual_host, actual_port = server.server_address
        if actual_host in {"0.0.0.0", "::"}:
            actual_host = "127.0.0.1"

        self.config.port = int(actual_port)
        self._server = server
        self._base_url = f"http://{actual_host}:{actual_port}"
        self._thread = threading.Thread(
            target=server.serve_forever, name="LocalLLMServer", daemon=True
        )
        self._thread.start()

        self._wait_for_health(timeout)

        LOGGER.info("Local LLM server started successfully at %s", self._base_url)

    def stop(self, *, timeout: float = 2.0) -> None:
        if not self.is_running:
            return

        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()

        if self._thread is not None:
            self._thread.join(timeout=timeout)

        self._server = None
        self._thread = None
        self._base_url = None

    # Support `with LocalLLMServer() as server:` syntax.
    def __enter__(self) -> LocalLLMServer:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.stop()

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    @property
    def base_url(self) -> str:
        if not self._base_url:
            raise LocalLLMError("Local LLM server is not running")
        return self._base_url

    def health_check(self, *, timeout: float = 0.5) -> dict[str, Any]:
        url = f"{self.base_url}/healthz"
        ensure_outbound_url_allowed(url)
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wait_for_health(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            try:
                self.health_check(timeout=0.25)
                return
            except Exception as exc:  # pragma: no cover - transient network startup
                last_error = exc
                time.sleep(0.05)

        raise LocalLLMError(
            f"Local LLM server failed health check within {timeout}s"
        ) from last_error


class LocalLLMClient:
    """Simple HTTP client for interacting with the local LLM server."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, *, timeout: float = 5.0) -> str:
        payload = {"prompt": prompt}
        url = f"{self.base_url}/v1/completions"
        ensure_outbound_url_allowed(url)
        response = httpx.post(url, json=payload, timeout=timeout)
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - escalated to caller
            raise LocalLLMError(f"LLM completion failed: {exc}") from exc

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise LocalLLMError("LLM completion did not return any choices")
        return str(choices[0].get("text", ""))


# ----------------------------------------------------------------------
# LLM assist orchestration with strict guardrails
# ----------------------------------------------------------------------


MB = 1024 * 1024


@dataclass(slots=True)
class ImageMetricsSnapshot:
    """Lightweight view of build metrics shared with the assist layer."""

    size_bytes: int
    layers: int
    build_seconds: float

    def size_mb(self) -> float:
        return round(self.size_bytes / MB, 2)


@dataclass(slots=True)
class AssistCandidate:
    """Candidate metadata exposed to the LLM assist functions."""

    rule_id: str
    name: str | None
    description: str | None
    rationale: Sequence[str]
    policy_notes: Sequence[str]
    metrics: ImageMetricsSnapshot


@dataclass(slots=True)
class AssistDetection:
    """Detection snapshot passed to the assist summary."""

    stack: str
    confidence: float
    evidence: Mapping[str, Sequence[str]]


@dataclass(slots=True)
class RAGMatchReference:
    """Compact reference to a prior run retrieved via RAG."""

    run_id: str
    score: float
    label: str | None
    candidate_rules: Sequence[str]


@dataclass(slots=True)
class AssistContext:
    """Signals provided to the LLM assist functions."""

    project_name: str
    detection: AssistDetection
    features: Sequence[str]
    files: Sequence[str]
    lockfiles: Sequence[str]
    original: ImageMetricsSnapshot
    candidates: Sequence[AssistCandidate]
    rag_matches: Sequence[RAGMatchReference] = ()


@dataclass(slots=True)
class TemplateRecommendation:
    """Structured recommendation returned by ``LLM_TEMPLATE_CHOICE``."""

    rule_id: str
    reason: str
    confidence: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "reason": self.reason,
            "confidence": round(self.confidence, 3),
            "source": self.source,
        }


class LLMAssist:
    """Facade for LLM assist routines with strong guardrails."""

    def __init__(
        self,
        client: LocalLLMClient | None = None,
        *,
        enabled: bool = True,
        timeout: float = 3.0,
        summary_max_chars: int = 480,
    ) -> None:
        self._client = client
        self._enabled = enabled
        self._timeout = timeout
        self._summary_max_chars = summary_max_chars

    @classmethod
    def from_environment(cls) -> LLMAssist:
        settings = CodiEnvironment.from_env()
        return cls.from_settings(settings)

    @classmethod
    def from_settings(cls, settings: CodiEnvironment) -> LLMAssist:
        enforce_airgap_guard()

        endpoint = settings.llm.endpoint
        enabled = settings.llm.enabled
        client = None
        if endpoint:
            ensure_outbound_url_allowed(endpoint)
            client = LocalLLMClient(endpoint)
        return cls(client=client, enabled=enabled)

    def summarise(self, context: AssistContext) -> str:
        if not context.candidates:
            return "No optimisation candidates were generated."

        prompt = _build_summary_prompt(context)
        raw = self._complete(prompt)
        if raw:
            summary = _sanitize_summary_text(raw, max_chars=self._summary_max_chars)
            if summary:
                return summary
        return _fallback_summary(context)

    def recommend_template(self, context: AssistContext) -> TemplateRecommendation | None:
        if not context.candidates:
            return None

        allowed = {candidate.rule_id for candidate in context.candidates}
        prompt = _build_template_prompt(context)
        raw = self._complete(prompt)
        if raw:
            parsed = _parse_recommendation(raw, allowed)
            if parsed:
                rule_id, reason = parsed
                sanitized_reason = _sanitize_reason_text(reason)
                return TemplateRecommendation(
                    rule_id=rule_id,
                    reason=sanitized_reason,
                    confidence=0.65,
                    source="llm",
                )

        return _fallback_recommendation(context)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _complete(self, prompt: str) -> str | None:
        if not self._enabled or self._client is None:
            return None
        try:
            return self._client.complete(prompt, timeout=self._timeout)
        except LocalLLMError:
            return None
        except Exception:  # pragma: no cover - defensive guard
            return None


# ----------------------------------------------------------------------
# Ranking and rationale service layer
# ----------------------------------------------------------------------


@dataclass(slots=True)
class RankedCandidate:
    """Represents a candidate with ranking metadata."""

    candidate_id: str
    rule_id: str
    score: float
    rank: int


@dataclass(slots=True)
class RankingResult:
    """Result of ranking candidates with LLM assistance."""

    ranking: Sequence[RankedCandidate]
    rationale: str
    adapter_version: str
    llm_metrics: dict[str, Any]


@dataclass(slots=True)
class ExplanationResult:
    """Result of generating an explanation for analysis results."""

    summary: str
    rationale: str
    adapter_version: str


class LLMRankingService:
    """Service layer for LLM-assisted ranking and rationale generation.

    This service provides:
    - Candidate ranking with confidence scores
    - Rationale generation referencing rule names and CMD signals
    - Validators that reject Dockerfile tokens outside template bounds
    - Support for LLM_ENABLED toggle
    """

    def __init__(
        self,
        client: LocalLLMClient | None = None,
        *,
        enabled: bool = True,
        timeout: float = 3.0,
        adapter_version: str = "unknown",
    ) -> None:
        self._client = client
        self._enabled = enabled
        self._timeout = timeout
        self._adapter_version = adapter_version

    @classmethod
    def from_environment(cls) -> LLMRankingService:
        """Create service from environment settings."""
        settings = CodiEnvironment.from_env()
        return cls.from_settings(settings)

    @classmethod
    def from_settings(cls, settings: CodiEnvironment) -> LLMRankingService:
        """Create service from CodiEnvironment settings."""
        enforce_airgap_guard()

        endpoint = settings.llm.endpoint
        enabled = settings.llm.enabled
        client = None
        adapter_version = "unknown"

        if endpoint:
            ensure_outbound_url_allowed(endpoint)
            client = LocalLLMClient(endpoint)

        # Try to read adapter version from configured path
        if settings.llm.adapter_path:
            from pathlib import Path

            adapter_path = Path(settings.llm.adapter_path)
            metadata = read_adapter_metadata(adapter_path)
            adapter_version = metadata.get("version", "unknown")

        return cls(
            client=client,
            enabled=enabled,
            adapter_version=adapter_version,
        )

    def rank_candidates(self, context: AssistContext) -> RankingResult:
        """Rank candidates and provide rationale with rule and CMD references.

        Args:
            context: Context containing candidates, detection, and analysis data

        Returns:
            RankingResult with ordered candidates, rationale, and metrics

        Raises:
            LocalLLMError: If ranking fails when LLM is enabled
        """
        if not context.candidates:
            return RankingResult(
                ranking=[],
                rationale="No candidates available for ranking.",
                adapter_version=self._adapter_version,
                llm_metrics={"mode": "empty"},
            )

        if not self._enabled or self._client is None:
            # Fallback to heuristic ranking
            return self._heuristic_ranking(context)

        # Build ranking prompt
        prompt = self._build_ranking_prompt(context)

        # Get LLM completion
        try:
            raw_response = self._client.complete(prompt, timeout=self._timeout)
        except LocalLLMError as exc:
            LOGGER.warning("LLM ranking failed, falling back to heuristic: %s", exc)
            return self._heuristic_ranking(context)

        # Parse and validate response
        ranking, rationale = self._parse_ranking_response(raw_response, context)

        # Validate rationale doesn't contain forbidden Dockerfile tokens
        validated_rationale = self._validate_rationale(rationale)

        # Calculate metrics
        llm_metrics = {
            "mode": "llm",
            "adapter_version": self._adapter_version,
            "candidate_count": len(context.candidates),
            "mean_confidence": sum(r.score for r in ranking) / len(ranking) if ranking else 0.0,
        }

        return RankingResult(
            ranking=ranking,
            rationale=validated_rationale,
            adapter_version=self._adapter_version,
            llm_metrics=llm_metrics,
        )

    def explain_analysis(self, context: AssistContext) -> ExplanationResult:
        """Generate explanation for analysis results with CMD signal references.

        Args:
            context: Context containing detection and analysis data

        Returns:
            ExplanationResult with summary and rationale
        """
        if not self._enabled or self._client is None:
            # Fallback to heuristic explanation
            return self._heuristic_explanation(context)

        # Build explanation prompt
        prompt = self._build_explanation_prompt(context)

        # Get LLM completion
        try:
            raw_response = self._client.complete(prompt, timeout=self._timeout)
        except LocalLLMError as exc:
            LOGGER.warning("LLM explanation failed, falling back to heuristic: %s", exc)
            return self._heuristic_explanation(context)

        # Parse and validate response
        summary, rationale = self._parse_explanation_response(raw_response)

        # Validate rationale
        validated_summary = self._validate_rationale(summary)
        validated_rationale = self._validate_rationale(rationale)

        return ExplanationResult(
            summary=validated_summary,
            rationale=validated_rationale,
            adapter_version=self._adapter_version,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_ranking_prompt(self, context: AssistContext) -> str:
        """Build prompt for ranking candidates."""
        lines = [
            "You are CODI's ranking assistant. Rank the following Dockerfile optimization candidates.",
            "Consider size reduction, layer count, build time, and adherence to policy guardrails.",
            "",
            f"Project: {context.project_name}",
            f"Stack: {context.detection.stack} (confidence {context.detection.confidence:.2f})",
            f"Features: {', '.join(sorted(context.features)) or 'none'}",
            f"Files: {', '.join(sorted(context.files)) or 'none'}",
            f"Lockfiles: {', '.join(sorted(context.lockfiles)) or 'none'}",
            "",
            "Original metrics:",
            f"- Layers: {context.original.layers}",
            f"- Size: {context.original.size_mb():.1f} MB",
            f"- Build time: {context.original.build_seconds:.2f}s",
            "",
            "Candidates to rank:",
        ]

        for idx, candidate in enumerate(context.candidates, start=1):
            lines.append(f"{idx}. Rule: {candidate.rule_id}")
            if candidate.name:
                lines.append(f"   Name: {candidate.name}")
            lines.append(
                f"   Layers: {candidate.metrics.layers} ({_format_delta_layers(context.original.layers, candidate.metrics.layers)})"
            )
            lines.append(
                f"   Size: {candidate.metrics.size_mb():.1f} MB ({_format_delta_mb(context.original.size_bytes, candidate.metrics.size_bytes)})"
            )
            lines.append(
                f"   Build time: {candidate.metrics.build_seconds:.2f}s ({_format_delta_seconds(context.original.build_seconds, candidate.metrics.build_seconds)})"
            )
            lines.append("")

        lines.extend(
            [
                "Respond with:",
                "1. RANKING: List candidate numbers in order of preference (e.g., '2,1,3')",
                "2. RATIONALE: Brief explanation referencing rule IDs and improvements",
                "",
                "Do not include Dockerfile instructions in your response.",
            ]
        )

        return "\n".join(lines)

    def _build_explanation_prompt(self, context: AssistContext) -> str:
        """Build prompt for explaining analysis."""
        lines = [
            "You are CODI's analysis assistant. Explain the optimization opportunities for this project.",
            "",
            f"Project: {context.project_name}",
            f"Stack: {context.detection.stack} (confidence {context.detection.confidence:.2f})",
            f"Features: {', '.join(sorted(context.features)) or 'none'}",
            f"Files: {', '.join(sorted(context.files)) or 'none'}",
            f"Lockfiles: {', '.join(sorted(context.lockfiles)) or 'none'}",
            "",
            "Original metrics:",
            f"- Layers: {context.original.layers}",
            f"- Size: {context.original.size_mb():.1f} MB",
            f"- Build time: {context.original.build_seconds:.2f}s",
            "",
        ]

        if context.candidates:
            lines.append("Available optimization candidates:")
            for candidate in context.candidates:
                lines.append(f"- {candidate.rule_id}: {candidate.name or 'No description'}")

        lines.extend(
            [
                "",
                "Provide a concise explanation (2-3 sentences) of:",
                "1. What optimization opportunities exist",
                "2. Expected benefits",
                "",
                "Do not include Dockerfile instructions in your response.",
            ]
        )

        return "\n".join(lines)

    def _parse_ranking_response(
        self,
        raw_response: str,
        context: AssistContext,
    ) -> tuple[Sequence[RankedCandidate], str]:
        """Parse LLM ranking response into structured data."""
        lines = [line.strip() for line in raw_response.splitlines() if line.strip()]

        ranking_order: list[int] = []
        rationale_lines: list[str] = []
        in_rationale = False

        for line in lines:
            lower = line.lower()
            if lower.startswith("ranking:"):
                # Parse ranking order
                order_text = line.split(":", 1)[1].strip()
                try:
                    ranking_order = [int(x.strip()) for x in order_text.split(",")]
                except ValueError:
                    # Fallback if parsing fails
                    ranking_order = list(range(1, len(context.candidates) + 1))
            elif lower.startswith("rationale:"):
                in_rationale = True
                rationale_text = line.split(":", 1)[1].strip()
                if rationale_text:
                    rationale_lines.append(rationale_text)
            elif in_rationale:
                rationale_lines.append(line)

        # If no ranking found, use heuristic order
        if not ranking_order:
            ranking_order = list(range(1, len(context.candidates) + 1))

        # Build ranked candidates
        ranked: list[RankedCandidate] = []
        for rank, idx in enumerate(ranking_order, start=1):
            if 1 <= idx <= len(context.candidates):
                candidate = context.candidates[idx - 1]
                score = 1.0 - (rank - 1) * 0.2  # Decreasing confidence score
                ranked.append(
                    RankedCandidate(
                        candidate_id=f"candidate_{idx}",
                        rule_id=candidate.rule_id,
                        score=max(0.1, score),
                        rank=rank,
                    )
                )

        rationale = " ".join(rationale_lines) or "Ranking based on metrics analysis."
        return ranked, rationale

    def _parse_explanation_response(self, raw_response: str) -> tuple[str, str]:
        """Parse LLM explanation response."""
        lines = [line.strip() for line in raw_response.splitlines() if line.strip()]

        if not lines:
            return "", ""

        # First two lines form the summary; any additional lines are the rationale.
        summary = " ".join(lines[:2])
        rationale = " ".join(lines[2:])
        return summary, rationale

    def _validate_rationale(self, text: str) -> str:
        """Validate rationale doesn't contain forbidden Dockerfile tokens."""
        return scrub_docker_tokens(text)

    def _heuristic_ranking(self, context: AssistContext) -> RankingResult:
        """Fallback heuristic ranking when LLM is disabled."""
        # Rank by best size reduction, then layer reduction, then build time
        scored: list[tuple[AssistCandidate, tuple[float, float, float]]] = []

        for candidate in context.candidates:
            score = _candidate_score(candidate, context.original)
            scored.append((candidate, score))

        # Sort by score (descending)
        scored.sort(key=lambda x: x[1], reverse=True)

        # Build ranked results
        ranking = [
            RankedCandidate(
                candidate_id=f"candidate_{idx+1}",
                rule_id=candidate.rule_id,
                score=0.35,  # Lower confidence for heuristic
                rank=rank,
            )
            for rank, (candidate, _) in enumerate(scored, start=1)
            for idx, c in enumerate(context.candidates)
            if c.rule_id == candidate.rule_id
        ]

        # Build rationale
        best = scored[0][0]
        delta_size = context.original.size_mb() - best.metrics.size_mb()
        delta_layers = context.original.layers - best.metrics.layers

        rationale = (
            f"Heuristic ranking suggests {best.rule_id} as the best candidate, "
            f"offering {delta_size:.1f} MB size reduction and {delta_layers} fewer layers. "
            "Enable LLM for more detailed analysis."
        )

        return RankingResult(
            ranking=ranking,
            rationale=rationale,
            adapter_version=self._adapter_version,
            llm_metrics={"mode": "heuristic"},
        )

    def _heuristic_explanation(self, context: AssistContext) -> ExplanationResult:
        """Fallback heuristic explanation when LLM is disabled."""
        summary = (
            f"{context.project_name} ({context.detection.stack}) can benefit from "
            f"multi-stage builds and optimized base images."
        )

        rationale = (
            f"Detected {len(context.candidates)} optimization opportunities "
            f"targeting layer reduction and size optimization. "
            "Enable LLM for detailed rationale."
        )

        return ExplanationResult(
            summary=summary,
            rationale=rationale,
            adapter_version=self._adapter_version,
        )


# ----------------------------------------------------------------------
# Response shaping helpers
# ----------------------------------------------------------------------


def _extract_prompt(payload: dict[str, Any]) -> str:
    prompt = ""
    if "prompt" in payload and isinstance(payload["prompt"], str):
        prompt = payload["prompt"]
    elif isinstance(payload.get("messages"), Iterable):
        fragments: list[str] = []
        for item in payload["messages"]:
            if isinstance(item, dict) and isinstance(item.get("content"), str):
                fragments.append(item["content"])
        prompt = "\n".join(fragments)
    return prompt.strip()


def _generate_response(prompt: str, config: LocalLLMConfig) -> str:
    if not prompt:
        return "[codi-local] No prompt supplied. Ensure messages include 'content'."

    normalized = " ".join(segment.strip() for segment in prompt.splitlines() if segment.strip())
    max_chars = max(config.max_tokens * 4, 120)
    if len(normalized) > max_chars:
        normalized = normalized[: max_chars - 3].rstrip() + "..."

    highlights = _extract_highlights(normalized)
    summary_lines = [
        f"[{config.model_id}] Offline reasoning summary:",
        f"- Key prompt: {normalized}",
    ]
    if highlights:
        summary_lines.extend(f"- Insight: {item}" for item in highlights)
    summary_lines.append("- Guarantee: Deterministic templates remain enforced.")
    return "\n".join(summary_lines)


def _extract_highlights(normalized_prompt: str) -> list[str]:
    highlights: list[str] = []
    lower = normalized_prompt.lower()
    if "docker" in lower or "image" in lower:
        highlights.append("Reinforce multi-stage builds for smaller runtimes.")
    if "security" in lower or "policy" in lower:
        highlights.append("Ensure policy gates stay active for offline runs.")
    if "next" in lower or "fastapi" in lower or "spring" in lower:
        highlights.append("Tailor rationale to the detected stack signals.")
    if not highlights:
        highlights.append("Provide concise, policy-aware rationale snippets.")
    return highlights


def _usage_stats(prompt: str, completion: str) -> dict[str, int]:
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text.split()) // 3 + 1)

    prompt_tokens = _estimate_tokens(prompt)
    completion_tokens = _estimate_tokens(completion)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


# ----------------------------------------------------------------------
# Assist prompt construction & sanitisation utilities
# ----------------------------------------------------------------------


def _build_summary_prompt(context: AssistContext) -> str:
    detection = context.detection
    feature_text = ", ".join(sorted(context.features)) or "none"
    lockfile_text = ", ".join(sorted(context.lockfiles)) or "none"
    evidence_lines = _format_evidence(detection.evidence)
    candidates_lines = "\n".join(
        _format_candidate_line(candidate, context.original) for candidate in context.candidates
    )
    rag_text = _format_rag_matches(context.rag_matches)

    prompt = textwrap.dedent(f"""
        You are CODI's offline assistant. Provide a concise human-readable summary for a Docker optimisation
        report without emitting Dockerfile instructions. Focus on improvements, stack awareness, and policy guarantees.

        Project: {context.project_name}
        Stack: {detection.stack}
        Detection confidence: {detection.confidence:.2f}
        Feature signals: {feature_text}
        Lockfiles: {lockfile_text}
        Original metrics: {context.original.layers} layers, {context.original.size_mb():.1f} MB, {context.original.build_seconds:.2f} s
        Candidates:
        {candidates_lines}
        Evidence:
        {evidence_lines}
        RAG references: {rag_text or 'none'}

        Respond with 2 short sentences (max 60 words total). Avoid bullet lists, avoid Dockerfile keywords, emphasise policy adherence.
        """).strip()
    return prompt


def _build_template_prompt(context: AssistContext) -> str:
    lines = [
        "You are CODI's template guard. Choose the best candidate by referencing only the provided options.",
        f"Stack: {context.detection.stack} (confidence {context.detection.confidence:.2f})",
        f"Features: {', '.join(sorted(context.features)) or 'none'}",
        f"Original metrics: {context.original.layers} layers | {context.original.size_mb():.1f} MB | {context.original.build_seconds:.2f} s",
        "Candidates:",
    ]

    for index, candidate in enumerate(context.candidates, start=1):
        metrics = candidate.metrics
        lines.append(
            f"{index}. {candidate.rule_id} — {metrics.layers} layers ({_format_delta_layers(context.original.layers, metrics.layers)}), "
            f"{metrics.size_mb():.1f} MB ({_format_delta_mb(context.original.size_bytes, metrics.size_bytes)}), "
            f"{metrics.build_seconds:.2f} s ({_format_delta_seconds(context.original.build_seconds, metrics.build_seconds)})"
        )
    lines.append(
        "Reply with exactly two lines:\nRULE: <rule_id>\nREASON: <short justification>. Stay within 30 words. Use only the listed rule ids."
    )
    return "\n".join(lines)


def _parse_recommendation(raw: str, allowed: set[str]) -> tuple[str, str] | None:
    rule_id: str | None = None
    reason_parts: list[str] = []

    for line in raw.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        lower = cleaned.lower()
        if lower.startswith("rule") and ":" in cleaned:
            candidate = cleaned.split(":", 1)[1].strip()
            if candidate in allowed:
                rule_id = candidate
        elif lower.startswith("reason") and ":" in cleaned:
            reason_parts.append(cleaned.split(":", 1)[1].strip())
        else:
            detected = _match_allowed(cleaned, allowed)
            if detected and rule_id is None:
                rule_id = detected
            elif rule_id and not reason_parts:
                reason_parts.append(cleaned)

    if rule_id is None:
        return None

    reason = " ".join(reason_parts).strip()
    return rule_id, reason or f"{rule_id} offers the strongest estimated improvement."


def _match_allowed(text: str, allowed: set[str]) -> str | None:
    for rule_id in allowed:
        if rule_id in text.split():
            return rule_id
        if rule_id in text:
            return rule_id
    return None


def _sanitize_summary_text(raw: str, *, max_chars: int) -> str:
    parts: list[str] = []
    for chunk in raw.splitlines():
        cleaned = chunk.strip()
        if not cleaned:
            continue
        if cleaned.startswith("[") and "]" in cleaned:
            cleaned = cleaned.split("]", 1)[1].strip()
        if cleaned.startswith("-"):
            cleaned = cleaned.lstrip("- ").strip()
        parts.append(cleaned)
    text = scrub_docker_tokens(" ".join(parts))
    return text[:max_chars].strip()


def _sanitize_reason_text(raw: str) -> str:
    if not raw:
        return ""
    cleaned = raw.replace("\n", " ").strip()
    sanitized = scrub_docker_tokens(cleaned)
    return sanitized[:240].strip()


def _fallback_summary(context: AssistContext) -> str:
    best = _select_best_candidate(context)
    metrics = best.metrics
    original = context.original
    delta_size = original.size_mb() - metrics.size_mb()
    delta_layers = original.layers - metrics.layers
    delta_seconds = original.build_seconds - metrics.build_seconds

    features = ", ".join(sorted(context.features)) or "core heuristics"
    rag_hint = ""
    if context.rag_matches:
        top = context.rag_matches[0]
        rag_label = top.label or top.run_id
        rag_hint = f" Similar prior run: {rag_label} (score {top.score:.2f})."

    improvements = []
    if delta_size > 0.05:
        improvements.append(f"{delta_size:.1f} MB smaller")
    if delta_layers > 0:
        improvements.append(f"{delta_layers} fewer layers")
    if delta_seconds > 0.1:
        improvements.append(f"{delta_seconds:.1f}s faster builds")
    improvement_text = ", ".join(improvements) or "steady metrics"

    summary = (
        f"{context.project_name} ({context.detection.stack}) benefits most via template {best.rule_id}, delivering {improvement_text}. "
        f"Signals: {features}. Policy guardrails remain enforced.{rag_hint}"
    )
    return summary.strip()


def _fallback_recommendation(context: AssistContext) -> TemplateRecommendation:
    best = _select_best_candidate(context)
    original = context.original
    delta_size = original.size_mb() - best.metrics.size_mb()
    delta_layers = original.layers - best.metrics.layers
    reason_parts = []
    if delta_size > 0.05:
        reason_parts.append(f"~{delta_size:.1f} MB smaller")
    if delta_layers > 0:
        reason_parts.append(f"{delta_layers} fewer layers")
    reason = " & ".join(reason_parts) or "balanced metrics and policy fit"
    return TemplateRecommendation(
        rule_id=best.rule_id,
        reason=f"Heuristic tie-breaker: {reason}.",
        confidence=0.35,
        source="heuristic",
    )


def _select_best_candidate(context: AssistContext) -> AssistCandidate:
    original = context.original
    best = context.candidates[0]
    best_score = _candidate_score(best, original)
    for candidate in context.candidates[1:]:
        score = _candidate_score(candidate, original)
        if score > best_score:
            best = candidate
            best_score = score
    return best


def _candidate_score(
    candidate: AssistCandidate, original: ImageMetricsSnapshot
) -> tuple[float, float, float]:
    delta_size = max(0.0, (original.size_bytes - candidate.metrics.size_bytes) / MB)
    delta_layers = max(0.0, float(original.layers - candidate.metrics.layers))
    delta_seconds = max(0.0, original.build_seconds - candidate.metrics.build_seconds)
    return delta_size, delta_layers, delta_seconds


def _format_evidence(evidence: Mapping[str, Sequence[str]]) -> str:
    if not evidence:
        return "(no additional signals)"
    parts = []
    for category, signals in evidence.items():
        items = ", ".join(str(signal) for signal in signals) if signals else "none"
        parts.append(f"- {category}: {items}")
    return "\n".join(parts)


def _format_candidate_line(candidate: AssistCandidate, original: ImageMetricsSnapshot) -> str:
    metrics = candidate.metrics
    return (
        f"- {candidate.rule_id}: {metrics.layers} layers ({_format_delta_layers(original.layers, metrics.layers)}), "
        f"{metrics.size_mb():.1f} MB ({_format_delta_mb(original.size_bytes, metrics.size_bytes)}), "
        f"{metrics.build_seconds:.2f} s ({_format_delta_seconds(original.build_seconds, metrics.build_seconds)})"
    )


def _format_rag_matches(matches: Sequence[RAGMatchReference]) -> str:
    if not matches:
        return ""
    lines = []
    for match in matches[:2]:
        rule_text = ",".join(match.candidate_rules) if match.candidate_rules else "n/a"
        label = match.label or "unknown"
        lines.append(f"{label} (score {match.score:.2f}, rules {rule_text})")
    return "; ".join(lines)


def _format_delta_mb(original_bytes: int, candidate_bytes: int) -> str:
    delta = (original_bytes - candidate_bytes) / MB
    if delta > 0:
        return f"-{delta:.1f} MB"
    if delta < 0:
        return f"+{abs(delta):.1f} MB"
    return "±0 MB"


def _format_delta_layers(original_layers: int, candidate_layers: int) -> str:
    delta = original_layers - candidate_layers
    if delta > 0:
        return f"-{delta}"
    if delta < 0:
        return f"+{abs(delta)}"
    return "±0"


def _format_delta_seconds(original_seconds: float, candidate_seconds: float) -> str:
    delta = original_seconds - candidate_seconds
    if delta > 0.01:
        return f"-{delta:.2f} s"
    if delta < -0.01:
        return f"+{abs(delta):.2f} s"
    return "±0 s"
