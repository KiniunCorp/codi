from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Literal,
    TypedDict,
    cast,
)

import yaml

from .security import ensure_instruction_allowlist

AllowedStack = Literal["node", "python", "java"]
ShellForm = Literal["shell", "exec"]


class Rule(TypedDict, total=False):
    id: str
    stack: AllowedStack
    name: str
    description: str
    predicates: dict[str, Any]
    template: str


@dataclass(frozen=True)
class CmdRewriteCommand:
    form: ShellForm
    argv: tuple[str, ...] = field(default_factory=tuple)
    command: str | None = None

    def __post_init__(self) -> None:
        if self.form not in {"shell", "exec"}:
            raise ValueError(f"Unsupported runtime_cmd form: {self.form}")
        if self.form == "exec" and not self.argv:
            raise ValueError("runtime_cmd with form 'exec' requires a non-empty argv list")
        if self.form == "shell" and not self.command:
            raise ValueError("runtime_cmd with form 'shell' requires a command string")

    def as_dict(self) -> dict[str, Any]:  # pragma: no cover - convenience helper for future callers
        payload: dict[str, Any] = {"form": self.form}
        if self.argv:
            payload["argv"] = list(self.argv)
        if self.command:
            payload["command"] = self.command
        return payload


@dataclass(frozen=True)
class CmdRewriteMatch:
    form: ShellForm | None
    flags: dict[str, bool] = field(default_factory=dict)
    command_contains_any: tuple[str, ...] = ()
    command_contains_all: tuple[str, ...] = ()
    executable_any: tuple[str, ...] = ()
    argv_contains_any: tuple[str, ...] = ()
    argv_contains_all: tuple[str, ...] = ()
    script_flags: dict[str, bool] = field(default_factory=dict)

    def matches(
        self,
        *,
        form: ShellForm | None,
        command: str | None,
        argv: Sequence[str],
        flags: Mapping[str, bool],
        script_flags: Mapping[str, bool],
    ) -> bool:
        if self.form is not None:
            if form is None or form != self.form:
                return False

        normalised_flags = {key: bool(value) for key, value in flags.items()}
        for key, expected in self.flags.items():
            if normalised_flags.get(key, False) != expected:
                return False

        normalised_script_flags = {key: bool(value) for key, value in script_flags.items()}
        for key, expected in self.script_flags.items():
            if normalised_script_flags.get(key, False) != expected:
                return False

        command_text = (command or "").lower()
        if not command_text and argv:
            command_text = " ".join(str(part).lower() for part in argv)

        if self.command_contains_any:
            if not command_text or not any(
                part in command_text for part in self.command_contains_any
            ):
                return False

        if self.command_contains_all:
            if not command_text or not all(
                part in command_text for part in self.command_contains_all
            ):
                return False

        argv_lower = tuple(str(item).lower() for item in argv)
        if self.executable_any:
            head = argv_lower[0] if argv_lower else None
            if head is None or head not in self.executable_any:
                return False

        if self.argv_contains_any:
            if not argv_lower or not any(token in argv_lower for token in self.argv_contains_any):
                return False

        if self.argv_contains_all:
            if not argv_lower or not all(token in argv_lower for token in self.argv_contains_all):
                return False

        return True


@dataclass(frozen=True)
class CmdRewrite:
    id: str
    stack: AllowedStack
    match: CmdRewriteMatch
    preferred_form: ShellForm | None
    builder_promotions: tuple[str, ...]
    post_copy_steps: tuple[str, ...]
    runtime_cmd: CmdRewriteCommand | None
    rationale_template: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromotionGuardrails:
    allowed_instructions: tuple[str, ...]
    rationale_tags: tuple[str, ...]


@dataclass(frozen=True)
class PromotionMetrics:
    eval_run: str
    eval_report: str
    sample_size: int
    win_rate: float
    avg_size_delta_mb: float
    avg_layer_delta: float


@dataclass(frozen=True)
class LLMPromotion:
    promotion_id: str
    rule_id: str
    adapter_version: str
    promoted_at: datetime
    metrics: PromotionMetrics
    guardrails: PromotionGuardrails


