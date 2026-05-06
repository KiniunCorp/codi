"""Normalization utilities for Dockerfile CMD/ENTRYPOINT instructions.

The CMD parser consumes :mod:`core.parse` metadata and produces a structured
`cmd_analysis` payload that downstream components (script analysis, rules
engine, reporting) can consume without re-tokenising Dockerfile source text.

The module focuses on lightweight, deterministic inspection:

* Differentiate shell-form (``CMD npm start``) from exec-form
  (``CMD ["npm", "start"]``) instructions.
* Record the dominant instruction (preferring ``CMD`` over ``ENTRYPOINT``) for
  the runtime stage of the Dockerfile.
* Capture script references (``./start.sh``) without executing anything, flag
  missing scripts relative to the project context, and surface inline shell
  chains for later heuristics.

It intentionally avoids any opinionated rewrites; higher-level modules decide
what to do with the structured metadata.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .parse import DockerfileDocument, DockerInstruction, DockerStage

__all__ = [
    "CmdAnalysisResult",
    "CmdInstructionDetails",
    "ScriptReference",
    "extract_cmd_analysis",
    "serialize_cmd_analysis",
]


ShellForm = Literal["shell", "exec"]

_DEFAULT_SHELL = "/bin/sh -c"
_SCRIPT_EXTENSIONS = (".sh", ".bash", ".py", ".ps1")
_SHELL_EXEC_WRAPPERS = {"/bin/sh", "sh", "bash", "/bin/bash"}


@dataclass(slots=True)
class ScriptReference:
    """Metadata describing a referenced script inside CMD/ENTRYPOINT."""

    path: str
    exists: bool
    resolved_path: str | None = None
    flags: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "exists": self.exists,
        }
        if self.resolved_path:
            payload["resolved_path"] = self.resolved_path
        if self.flags:
            payload["flags"] = dict(sorted(self.flags.items()))
        if self.warnings:
            payload["warnings"] = list(self.warnings)
        return payload


@dataclass(slots=True)
class CmdInstructionDetails:
    """Normalised representation of a single Docker runtime instruction."""

    instruction: str  # "CMD" or "ENTRYPOINT"
    form: ShellForm
    original: str
    parsed: dict[str, Any]
    scripts: list[ScriptReference]
    flags: dict[str, bool]
    warnings: list[str]
    recommendations: list[str]
    stage_name: str | None
    stage_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction": self.instruction,
            "form": self.form,
            "original": self.original,
            "parsed": self.parsed,
            "scripts": [script.to_dict() for script in self.scripts],
            "flags": dict(sorted(self.flags.items())),
            "warnings": list(self.warnings),
            "recommendations": list(self.recommendations),
            "stage": {
                "index": self.stage_index,
                "name": self.stage_name,
            },
        }


@dataclass(slots=True)
class CmdAnalysisResult:
    """Container object for CMD/ENTRYPOINT analysis."""

    dominant: CmdInstructionDetails | None
    entrypoint: CmdInstructionDetails | None
    cmd: CmdInstructionDetails | None

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - convenience wrapper
        payload: dict[str, Any] = {}
        if self.dominant:
            payload.update(self.dominant.to_dict())
        if self.cmd and self.cmd is not self.dominant:
            payload["cmd"] = self.cmd.to_dict()
        if self.entrypoint and self.entrypoint is not self.dominant:
            payload["entrypoint"] = self.entrypoint.to_dict()
        return payload


def extract_cmd_analysis(
    document: DockerfileDocument,
    *,
    context_dir: Path | None = None,
) -> CmdAnalysisResult | None:
    """Return structured CMD/ENTRYPOINT metadata for the runtime stage.

    Args:
        document: Parsed Dockerfile representation.
        context_dir: Optional project root used to resolve script references.

    Returns:
        :class:`CmdAnalysisResult` or ``None`` when neither CMD nor ENTRYPOINT
        exists in the runtime stage.
    """

    if not document.stages:
        return None

    runtime_stage = document.stages[-1]
    stage_index = len(document.stages) - 1

    last_entrypoint = _find_last_instruction(runtime_stage, "ENTRYPOINT")
    last_cmd = _find_last_instruction(runtime_stage, "CMD")

    if not last_entrypoint and not last_cmd:
        return None

    entrypoint_details = (
        _build_instruction_details(
            last_entrypoint,
            runtime_stage,
            stage_index,
            context_dir=context_dir,
        )
        if last_entrypoint
        else None
    )
    cmd_details = (
        _build_instruction_details(
            last_cmd,
            runtime_stage,
            stage_index,
            context_dir=context_dir,
        )
        if last_cmd
        else None
    )

    dominant = cmd_details or entrypoint_details
    return CmdAnalysisResult(dominant=dominant, entrypoint=entrypoint_details, cmd=cmd_details)


def serialize_cmd_analysis(result: CmdAnalysisResult | None) -> dict[str, Any] | None:
    """Convert a :class:`CmdAnalysisResult` into a JSON-serialisable payload."""

    if result is None or result.dominant is None:
        return None

    payload = result.dominant.to_dict()
    if result.cmd and result.cmd is not result.dominant:
        payload["cmd"] = result.cmd.to_dict()
    if result.entrypoint and result.entrypoint is not result.dominant:
        payload["entrypoint"] = result.entrypoint.to_dict()
    return payload


def _find_last_instruction(stage: DockerStage, keyword: str) -> DockerInstruction | None:
    keyword_upper = keyword.upper()
    for instruction in reversed(stage.instructions):
        if instruction.keyword == keyword_upper:
            return instruction
    return None


def _build_instruction_details(
    instruction: DockerInstruction,
    stage: DockerStage,
    stage_index: int,
    *,
    context_dir: Path | None,
) -> CmdInstructionDetails:
    form, parsed = _normalise_arguments(instruction.arguments)
    scripts = _discover_scripts(parsed, context_dir=context_dir)

    flags: dict[str, bool] = {
        "uses_shell_form": form == "shell",
        "uses_shell_wrapper": _detect_shell_wrapper(parsed),
        "has_inline_chain": _detect_inline_chain(parsed),
        "references_script": any(script.path for script in scripts),
        "missing_script": any(not script.exists for script in scripts),
    }
    warnings: list[str] = []
    recommendations: list[str] = []

    for script in scripts:
        if not script.exists:
            warnings.append(
                f"Referenced script '{script.path}' was not found in the project context."
            )
            script.warnings.append("Script not located in project directory.")

    if flags["uses_shell_form"] and not flags["uses_shell_wrapper"]:
        recommendations.append("Convert runtime command to exec-form for improved signal handling.")

    stage_name = stage.name
    return CmdInstructionDetails(
        instruction=instruction.keyword,
        form=form,
        original=instruction.original,
        parsed=parsed,
        scripts=scripts,
        flags=flags,
        warnings=warnings,
        recommendations=recommendations,
        stage_name=stage_name,
        stage_index=stage_index,
    )


def _normalise_arguments(arguments: str) -> tuple[ShellForm, dict[str, Any]]:
    """Return the instruction form and a structured representation."""

    stripped = arguments.strip()
    if not stripped:
        return "shell", {"command": ""}

    try:
        parsed_json = json.loads(stripped)
    except json.JSONDecodeError:
        parsed_json = None

    if isinstance(parsed_json, list):
        argv = [str(item) for item in parsed_json]
        payload: dict[str, Any] = {
            "argv": argv,
        }
        if argv:
            payload["executable"] = argv[0]
        return "exec", payload

    # Shell-form fallback
    tokens = _safe_split_shell(stripped)
    payload = {
        "command": stripped,
        "argv": tokens,
        "shell": _DEFAULT_SHELL,
    }
    if tokens:
        payload["executable"] = tokens[0]
    return "shell", payload


def _detect_shell_wrapper(parsed: dict[str, Any]) -> bool:
    argv = parsed.get("argv")
    if isinstance(argv, list) and len(argv) >= 2:
        head = str(argv[0]).strip()
        if head in _SHELL_EXEC_WRAPPERS:
            return True
        if head in {"/bin/sh", "/bin/bash"}:
            return True
    return False


def _detect_inline_chain(parsed: dict[str, Any]) -> bool:
    command = parsed.get("command")
    if isinstance(command, str):
        return bool(re.search(r"\s(?:&&|\|\||;)+\s", command))
    argv = parsed.get("argv")
    if isinstance(argv, list):
        return any(token in {"&&", "||", ";"} for token in argv)
    return False


def _safe_split_shell(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        # Fallback: split on whitespace when quoting is mismatched
        return command.split()


def _discover_scripts(
    parsed: dict[str, Any],
    *,
    context_dir: Path | None,
) -> list[ScriptReference]:
    argv = parsed.get("argv")
    scripts: list[ScriptReference] = []
    tokens: Sequence[str] = [str(item) for item in argv] if isinstance(argv, Sequence) else []

    candidate_tokens = list(_yield_candidate_script_tokens(tokens))
    seen: set[str] = set()
    for token in candidate_tokens:
        if token in seen:
            continue
        seen.add(token)
        reference = _resolve_script_reference(token, context_dir=context_dir)
        scripts.append(reference)
    return scripts


def _yield_candidate_script_tokens(tokens: Sequence[str]) -> Iterable[str]:
    for index, token in enumerate(tokens):
        normalized = token.strip()
        if not normalized:
            continue
        lower = normalized.lower()
        if lower in _SHELL_EXEC_WRAPPERS and index + 1 < len(tokens):
            yield tokens[index + 1]
            continue
        if (
            normalized.endswith(_SCRIPT_EXTENSIONS)
            or "/" in normalized
            or normalized.startswith(".")
        ):
            yield normalized


def _resolve_script_reference(token: str, *, context_dir: Path | None) -> ScriptReference:
    """Return a :class:`ScriptReference` for the provided token."""

    normalized = token.strip().strip("\"'")
    if context_dir is None:
        return ScriptReference(path=normalized, exists=False)

    root = context_dir.resolve()
    candidate = (root / normalized).resolve()

    try:
        candidate.relative_to(root)
    except ValueError:
        return ScriptReference(
            path=normalized, exists=False, warnings=["Script path escapes project root; ignored."]
        )

    exists = candidate.exists()
    relative = candidate.relative_to(root)
    return ScriptReference(path=normalized, exists=exists, resolved_path=relative.as_posix())
