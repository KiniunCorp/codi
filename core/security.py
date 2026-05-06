"""Security and policy gates for Dockerfile validation and runtime safeguards.

These checks are deterministic and fast; they run during analysis and prior to
executing any real builds. Violations are reported with actionable messages.

This module also provides **air-gap enforcement** utilities that guard outbound
HTTP(S) requests whenever ``AIRGAP=true`` (the default across CODI containers).
The helper patches ``httpx`` entry points to reject non-loopback destinations
and exposes convenience functions for other layers to query the air-gap status,
validate endpoints, and resolve the model mount path expected by
the Complete container.
"""

from __future__ import annotations

import ipaddress
import os
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import parse_env_bool
from .parse import DockerfileDocument

__all__ = [
    "AirgapViolation",
    "SecurityPolicyError",
    "disable_airgap_guard",
    "enforce_airgap_guard",
    "ensure_instruction_allowlist",
    "ensure_model_mount_path",
    "ensure_outbound_url_allowed",
    "evaluate_policy",
    "get_model_mount_path",
    "is_airgap_enabled",
    "scrub_docker_tokens",
    "validate_or_raise",
]

AIRGAP_ENV_VAR = "AIRGAP"
AIRGAP_ALLOWLIST_ENV_VAR = "AIRGAP_ALLOWLIST"

MODEL_MOUNT_ENV_VARS = (
    "MODEL_MOUNT_PATH",
    "CODI_MODEL_PATH",
)
DEFAULT_MODEL_MOUNT_PATH = Path("/models")


class AirgapViolation(RuntimeError):
    """Raised when an outbound network request violates the air-gap policy."""


_httpx_guard_lock = threading.Lock()
_httpx_guard_active = False
_httpx_original_functions: dict[str, Callable[..., Any]] = {}
_httpx_client_request_original: Callable[..., Any] | None = None
_httpx_async_client_request_original: Callable[..., Any] | None = None


def is_airgap_enabled(default: bool = True) -> bool:
    """Return ``True`` when the air-gap guard should be active."""

    return parse_env_bool(os.getenv(AIRGAP_ENV_VAR), default=default)


def _load_allowlist() -> set[str]:
    value = os.getenv(AIRGAP_ALLOWLIST_ENV_VAR)
    if not value:
        return set()
    entries = {item.strip().lower() for item in value.split(",") if item.strip()}
    return entries


def _is_host_allowlisted(host: str, allowlist: Iterable[str]) -> bool:
    target = host.lower()
    for entry in allowlist:
        if entry.startswith("*."):
            suffix = entry[1:]
            if target.endswith(suffix):
                return True
        elif target == entry:
            return True
    return False


def _is_loopback_host(host: str) -> bool:
    cleaned = host.strip().lower().strip("[]")
    if cleaned in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        address = ipaddress.ip_address(cleaned)
    except ValueError:
        return False
    return address.is_loopback


def _extract_host(url: Any) -> str | None:
    if url is None:
        return None
    # httpx.URL exposes host attribute
    if hasattr(url, "host"):
        host = url.host
        return host.lower() if host else None
    parsed = urlparse(str(url))
    if not parsed.scheme:
        return None
    host = parsed.hostname
    return host.lower() if host else None


def ensure_outbound_url_allowed(url: Any) -> None:
    """Raise ``AirgapViolation`` if the provided URL violates the air-gap policy."""

    if not is_airgap_enabled():
        return

    host = _extract_host(url)
    if host is None:
        return

    if _is_loopback_host(host):
        return

    allowlist = _load_allowlist()
    if _is_host_allowlisted(host, allowlist):
        return

    raise AirgapViolation(f"Outbound network access to '{host}' is blocked by AIRGAP policy.")


def _guard_httpx_function(
    func: Callable[..., Any],
    *,
    has_method_argument: bool,
    client_offset: int = 0,
    is_async: bool = False,
) -> Callable[..., Any]:
    if is_async:

        @wraps(func)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            url = _select_url_argument(args, kwargs, has_method_argument, client_offset)
            ensure_outbound_url_allowed(url)
            return await func(*args, **kwargs)

        return _async_wrapper

    @wraps(func)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        url = _select_url_argument(args, kwargs, has_method_argument, client_offset)
        ensure_outbound_url_allowed(url)
        return func(*args, **kwargs)

    return _wrapper