@dataclass(frozen=True)
class AdapterCompatibility:
    adapter_version: str
    ruleset: str
    compatible_rules: tuple[str, ...]
    notes: str | None = None


@dataclass(frozen=True)
class RulesDocument:
    schema_version: int
    rules: list[Rule]
    cmd_rewrites: dict[AllowedStack, tuple[CmdRewrite, ...]] = field(default_factory=dict)
    cmd_schema_version: int | None = None
    llm_promotions: tuple[LLMPromotion, ...] = field(default_factory=tuple)
    adapter_compatibility: tuple[AdapterCompatibility, ...] = field(default_factory=tuple)


DEFAULT_RULES_RELATIVE_PATH = "patterns/rules.yml"
ENV_RULES_PATH = "RULES_PATH"


def get_default_rules_path() -> Path:
    """Return the default rules file path, allowing override via RULES_PATH env var."""
    env_path = os.getenv(ENV_RULES_PATH)
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parent.parent / DEFAULT_RULES_RELATIVE_PATH


def _ensure_path_exists(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"rules.yml not found at: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"rules.yml path is not a file: {path}")


def load_rules(path: str | Path | None = None) -> RulesDocument:
    """Load and validate rules.yml, returning a structured RulesDocument."""
    rules_path = Path(path) if path else get_default_rules_path()
    _ensure_path_exists(rules_path)

    with rules_path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    _validate_schema(data)

    rules: list[Rule] = data.get("rules", [])
    schema_version: int = int(data.get("schema_version", 1))
    cmd_rewrites_section = data.get("cmd_rewrites")
    cmd_schema_version: int | None = None
    cmd_rewrites: dict[AllowedStack, tuple[CmdRewrite, ...]] = {}

    if cmd_rewrites_section:
        cmd_schema_version = _extract_cmd_schema_version(cmd_rewrites_section)
        cmd_rewrites = _parse_cmd_rewrites(cmd_rewrites_section)

    llm_section = data.get("llm_assist") or {}
    promotions = _parse_llm_promotions(llm_section.get("promotions"), rules)
    compatibility = _parse_adapter_compatibility(
        (llm_section.get("compatibility_matrix") or {}).get("adapters"),
        rules,
    )

    return RulesDocument(
        schema_version=schema_version,
        rules=rules,
        cmd_rewrites=cmd_rewrites,
        cmd_schema_version=cmd_schema_version,
        llm_promotions=promotions,
        adapter_compatibility=compatibility,
    )


def _validate_schema(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("rules.yml must contain a mapping at the top level")

    if "rules" not in data:
        raise ValueError("rules.yml must contain a 'rules' list")

    rules = data["rules"]
    if not isinstance(rules, list) or not rules:
        raise ValueError("'rules' must be a non-empty list")

    allowed_stacks: set[str] = {"node", "python", "java"}
    seen_ids: set[str] = set()

    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"rule at index {idx} must be a mapping")
        rid = rule.get("id")
        if not rid or not isinstance(rid, str):
            raise ValueError(f"rule at index {idx} missing non-empty 'id'")
        if rid in seen_ids:
            raise ValueError(f"duplicate rule id: {rid}")
        seen_ids.add(rid)

        stack = rule.get("stack")
        if stack not in allowed_stacks:
            raise ValueError(
                f"rule '{rid}' has invalid stack '{stack}'. Expected one of {sorted(allowed_stacks)}"
            )

        template = rule.get("template")
        if not template or not isinstance(template, str):
            raise ValueError(f"rule '{rid}' missing 'template' string")

        # Optional checks
        if "name" in rule and not isinstance(rule["name"], str):
            raise ValueError(f"rule '{rid}' field 'name' must be a string if present")
        if "description" in rule and not isinstance(rule["description"], str):
            raise ValueError(f"rule '{rid}' field 'description' must be a string if present")
        if "predicates" in rule and not isinstance(rule["predicates"], dict):
            raise ValueError(f"rule '{rid}' field 'predicates' must be a mapping if present")

    if "cmd_rewrites" in data:
        _validate_cmd_rewrites(data["cmd_rewrites"])


def _validate_cmd_rewrites(section: Any) -> None:
    if section is None:
        return
    if not isinstance(section, dict):
        raise ValueError("'cmd_rewrites' must be a mapping keyed by stack")

    allowed_stacks: set[str] = {"node", "python", "java"}
    for key, value in section.items():
        if key == "schema_version":
            if not isinstance(value, int):
                raise ValueError("cmd_rewrites.schema_version must be an integer")
            continue

        if key not in allowed_stacks:
            raise ValueError(
                f"cmd_rewrites contains unsupported stack '{key}'. Expected one of {sorted(allowed_stacks)}"
            )
        if not isinstance(value, list):
            raise ValueError(f"cmd_rewrites['{key}'] must be a list of rewrite rules")
        for index, entry in enumerate(value):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"cmd_rewrites['{key}'][{index}] must be a mapping with 'match' and rewrite fields"
                )
            if "match" not in entry or not isinstance(entry["match"], dict):
                raise ValueError(
                    f"cmd_rewrites['{key}'][{index}] must include a 'match' mapping describing trigger conditions"
                )
            preferred_form = entry.get("preferred_form")
            if preferred_form is not None and preferred_form not in {"shell", "exec"}:
                raise ValueError(
                    f"cmd_rewrites['{key}'][{index}].preferred_form must be 'shell' or 'exec' when provided"
                )
            if "builder_promotions" in entry and not _is_list_of_strings(
                entry["builder_promotions"]
            ):
                raise ValueError(
                    f"cmd_rewrites['{key}'][{index}].builder_promotions must be a list of strings"
                )
            if "post_copy_steps" in entry and not _is_list_of_strings(entry["post_copy_steps"]):
                raise ValueError(
                    f"cmd_rewrites['{key}'][{index}].post_copy_steps must be a list of strings"
                )
            if "runtime_cmd" in entry:
                runtime_cmd = entry["runtime_cmd"]
                if not isinstance(runtime_cmd, dict):
                    raise ValueError(
                        f"cmd_rewrites['{key}'][{index}].runtime_cmd must be a mapping with 'form' plus argv/command"
                    )
                form = runtime_cmd.get("form")
                if form not in {"shell", "exec"}:
                    raise ValueError(
                        f"cmd_rewrites['{key}'][{index}].runtime_cmd.form must be 'shell' or 'exec'"
                    )
                if form == "exec" and not _is_list_of_strings(runtime_cmd.get("argv")):
                    raise ValueError(
                        f"cmd_rewrites['{key}'][{index}].runtime_cmd.argv must be a list of strings for exec form"
                    )
                if form == "shell" and not isinstance(runtime_cmd.get("command"), str):
                    raise ValueError(
                        f"cmd_rewrites['{key}'][{index}].runtime_cmd.command must be a string for shell form"
                    )


