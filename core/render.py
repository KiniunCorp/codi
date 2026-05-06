"""Renderer for CODI deterministic Dockerfile templates.

The rendering stage is responsible for selecting stack-specific rules and
rendering Dockerfile candidates using Jinja2. The renderer enforces determinism
by evaluating predicates, rendering with strict variable handling, and
validating each candidate with the existing parser and security gates.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import BaseLoader, Environment, StrictUndefined, TemplateError

from .parse import DockerfileDocument, DockerfileParseError, parse_dockerfile
from .rules import (
    AllowedStack,
    CmdRewrite,
    CmdRewriteCommand,
    Rule,
    RulesCatalog,
    RulesDocument,
    load_rules,
    select_rules_for_stack,
)
from .security import SecurityPolicyError, validate_or_raise

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .cmd_parser import CmdAnalysisResult

__all__ = [
    "CandidateValidationError",
    "CmdRenderContext",
    "NoMatchingRulesError",
    "RenderContext",
    "RenderError",
    "RenderedCandidate",
    "TemplateRenderingError",
    "add_llm_rationale_comment",
    "build_cmd_runtime_summary",
    "extract_cmd_render_context",
    "render_for_stack",
]


class RenderError(RuntimeError):
    """Base class for renderer specific exceptions."""


class NoMatchingRulesError(RenderError):
    pass


class TemplateRenderingError(RenderError):
    pass


class CandidateValidationError(RenderError):
    pass


@dataclass(slots=True)
class CmdRenderContext:
    instruction: str | None
    form: str | None
    command: str | None
    argv: tuple[str, ...]
    flags: dict[str, bool]
    script_flags: dict[str, bool]
    original: str | None


@dataclass(slots=True)
class RenderContext:
    """Signals and variables used to select and render rules."""

    stack: AllowedStack
    files: set[str] = field(default_factory=set)
    lockfiles: set[str] = field(default_factory=set)
    features: set[str] = field(default_factory=set)
    variables: dict[str, Any] = field(default_factory=dict)
    cmd: CmdRenderContext | None = None
    cmd_rewrite: CmdRewrite | None = None

    def add_file(self, path: str | Path) -> None:
        self.files.add(_to_posix(path))

    def add_lockfile(self, path: str | Path) -> None:
        self.lockfiles.add(_to_posix(path))

    def add_feature(self, feature: str) -> None:
        normalized = feature.strip().lower()
        if normalized:
            self.features.add(normalized)


@dataclass(slots=True)
class RenderedCandidate:
    """Rendered Dockerfile candidate along with metadata used for reporting."""

    rule_id: str
    name: str | None
    description: str | None
    content: str
    rationale: Sequence[str]
    policy_notes: Sequence[str]
    document: DockerfileDocument


_ENV = Environment(
    loader=BaseLoader(),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
    undefined=StrictUndefined,
)


def render_for_stack(
    context: RenderContext,
    *,
    rules_doc: RulesDocument | None = None,
    limit: int | None = 2,
) -> list[RenderedCandidate]:
    """Render Dockerfile candidates for the provided context.

    Args:
        context: Signals describing the target project (stack, files, features ...).
        rules_doc: Optional pre-loaded rules document; defaults to loading the
            repository's rules file.
        limit: Maximum number of candidates to render. ``None`` renders all
            matching rules.

    Raises:
        NoMatchingRulesError: When no rules pass predicate evaluation.
        TemplateRenderingError / CandidateValidationError: For rendering issues.
    """

    if rules_doc is None:
        rules_doc = load_rules()

    catalog = RulesCatalog(rules_doc)
    if context.cmd and context.cmd_rewrite is None:
        context.cmd_rewrite = catalog.get_cmd_rewrite(
            context.stack,
            form=context.cmd.form,
            command=context.cmd.command,
            argv=context.cmd.argv,
            flags=context.cmd.flags,
            script_flags=context.cmd.script_flags,
        )

    candidates: list[RenderedCandidate] = []
    matching_rules = _find_matching_rules(rules_doc, context)

    if not matching_rules:
        raise NoMatchingRulesError(
            f"No rules matched stack {context.stack!r} given provided signals."
        )

    for rule in matching_rules:
        candidate = _render_rule(rule, context)
        candidates.append(candidate)
        if limit is not None and len(candidates) >= limit:
            break

    return candidates


def _find_matching_rules(rules_doc: RulesDocument, context: RenderContext) -> list[Rule]:
    stack_rules = select_rules_for_stack(rules_doc, context.stack)
    return [rule for rule in stack_rules if _predicates_match(rule.get("predicates"), context)]


def _predicates_match(predicates: dict[str, Any] | None, context: RenderContext) -> bool:
    if not predicates:
        return True

    files_any = _as_list(predicates.get("files_any"))
    files_all = _as_list(predicates.get("files_all"))
    lock_any = _as_list(predicates.get("lockfiles_any"))
    lock_all = _as_list(predicates.get("lockfiles_all"))
    feat_any = _normalize_simple(predicates.get("features_any"))
    feat_all = _normalize_simple(predicates.get("features_all"))

    files = {_normalize_path(f) for f in context.files}
    lockfiles = {_normalize_path(f) for f in context.lockfiles}
    features = {f.lower() for f in context.features}

    if files_any and not _any_suffix_match(files, files_any):
        return False
    if files_all and not _all_suffix_match(files, files_all):
        return False

    if lock_any and not _any_suffix_match(lockfiles, lock_any):
        return False
    if lock_all and not _all_suffix_match(lockfiles, lock_all):
        return False

    if feat_any and not (features & feat_any):
        return False
    if feat_all and not feat_all.issubset(features):
        return False

    return True


def _render_rule(rule: Rule, context: RenderContext) -> RenderedCandidate:
    template_source = rule.get("template", "")
    rule_id = rule.get("id", "<unknown>")

    try:
        template = _ENV.from_string(template_source)
        rendered = template.render(_build_template_vars(rule, context))
    except TemplateError as exc:  # pragma: no cover - exercised via unit tests
        raise TemplateRenderingError(f"Rule '{rule_id}' template rendering failed: {exc}") from exc

    normalized = _normalize_output(rendered)
    _assert_no_unrendered_tokens(normalized, rule_id)

    document = _validate_candidate(normalized, rule_id)
    rationale, policy_notes = _extract_metadata(normalized)

    return RenderedCandidate(
        rule_id=rule_id,
        name=rule.get("name"),
        description=rule.get("description"),
        content=normalized,
        rationale=rationale,
        policy_notes=policy_notes,
        document=document,
    )


def _build_template_vars(rule: Rule, context: RenderContext) -> dict[str, Any]:
    variables = {
        "stack": context.stack,
        "files": sorted(context.files),
        "lockfiles": sorted(context.lockfiles),
        "features": sorted(context.features),
        "rule": {k: v for k, v in rule.items() if k != "template"},
    }
    variables.update(context.variables)
    variables["cmd_runtime"] = _build_cmd_runtime_variables(context)
    return variables


def _build_cmd_runtime_variables(context: RenderContext) -> dict[str, Any]:
    cmd_details = context.cmd
    rewrite = context.cmd_rewrite

    runtime_instruction = _format_runtime_instruction(cmd_details, rewrite)
    rationale_comment = _build_rationale_comment(rewrite)

    flags: dict[str, bool] = {}
    script_flags: dict[str, bool] = {}
    if cmd_details:
        flags = {key: bool(value) for key, value in cmd_details.flags.items()}
        script_flags = {key: bool(value) for key, value in cmd_details.script_flags.items()}

    payload: dict[str, Any] = {
        "applied": bool(rewrite),
        "rewrite_id": rewrite.id if rewrite else None,
        "preferred_form": rewrite.preferred_form if rewrite else None,
        "builder_promotions": list(rewrite.builder_promotions) if rewrite else [],
        "post_copy_steps": list(rewrite.post_copy_steps) if rewrite else [],
        "runtime_instruction": runtime_instruction,
        "rationale_comment": rationale_comment,
        "original_instruction": cmd_details.original if cmd_details else None,
        "original_form": cmd_details.form if cmd_details else None,
        "flags": flags,
        "script_flags": script_flags,
    }

    return payload


def build_cmd_runtime_summary(context: RenderContext) -> dict[str, Any] | None:
    """Return a JSON-friendly snapshot of CMD runtime details for reporting."""

    if context.cmd is None and context.cmd_rewrite is None:
        return None

    snapshot = _build_cmd_runtime_variables(context)

    # Normalise boolean mappings for stable serialization
    flags = snapshot.get("flags")
    if isinstance(flags, dict):
        snapshot["flags"] = {key: bool(value) for key, value in sorted(flags.items())}

    script_flags = snapshot.get("script_flags")
    if isinstance(script_flags, dict):
        snapshot["script_flags"] = {key: bool(value) for key, value in sorted(script_flags.items())}

    return snapshot


def _format_runtime_instruction(
    cmd_details: CmdRenderContext | None,
    rewrite: CmdRewrite | None,
) -> str | None:
    instruction_keyword = (
        cmd_details.instruction if cmd_details and cmd_details.instruction else "CMD"
    )

    if rewrite and rewrite.runtime_cmd:
        return _format_rewrite_instruction(instruction_keyword, rewrite.runtime_cmd)

    if cmd_details:
        return _format_existing_instruction(cmd_details)

    return None


def _format_rewrite_instruction(instruction: str, runtime_cmd: CmdRewriteCommand) -> str:
    keyword = instruction or "CMD"
    if runtime_cmd.form == "shell":
        command_text = runtime_cmd.command or ""
        return f"{keyword} {command_text}".strip()

    argv_text = ", ".join(_quote_argv_token(part) for part in runtime_cmd.argv)
    return f"{keyword} [{argv_text}]"


def _format_existing_instruction(cmd_details: CmdRenderContext) -> str | None:
    keyword = cmd_details.instruction or "CMD"
    if cmd_details.form == "shell":
        if cmd_details.command:
            return f"{keyword} {cmd_details.command}".strip()
        if cmd_details.original:
            return cmd_details.original
        if cmd_details.argv:
            return f"{keyword} {' '.join(cmd_details.argv)}"
        return None

    if cmd_details.argv:
        argv_text = ", ".join(_quote_argv_token(part) for part in cmd_details.argv)
        return f"{keyword} [{argv_text}]"

    return cmd_details.original


def _quote_argv_token(token: str) -> str:
    escaped = token.replace('"', '\\"')
    return f'"{escaped}"'


def _build_rationale_comment(rewrite: CmdRewrite | None) -> str | None:
    if rewrite and rewrite.rationale_template:
        rationale = rewrite.rationale_template.strip()
        if rationale:
            return f"# RATIONALE: CMD rewrite - {rationale}"
    return None


def _normalize_output(rendered: str) -> str:
    sanitized = rendered.strip()
    if not sanitized:
        raise CandidateValidationError("Rendered template produced empty output.")
    return sanitized + "\n"


def _assert_no_unrendered_tokens(candidate: str, rule_id: str) -> None:
    if "{{" in candidate or "}}" in candidate or "{%" in candidate or "%}" in candidate:
        raise CandidateValidationError(
            f"Rule '{rule_id}' rendered output still contains template tokens; check variables."
        )


def _validate_candidate(candidate: str, rule_id: str) -> DockerfileDocument:
    try:
        document = parse_dockerfile(candidate)
    except DockerfileParseError as exc:
        raise CandidateValidationError(
            f"Rule '{rule_id}' produced invalid Dockerfile syntax: {exc}"
        ) from exc

    try:
        validate_or_raise(document)
    except SecurityPolicyError as exc:  # pragma: no cover - validated via unit tests
        raise CandidateValidationError(f"Rule '{rule_id}' violates security policy: {exc}") from exc

    return document


def _extract_metadata(candidate: str) -> tuple[Sequence[str], Sequence[str]]:
    rationale: list[str] = []
    policy: list[str] = []
    for line in candidate.splitlines():
        stripped = line.strip()
        if stripped.startswith("# RATIONALE:"):
            rationale.append(stripped.split(":", 1)[1].strip())
        if stripped.startswith("# POLICY:"):
            policy.append(stripped.split(":", 1)[1].strip())
    return tuple(rationale), tuple(policy)


def add_llm_rationale_comment(
    content: str,
    *,
    rank: int,
    total: int,
    score: float | None = None,
    adapter_version: str | None = None,
    rationale: str | None = None,
) -> str:
    """Prepend a sanitized LLM rationale comment block to a rendered candidate.

    Args:
        content: Original Dockerfile candidate contents.
        rank: 1-based ranking assigned by the LLM service.
        total: Total number of candidates considered in the ranking.
        score: Optional confidence score reported by the LLM (0-1 range).
        adapter_version: Adapter version string to surface in the comment.
        rationale: Optional free-form rationale snippet sourced from the LLM.

    Returns:
        Updated candidate content with the comment block inserted. If the
        candidate already begins with an LLM comment the original content is
        returned unchanged.
    """

    stripped = content.lstrip()
    if stripped.startswith("# LLM RANK:"):
        return content

    total = max(1, total)
    header_parts = [f"# LLM RANK: #{rank}/{total}"]
    if score is not None:
        header_parts.append(f"(score {score:.2f})")
    if adapter_version:
        header_parts.append(f"[adapter {adapter_version}]")
    header_line = " ".join(part for part in header_parts if part)

    block_lines = [header_line]
    rationale_line = _sanitize_llm_rationale(rationale)
    if rationale_line:
        block_lines.append(f"# LLM NOTE: {rationale_line}")

    comment_block = "\n".join(block_lines).rstrip()
    if not comment_block.endswith("\n"):
        comment_block += "\n"

    if content.startswith("\n"):
        updated = f"{comment_block}{content.lstrip()}"
    else:
        updated = f"{comment_block}{content}"

    if not updated.endswith("\n"):
        updated += "\n"

    return updated


def _sanitize_llm_rationale(rationale: str | None, *, max_chars: int = 200) -> str:
    if not rationale:
        return ""
    disallowed = {"FROM", "RUN", "COPY", "ADD", "CMD", "ENTRYPOINT"}
    collapsed = " ".join(segment.strip() for segment in rationale.splitlines() if segment.strip())
    words: list[str] = []
    for token in collapsed.split():
        if token.upper() in disallowed:
            continue
        words.append(token)
        if len(" ".join(words)) >= max_chars:
            break
    return " ".join(words)[:max_chars].strip()


def _any_suffix_match(values: Iterable[str], patterns: Iterable[str]) -> bool:
    normalized_values = [_normalize_path(v) for v in values]
    for pattern in patterns:
        target = _normalize_path(pattern)
        for value in normalized_values:
            if value.endswith(target):
                return True
    return False


def _all_suffix_match(values: Iterable[str], patterns: Iterable[str]) -> bool:
    normalized_values = [_normalize_path(v) for v in values]
    for pattern in patterns:
        target = _normalize_path(pattern)
        if not any(value.endswith(target) for value in normalized_values):
            return False
    return True


def _normalize_simple(values: Iterable[str] | None) -> set[str]:
    if not values:
        return set()
    return {value.strip().lower() for value in values if isinstance(value, str) and value.strip()}


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (str, Path)):
        return [str(value)]
    return [str(item) for item in value]


def _normalize_path(value: str | Path) -> str:
    text = _to_posix(value)
    return text.lower()


def _to_posix(value: str | Path) -> str:
    if isinstance(value, Path):
        return value.as_posix()
    return str(value).replace("\\", "/")


def extract_cmd_render_context(
    cmd_result: CmdAnalysisResult | None,
) -> CmdRenderContext | None:
    if cmd_result is None or getattr(cmd_result, "dominant", None) is None:
        return None

    dominant = cmd_result.dominant  # type: ignore[assignment]
    parsed = getattr(dominant, "parsed", {}) or {}

    command_value = parsed.get("command") if isinstance(parsed.get("command"), str) else None
    argv_raw = parsed.get("argv")
    if isinstance(argv_raw, list):
        argv = tuple(str(item) for item in argv_raw)
    else:
        argv = ()

    flags = {key: bool(value) for key, value in getattr(dominant, "flags", {}).items()}

    script_flags: dict[str, bool] = {}
    for script in getattr(dominant, "scripts", []) or []:
        for key, value in getattr(script, "flags", {}).items():
            if bool(value):
                script_flags[key] = True

    if flags.get("missing_script"):
        script_flags.setdefault("missing_script", True)

    return CmdRenderContext(
        instruction=getattr(dominant, "instruction", None),
        form=getattr(dominant, "form", None),
        command=command_value,
        argv=argv,
        flags=flags,
        script_flags=script_flags,
        original=getattr(dominant, "original", None),
    )