def _select_url_argument(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    has_method_argument: bool,
    client_offset: int,
) -> Any:
    index = client_offset + (1 if has_method_argument else 0)
    if len(args) > index:
        return args[index]
    return kwargs.get("url")


def enforce_airgap_guard() -> None:
    """Patch httpx helpers so non-loopback destinations are rejected."""

    global _httpx_guard_active, _httpx_client_request_original, _httpx_async_client_request_original

    if not is_airgap_enabled():
        disable_airgap_guard()
        return

    with _httpx_guard_lock:
        if _httpx_guard_active:
            return

        _httpx_original_functions.clear()

        # Module-level helpers
        targets = {
            "request": (True, 0),
            "get": (False, 0),
            "post": (False, 0),
            "put": (False, 0),
            "patch": (False, 0),
            "delete": (False, 0),
            "head": (False, 0),
            "options": (False, 0),
            "stream": (True, 0),
        }

        for name, (has_method, client_offset) in targets.items():
            func = getattr(httpx, name, None)
            if func is None:
                continue
            _httpx_original_functions[name] = func
            wrapped = _guard_httpx_function(
                func, has_method_argument=has_method, client_offset=client_offset
            )
            setattr(httpx, name, wrapped)

        # Client.request
        if hasattr(httpx, "Client"):
            _httpx_client_request_original = httpx.Client.request
            httpx.Client.request = _guard_httpx_function(  # type: ignore[method-assign]
                httpx.Client.request,
                has_method_argument=True,
                client_offset=1,
            )

        # AsyncClient.request
        if hasattr(httpx, "AsyncClient"):
            _httpx_async_client_request_original = httpx.AsyncClient.request
            httpx.AsyncClient.request = _guard_httpx_function(  # type: ignore[method-assign]
                httpx.AsyncClient.request,
                has_method_argument=True,
                client_offset=1,
                is_async=True,
            )

        _httpx_guard_active = True


def disable_airgap_guard() -> None:
    """Restore original httpx helpers (primarily for tests)."""

    global _httpx_guard_active, _httpx_client_request_original, _httpx_async_client_request_original

    with _httpx_guard_lock:
        if not _httpx_guard_active:
            return

        for name, func in _httpx_original_functions.items():
            setattr(httpx, name, func)
        _httpx_original_functions.clear()

        if _httpx_client_request_original is not None:
            httpx.Client.request = _httpx_client_request_original  # type: ignore[method-assign]
            _httpx_client_request_original = None

        if _httpx_async_client_request_original is not None:
            httpx.AsyncClient.request = _httpx_async_client_request_original  # type: ignore[method-assign]
            _httpx_async_client_request_original = None

        _httpx_guard_active = False


def get_model_mount_path() -> Path:
    """Return the configured model mount path (default ``/models``)."""

    for env_var in MODEL_MOUNT_ENV_VARS:
        value = os.getenv(env_var)
        if value:
            return Path(value).expanduser().resolve()
    return DEFAULT_MODEL_MOUNT_PATH


def ensure_model_mount_path(*, create: bool = False) -> Path:
    """Ensure the model mount directory exists when requested and return it."""

    path = get_model_mount_path()
    if create and not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    return path


ALLOWED_BASE_IMAGE_PREFIXES = (
    # Node and Python pinned images (allow any tag, but prefer slim/alpine)
    "node:",
    "python:",
    # Java
    "eclipse-temurin:",
    "maven:",
)

DOCKER_INSTRUCTION_ALLOWLIST = (
    "ADD",
    "ARG",
    "CMD",
    "COPY",
    "ENTRYPOINT",
    "ENV",
    "EXPOSE",
    "FROM",
    "HEALTHCHECK",
    "LABEL",
    "RUN",
    "SHELL",
    "USER",
    "WORKDIR",
)

DISALLOWED_DOCKER_TOKENS = (
    "FROM",
    "RUN",
    "COPY",
    "ADD",
    "CMD",
    "ENTRYPOINT",
    "ENV",
    "WORKDIR",
    "EXPOSE",
    "USER",
    "LABEL",
)


@dataclass(slots=True)
class PolicyViolation:
    message: str
    stage_index: int | None = None


class SecurityPolicyError(RuntimeError):
    def __init__(self, violations: list[PolicyViolation]):
        self.violations = violations
        detail = "; ".join(v.message for v in violations) or "policy violation"
        super().__init__(f"Security gates failed: {detail}")