def select_rules_for_stack(rules_doc: RulesDocument, stack: AllowedStack) -> list[Rule]:
    """Return rules applicable to a given stack."""
    return [r for r in rules_doc.rules if r.get("stack") == stack]


def find_rule_by_id(rules_doc: RulesDocument, rule_id: str) -> Rule | None:
    for r in rules_doc.rules:
        if r.get("id") == rule_id:
            return r
    return None


@dataclass(frozen=True)
class RulesCatalog:
    document: RulesDocument

    @classmethod
    def load(cls, path: str | Path | None = None) -> RulesCatalog:
        return cls(load_rules(path))

    def select_rules(self, stack: AllowedStack) -> list[Rule]:
        return select_rules_for_stack(self.document, stack)

    def get_llm_promotions(self, rule_id: str | None = None) -> tuple[LLMPromotion, ...]:
        """Return recorded LLM promotions, optionally filtered by rule id."""
        promotions = self.document.llm_promotions
        if rule_id is None:
            return promotions
        return tuple(p for p in promotions if p.rule_id == rule_id)

    def get_adapter_compatibility(
        self,
        adapter_version: str | None = None,
    ) -> tuple[AdapterCompatibility, ...]:
        """Return adapter compatibility records."""
        entries = self.document.adapter_compatibility
        if adapter_version is None:
            return entries
        return tuple(entry for entry in entries if entry.adapter_version == adapter_version)

    def get_cmd_rewrite(
        self,
        stack: AllowedStack,
        *,
        form: ShellForm | None,
        command: str | None,
        argv: Sequence[str],
        flags: Mapping[str, bool],
        script_flags: Mapping[str, bool] | None = None,
    ) -> CmdRewrite | None:
        rewrites = self.document.cmd_rewrites.get(stack, ())
        script_flags = script_flags or {}

        for rewrite in rewrites:
            if rewrite.match.matches(
                form=form,
                command=command,
                argv=argv,
                flags=flags,
                script_flags=script_flags,
            ):
                return rewrite
        return None


