"""Centralised environment configuration helpers for CODI."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


def parse_env_bool(value: str | None, *, default: bool) -> bool:
    """Parse a boolean environment value with a sensible default."""

    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def parse_env_int(value: str | None, *, default: int) -> int:
    """Parse an integer environment value with fallback on errors."""

    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_allowlist(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    entries = [item.strip() for item in value.split(",") if item.strip()]
    return tuple(entries)


@dataclass(slots=True)
class LLMConfig:
    """Runtime configuration for the local or remote LLM assist layer."""

    enabled: bool
    endpoint: str | None
    host: str
    port: int
    model_id: str
    max_tokens: int
    code_model: str
    adapter_path: Path | None
    adapter_version: str

    def to_metadata(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "endpoint": self.endpoint,
            "host": self.host,
            "port": self.port,
            "model_id": self.model_id,
            "max_tokens": self.max_tokens,
            "code_model": self.code_model,
            "adapter_path": str(self.adapter_path) if self.adapter_path else None,
            "adapter_version": self.adapter_version,
        }


@dataclass(slots=True)
class CodiEnvironment:
    """Snapshot of CODI's environment-driven configuration."""

    output_root: Path
    rules_path: Path
    rules_source: str
    airgap_enabled: bool
    airgap_allowlist: tuple[str, ...]
    llm: LLMConfig

    @classmethod
    def from_env(cls) -> CodiEnvironment:
        base_dir = Path(__file__).resolve().parent.parent

        output_raw = os.getenv("CODI_OUTPUT_ROOT", "runs")
        output_root = Path(output_raw).expanduser().resolve()

        rules_env = os.getenv("RULES_PATH")
        if rules_env:
            rules_path = Path(rules_env).expanduser().resolve()
            rules_source = "env"
        else:
            rules_path = (base_dir / "patterns" / "rules.yml").resolve()
            rules_source = "default"

        airgap_enabled = parse_env_bool(os.getenv("AIRGAP"), default=True)
        airgap_allowlist = _split_allowlist(os.getenv("AIRGAP_ALLOWLIST"))

        endpoint = os.getenv("LLM_ENDPOINT") or os.getenv("CODI_LLM_ENDPOINT")
        llm_enabled = parse_env_bool(os.getenv("LLM_ENABLED"), default=True)
        llm_host = os.getenv("LLM_HOST", "127.0.0.1")
        llm_port = parse_env_int(os.getenv("LLM_PORT"), default=8081)
        llm_model_id = os.getenv("LLM_MODEL_ID", "codi-local-llama")
        llm_max_tokens = parse_env_int(os.getenv("LLM_MAX_TOKENS"), default=256)

        code_model = os.getenv("CODE_MODEL", "qwen2.5-coder-1.5b")
        adapter_path_str = os.getenv("ADAPTER_PATH")
        adapter_path = Path(adapter_path_str).expanduser().resolve() if adapter_path_str else None
        adapter_version = os.getenv("ADAPTER_VERSION", "unknown")

        llm_config = LLMConfig(
            enabled=llm_enabled,
            endpoint=endpoint,
            host=llm_host,
            port=llm_port,
            model_id=llm_model_id,
            max_tokens=llm_max_tokens,
            code_model=code_model,
            adapter_path=adapter_path,
            adapter_version=adapter_version,
        )

        return cls(
            output_root=output_root,
            rules_path=rules_path,
            rules_source=rules_source,
            airgap_enabled=airgap_enabled,
            airgap_allowlist=airgap_allowlist,
            llm=llm_config,
        )

    def with_output_root(self, value: Path) -> CodiEnvironment:
        """Return a new environment snapshot pointing to a different output root."""

        normalized = value.expanduser().resolve()
        return replace(self, output_root=normalized)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "output_root": str(self.output_root),
            "rules_path": str(self.rules_path),
            "rules_source": self.rules_source,
            "airgap": {
                "enabled": self.airgap_enabled,
                "allowlist": list(self.airgap_allowlist),
            },
            "llm": self.llm.to_metadata(),
        }
