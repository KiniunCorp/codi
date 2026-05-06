"""Runtime launcher for the CODI Complete container.

This helper orchestrates both the FastAPI service and the lightweight local LLM
server. The container entrypoint simply executes this
module, which performs the following steps:

1. Instantiate and start ``LocalLLMServer`` using environment-driven settings.
2. Populate ``LLM_ENDPOINT`` for downstream components if it is not already set.
3. Launch the FastAPI app via ``uvicorn`` while ensuring clean shutdown
   semantics for both processes when the container receives termination signals.

The implementation keeps dependencies minimal (pure Python standard library and
existing project modules) so the complete image remains lightweight and
air-gapped by default.
"""

from __future__ import annotations

import logging
import os
import signal
import sys

import uvicorn
from core.llm import LocalLLMConfig, LocalLLMServer
from core.security import enforce_airgap_guard, ensure_model_mount_path, is_airgap_enabled

LOGGER = logging.getLogger("codi.runtime.complete")


def _env(key: str, default: str) -> str:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return value


def configure_logging() -> None:
    """Initialise basic logging if the host application did not do so."""

    if logging.getLogger().handlers:
        return
    logging.basicConfig(  # pragma: no cover - defensive guard for container runtime
        level=os.getenv("CODI_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def start_llm_server() -> LocalLLMServer:
    """Start the embedded local LLM HTTP server."""
    from pathlib import Path

    host = _env("LLM_HOST", "127.0.0.1")
    port = int(_env("LLM_PORT", "8081"))
    model_id = _env("LLM_MODEL_ID", "codi-local-llama")
    max_tokens = int(_env("LLM_MAX_TOKENS", "256"))
    code_model = _env("CODE_MODEL", "qwen2.5-coder-1.5b")
    adapter_version = _env("ADAPTER_VERSION", "unknown")

    adapter_path_str = _env("ADAPTER_PATH", "")
    adapter_path = Path(adapter_path_str).resolve() if adapter_path_str else None

    config = LocalLLMConfig(
        host=host,
        port=port,
        model_id=model_id,
        max_tokens=max_tokens,
        code_model=code_model,
        adapter_path=adapter_path,
        adapter_version=adapter_version,
    )
    server = LocalLLMServer(config=config)

    LOGGER.info("Starting local LLM server on %s:%s", host, port)
    LOGGER.info("  Code Model: %s", code_model)
    LOGGER.info("  Adapter: %s (version: %s)", adapter_path or "none", adapter_version)

    timeout = float(_env("LLM_START_TIMEOUT", "5.0"))
    server.start(timeout=timeout)

    base_url = server.base_url
    os.environ.setdefault("LLM_ENDPOINT", base_url)
    os.environ.setdefault("LLM_ENABLED", "true")
    LOGGER.info("Local LLM server healthy at %s", base_url)
    return server


def prepare_model_mount() -> None:
    """Ensure the model mount directory exists and surface helpful logs."""

    path = ensure_model_mount_path(create=True)
    os.environ.setdefault("MODEL_MOUNT_PATH", str(path))
    if path.exists():
        LOGGER.info("Model mount path ready at %s (AIRGAP=%s)", path, is_airgap_enabled())


def run_uvicorn() -> None:
    """Launch the FastAPI application using uvicorn."""

    app_path = _env("CODI_API_APP", "api.server:app")
    host = _env("API_HOST", "0.0.0.0")
    port = int(_env("API_PORT", "8000"))
    log_level = _env("UVICORN_LOG_LEVEL", "info")

    LOGGER.info("Starting CODI API via uvicorn (%s:%s)", host, port)
    uvicorn.run(app_path, host=host, port=port, log_level=log_level)


def main(
    argv: list[str] | None = None,
) -> int:  # pragma: no cover - exercised in container runtime
    """Module entrypoint used by the Complete container CMD."""

    configure_logging()
    enforce_airgap_guard()
    prepare_model_mount()
    server = start_llm_server()

    def _shutdown_handler(signum: int, frame) -> None:
        LOGGER.info("Received signal %s, shutting down CODI services", signum)
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    try:
        run_uvicorn()
    finally:
        LOGGER.info("Stopping local LLM server")
        server.stop()

    return 0


if __name__ == "__main__":  # pragma: no cover - manual execution path
    raise SystemExit(main(sys.argv[1:]))