def _extract_cmd_schema_version(section: dict[str, Any]) -> int | None:
    value = section.get("schema_version")
    return int(value) if isinstance(value, int) else None


def _parse_cmd_rewrites(section: dict[str, Any]) -> dict[AllowedStack, tuple[CmdRewrite, ...]]:
    rewrites: dict[AllowedStack, tuple[CmdRewrite, ...]] = {}
    for stack, entries in section.items():
        if stack == "schema_version":
            continue
        parsed_rules: list[CmdRewrite] = []
        for index, entry in enumerate(entries or []):
            parsed_rules.append(_parse_cmd_rewrite(stack, entry, index))
        rewrites[stack] = tuple(parsed_rules)
    return rewrites


def _parse_cmd_rewrite(stack: str, data: dict[str, Any], index: int) -> CmdRewrite:
    identifier = str(data.get("id") or f"{stack}_rewrite_{index}")
    match_data = data.get("match") or {}
    match = _parse_cmd_rewrite_match(stack, identifier, match_data)

    preferred_form: ShellForm | None = data.get("preferred_form")
    if preferred_form is not None and preferred_form not in {"shell", "exec"}:
        raise ValueError(
            f"cmd_rewrites['{stack}'][{index}].preferred_form must be 'shell' or 'exec' when provided"
        )

    builder_promotions = tuple(_ensure_string_sequence(data.get("builder_promotions", [])))
    post_copy_steps = tuple(_ensure_string_sequence(data.get("post_copy_steps", [])))

    runtime_cmd_data = data.get("runtime_cmd")
    runtime_cmd = (
        _parse_cmd_rewrite_command(stack, identifier, runtime_cmd_data)
        if runtime_cmd_data
        else None
    )

    rationale_template = data.get("rationale_template")
    if rationale_template is not None and not isinstance(rationale_template, str):
        raise ValueError(
            f"cmd_rewrites['{stack}'][{index}].rationale_template must be a string when provided"
        )

    metadata_keys = set(data.keys()) - {
        "id",
        "match",
        "preferred_form",
        "builder_promotions",
        "post_copy_steps",
        "runtime_cmd",
        "rationale_template",
    }
    metadata = {key: data[key] for key in metadata_keys}

    return CmdRewrite(
        id=identifier,
        stack=cast(AllowedStack, stack),
        match=match,
        preferred_form=preferred_form,
        builder_promotions=builder_promotions,
        post_copy_steps=post_copy_steps,
        runtime_cmd=runtime_cmd,
        rationale_template=rationale_template,
        metadata=metadata,
    )