def _check_allowed_bases(document: DockerfileDocument) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    for idx, stage in enumerate(document.stages):
        if not stage.base_image:
            continue
        base = stage.base_image.lower()
        if not base.startswith(ALLOWED_BASE_IMAGE_PREFIXES):
            violations.append(
                PolicyViolation(
                    message=(
                        f"Disallowed base image '{stage.base_image}'. Allowed prefixes:"
                        f" {', '.join(ALLOWED_BASE_IMAGE_PREFIXES)}"
                    ),
                    stage_index=idx,
                )
            )
    return violations


def _check_disallowed_instructions(document: DockerfileDocument) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    for idx, stage in enumerate(document.stages):
        for instr in stage.instructions:
            upper = instr.keyword.upper()
            args_lower = instr.arguments.lower()

            if upper == "ADD" and ("http://" in args_lower or "https://" in args_lower):
                violations.append(
                    PolicyViolation(
                        message="Disallowed ADD from URL; use COPY and bind mounts instead.",
                        stage_index=idx,
                    )
                )

            if "--privileged" in args_lower:
                violations.append(
                    PolicyViolation(
                        message="Use of --privileged is forbidden in Dockerfiles.",
                        stage_index=idx,
                    )
                )

            if upper == "RUN" and "sudo" in args_lower:
                violations.append(
                    PolicyViolation(
                        message="Avoid sudo in containers; use USER and package managers with proper permissions.",
                        stage_index=idx,
                    )
                )

    return violations


def _check_user_root(document: DockerfileDocument) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    for idx, stage in enumerate(document.stages):
        for instr in stage.instructions:
            if instr.keyword.upper() == "USER" and instr.arguments.strip().lower() == "root":
                violations.append(
                    PolicyViolation(
                        message="Container should not run as root; choose a non-root USER.",
                        stage_index=idx,
                    )
                )
    return violations


def evaluate_policy(document: DockerfileDocument) -> list[PolicyViolation]:
    """Return a list of policy violations for the provided Dockerfile document."""
    violations: list[PolicyViolation] = []
    violations.extend(_check_allowed_bases(document))
    violations.extend(_check_disallowed_instructions(document))
    violations.extend(_check_user_root(document))
    return violations


def validate_or_raise(document: DockerfileDocument) -> None:
    """Raise SecurityPolicyError if any gate is violated."""
    violations = evaluate_policy(document)
    if violations:
        raise SecurityPolicyError(violations)


def ensure_instruction_allowlist(
    instructions: Iterable[str],
    *,
    allowlist: Iterable[str] | None = None,
) -> None:
    """Ensure the provided Docker instructions start with an allowed token.

    Args:
        instructions: Sequence of instruction strings (e.g. ``RUN npm ci``).
        allowlist: Optional iterable overriding the default instruction tokens.

    Raises:
        ValueError: If any entry is non-string or begins with a disallowed token.
    """

    if allowlist is None:
        allowed = {token.upper() for token in DOCKER_INSTRUCTION_ALLOWLIST}
    else:
        allowed = {str(token).upper() for token in allowlist}

    violations: list[str] = []
    for entry in instructions:
        if not isinstance(entry, str):
            raise ValueError("Instruction guardrails must contain string entries.")
        cleaned = entry.strip()
        if not cleaned:
            continue
        token = cleaned.split(maxsplit=1)[0].upper()
        if token not in allowed:
            violations.append(token)

    if violations:
        joined = ", ".join(sorted(set(violations)))
        raise ValueError(
            f"Promotion guardrails reference unsupported Docker instructions: {joined}"
        )


def scrub_docker_tokens(text: str, *, disallowed: Iterable[str] | None = None) -> str:
    """Remove Docker instruction tokens from free-form text.

    Args:
        text: Input text potentially containing Docker keywords.
        disallowed: Optional iterable of tokens to remove (defaults to Docker instructions).

    Returns:
        Sanitised text with disallowed tokens stripped out.
    """

    if not text:
        return ""

    blocked = {token.upper() for token in (disallowed or DISALLOWED_DOCKER_TOKENS)}
    cleaned_words: list[str] = []

    for raw in text.split():
        candidate = raw.strip(",.;:").upper()
        if candidate in blocked:
            continue
        cleaned_words.append(raw)

    return " ".join(cleaned_words).strip()
