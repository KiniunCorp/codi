"""Static heuristics for runtime script references in CMD/ENTRYPOINT.

The script analyzer augments :mod:`core.cmd_parser` results by scanning inline
shell commands and referenced scripts for patterns that indicate work better
suited to build stages (package installation, database migrations, long-lived
daemons). The implementation is intentionally conservative: false positives are
preferable to missing risky behaviours, but the heuristics bias towards
well-known commands to avoid noisy output.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .cmd_parser import CmdAnalysisResult, CmdInstructionDetails

__all__ = ["apply_script_heuristics"]


_PACKAGE_PATTERNS = (
    r"\bapt-get\s+install\b",
    r"\bapt\s+install\b",
    r"\bapk\s+add\b",
    r"\byum\s+install\b",
    r"\bdnf\s+install\b",
    r"\bnpm\s+(?:ci|install)\b",
    r"\byarn\s+install\b",
    r"\bpnpm\s+install\b",
    r"\bpip(?:3)?\s+install\b",
    r"\bpoetry\s+install\b",
    r"\bconda\s+install\b",
    r"\bbundle\s+install\b",
    r"\bcomposer\s+install\b",
)

_MIGRATION_PATTERNS = (
    r"\bmanage\.py\s+migrate\b",
    r"\bpython\s+manage\.py\s+migrate\b",
    r"\balembic\s+upgrade\b",
    r"\bsequelize\s+db:migrate\b",
    r"\brake\s+db:migrate\b",
    r"\bprisma\s+migrate\b",
    r"\bknex\s+migrate\b",
)

_BACKGROUND_PATTERNS = (
    r"\bnohup\b",
    r"\bsupervisord\b",
    r"\bforever\b",
)


@dataclass(slots=True)
class _AnalysisState:
    packages: bool = False
    migrations: bool = False
    background: bool = False


def apply_script_heuristics(
    result: CmdAnalysisResult | None,
    *,
    context_dir: Path | None = None,
) -> CmdAnalysisResult | None:
    """Inspect inline commands and scripts to annotate CMD analysis flags."""

    if result is None or result.dominant is None:
        return result

    instructions: list[CmdInstructionDetails] = [
        instruction
        for instruction in (result.dominant, result.cmd, result.entrypoint)
        if instruction is not None
    ]

    for instruction in instructions:
        state = _AnalysisState()
        _inspect_inline_command(instruction, state)
        _inspect_scripts(instruction, state, context_dir)

        if state.packages:
            instruction.flags["installs_packages"] = True
            if "Promote package installations to a build stage." not in instruction.recommendations:
                instruction.recommendations.append(
                    "Promote package installations to a build stage."
                )
        else:
            instruction.flags.setdefault("installs_packages", False)

        if state.migrations:
            instruction.flags["runs_migrations"] = True
        else:
            instruction.flags.setdefault("runs_migrations", False)

        if state.background:
            instruction.flags["spawns_background_process"] = True
            instruction.warnings.append(
                "Runtime command appears to start a background process; ensure it stays in foreground."
            )
        else:
            instruction.flags.setdefault("spawns_background_process", False)

        if instruction.flags.get("references_script") and not instruction.flags.get(
            "missing_script", False
        ):
            instruction.flags.setdefault("references_script", True)
        elif instruction.flags.get("references_script"):
            instruction.flags.setdefault("references_script", True)

    return result


def _inspect_inline_command(instruction: CmdInstructionDetails, state: _AnalysisState) -> None:
    command = instruction.parsed.get("command")
    argv = instruction.parsed.get("argv")

    text_segments: list[str] = []
    if isinstance(command, str) and command:
        text_segments.append(command)
    if isinstance(argv, list):
        text_segments.append(" ".join(str(item) for item in argv))

    for segment in text_segments:
        _match_patterns(segment, _PACKAGE_PATTERNS, lambda: setattr(state, "packages", True))
        _match_patterns(segment, _MIGRATION_PATTERNS, lambda: setattr(state, "migrations", True))
        _match_patterns(segment, _BACKGROUND_PATTERNS, lambda: setattr(state, "background", True))
        if segment.strip().endswith("&"):
            state.background = True


def _inspect_scripts(
    instruction: CmdInstructionDetails,
    state: _AnalysisState,
    context_dir: Path | None,
) -> None:
    for script in instruction.scripts:
        if not script.exists or not context_dir:
            continue
        absolute = (context_dir / script.resolved_path) if script.resolved_path else None
        if absolute is None:
            absolute = (context_dir / script.path).resolve()
        if not absolute.exists() or not absolute.is_file():
            continue
        try:
            content = absolute.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            script.warnings.append("Unable to read script contents for analysis.")
            continue
        script_text = content.lower()
        if _match_patterns(script_text, _PACKAGE_PATTERNS):
            script.flags["installs_packages"] = True
            state.packages = True
        if _match_patterns(script_text, _MIGRATION_PATTERNS):
            script.flags["runs_migrations"] = True
            state.migrations = True
        if _match_patterns(script_text, _BACKGROUND_PATTERNS) or any(
            line.strip().endswith("&") for line in content.splitlines()
        ):
            script.flags["spawns_background_process"] = True
            state.background = True


def _match_patterns(text: str, patterns: Iterable[str], on_match=None) -> bool:
    lowered = text.lower()
    for pattern in patterns:
        if re.search(pattern, lowered):
            if on_match:
                on_match()
            return True
    return False