def _parse_llm_promotions(section: Any, rules: Sequence[Rule]) -> tuple[LLMPromotion, ...]:
    if not section:
        return ()
    if not isinstance(section, list):
        raise ValueError("llm_assist.promotions must be a list")

    known_rule_ids = {rule.get("id") for rule in rules if isinstance(rule, dict)}
    parsed: list[LLMPromotion] = []

    for index, entry in enumerate(section):
        if not isinstance(entry, Mapping):
            raise ValueError(f"llm_assist.promotions[{index}] must be a mapping")

        promotion_id = str(entry.get("id") or f"promotion_{index}")
        rule_id = entry.get("rule_id")
        if rule_id not in known_rule_ids:
            raise ValueError(
                f"llm_assist.promotions[{promotion_id}] references unknown rule '{rule_id}'"
            )

        adapter_version = str(entry.get("adapter_version") or "").strip()
        if not adapter_version:
            raise ValueError(f"llm_assist.promotions[{promotion_id}] missing adapter_version")

        promoted_at_raw = entry.get("promoted_at")
        # Handle both string and datetime objects (PyYAML auto-converts ISO 8601 strings)
        if isinstance(promoted_at_raw, datetime):
            promoted_at = promoted_at_raw
        elif isinstance(promoted_at_raw, str) and promoted_at_raw.strip():
            try:
                promoted_at = datetime.fromisoformat(promoted_at_raw.strip())
            except ValueError as exc:  # pragma: no cover - invalid timestamp
                raise ValueError(
                    f"llm_assist.promotions[{promotion_id}] has invalid promoted_at timestamp"
                ) from exc
        else:
            raise ValueError(
                f"llm_assist.promotions[{promotion_id}] requires promoted_at timestamp"
            )

        metrics = _parse_promotion_metrics(entry.get("metrics"), promotion_id)
        guardrails = _parse_promotion_guardrails(entry.get("guardrails"), promotion_id)

        parsed.append(
            LLMPromotion(
                promotion_id=promotion_id,
                rule_id=str(rule_id),
                adapter_version=adapter_version,
                promoted_at=promoted_at,
                metrics=metrics,
                guardrails=guardrails,
            )
        )

    return tuple(parsed)


def _parse_promotion_metrics(data: Any, promotion_id: str) -> PromotionMetrics:
    if not isinstance(data, Mapping):
        raise ValueError(f"llm_assist.promotions[{promotion_id}].metrics must be a mapping")

    eval_run = str(data.get("eval_run") or "").strip()
    eval_report = str(data.get("eval_report") or "").strip()
    if not eval_run or not eval_report:
        raise ValueError(
            f"llm_assist.promotions[{promotion_id}] metrics must include eval_run and eval_report"
        )

    sample_size = int(data.get("sample_size") or 0)
    if sample_size <= 0:
        raise ValueError(f"llm_assist.promotions[{promotion_id}] metrics.sample_size must be > 0")

    win_rate = float(data.get("win_rate"))
    if not (0.0 <= win_rate <= 1.0):
        raise ValueError(
            f"llm_assist.promotions[{promotion_id}] metrics.win_rate must be between 0 and 1"
        )

    if "avg_size_delta_mb" not in data or "avg_layer_delta" not in data:
        raise ValueError(
            f"llm_assist.promotions[{promotion_id}] metrics require avg_size_delta_mb and avg_layer_delta"
        )

    avg_size_delta_mb = float(data["avg_size_delta_mb"])
    avg_layer_delta = float(data["avg_layer_delta"])

    return PromotionMetrics(
        eval_run=eval_run,
        eval_report=eval_report,
        sample_size=sample_size,
        win_rate=win_rate,
        avg_size_delta_mb=avg_size_delta_mb,
        avg_layer_delta=avg_layer_delta,
    )


def _parse_promotion_guardrails(data: Any, promotion_id: str) -> PromotionGuardrails:
    if not isinstance(data, Mapping):
        raise ValueError(f"llm_assist.promotions[{promotion_id}].guardrails must be a mapping")

    allowed_instructions = tuple(_ensure_string_sequence(data.get("allowed_instructions", [])))
    ensure_instruction_allowlist(allowed_instructions)

    rationale_tags = tuple(_ensure_string_sequence(data.get("rationale_tags", [])))

    return PromotionGuardrails(
        allowed_instructions=allowed_instructions,
        rationale_tags=rationale_tags,
    )


def _parse_adapter_compatibility(
    section: Any,
    rules: Sequence[Rule],
) -> tuple[AdapterCompatibility, ...]:
    if not section:
        return ()
    if not isinstance(section, list):
        raise ValueError("llm_assist.compatibility_matrix.adapters must be a list")

    known_rule_ids = {rule.get("id") for rule in rules if isinstance(rule, dict)}
    parsed: list[AdapterCompatibility] = []

    for index, entry in enumerate(section):
        if not isinstance(entry, Mapping):
            raise ValueError(f"compatibility_matrix.adapters[{index}] must be a mapping")

        adapter_version = str(entry.get("adapter_version") or "").strip()
        ruleset = str(entry.get("ruleset") or "").strip()
        if not adapter_version or not ruleset:
            raise ValueError(
                f"compatibility_matrix.adapters[{index}] requires adapter_version and ruleset"
            )

        compat_rules_raw = tuple(_ensure_string_sequence(entry.get("compatible_rules", [])))
        if not compat_rules_raw:
            raise ValueError(
                f"compatibility_matrix.adapters[{index}] must list at least one compatible rule"
            )

        for rule_id in compat_rules_raw:
            if rule_id not in known_rule_ids:
                raise ValueError(
                    f"compatibility_matrix.adapters[{index}] references unknown rule '{rule_id}'"
                )

        notes = entry.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise ValueError(
                f"compatibility_matrix.adapters[{index}].notes must be a string when provided"
            )

        parsed.append(
            AdapterCompatibility(
                adapter_version=adapter_version,
                ruleset=ruleset,
                compatible_rules=compat_rules_raw,
                notes=notes.strip() if isinstance(notes, str) else None,
            )
        )

    return tuple(parsed)


def _parse_cmd_rewrite_match(
    stack: str, identifier: str, data: Mapping[str, Any]
) -> CmdRewriteMatch:
    form_value = data.get("form")
    if form_value is not None and form_value not in {"shell", "exec"}:
        raise ValueError(
            f"cmd_rewrites['{stack}'][id='{identifier}'].match.form must be 'shell' or 'exec' when provided"
        )
    flags = _ensure_bool_mapping(data.get("flags"))
    script_flags = _ensure_bool_mapping(data.get("script_flags"))

    return CmdRewriteMatch(
        form=form_value,
        flags=flags,
        command_contains_any=_ensure_normalised_tuple(data.get("command_contains_any")),
        command_contains_all=_ensure_normalised_tuple(data.get("command_contains_all")),
        executable_any=_ensure_normalised_tuple(data.get("executable_any")),
        argv_contains_any=_ensure_normalised_tuple(data.get("argv_contains_any")),
        argv_contains_all=_ensure_normalised_tuple(data.get("argv_contains_all")),
        script_flags=script_flags,
    )


def _parse_cmd_rewrite_command(
    stack: str, identifier: str, data: Mapping[str, Any]
) -> CmdRewriteCommand:
    form = data.get("form")
    if form not in {"shell", "exec"}:
        raise ValueError(
            f"cmd_rewrites['{stack}'][id='{identifier}'].runtime_cmd.form must be 'shell' or 'exec'"
        )
    argv_values = tuple(_ensure_string_sequence(data.get("argv", [])))
    command_value = data.get("command")
    if command_value is not None and not isinstance(command_value, str):
        raise ValueError(
            f"cmd_rewrites['{stack}'][id='{identifier}'].runtime_cmd.command must be a string when provided"
        )
    return CmdRewriteCommand(form=form, argv=argv_values, command=command_value)


def _ensure_string_sequence(value: Any) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, (str, Path)):
        return [str(value)]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    raise ValueError("Expected a sequence of strings")


def _ensure_bool_mapping(value: Any) -> dict[str, bool]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("Expected a mapping of boolean values")
    result: dict[str, bool] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            raise ValueError("Flag keys must be strings")
        if not isinstance(raw, bool):
            raise ValueError("Flag values must be boolean")
        result[key] = raw
    return result


def _ensure_normalised_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, Path)):
        return (str(value).lower(),)
    if isinstance(value, Iterable):
        return tuple(str(item).lower() for item in value)
    raise ValueError("Expected string or iterable of strings")


def _is_list_of_strings(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, list):
        return False
    return all(isinstance(item, str) for item in value)


__all__ = [
    "AdapterCompatibility",
    "AllowedStack",
    "CmdRewrite",
    "CmdRewriteCommand",
    "CmdRewriteMatch",
    "LLMPromotion",
    "PromotionGuardrails",
    "PromotionMetrics",
    "Rule",
    "RulesCatalog",
    "RulesDocument",
    "ShellForm",
    "find_rule_by_id",
    "get_default_rules_path",
    "load_rules",
    "select_rules_for_stack",
]
