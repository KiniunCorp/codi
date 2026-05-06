from __future__ import annotations

from pathlib import Path

import pytest
from core.rules import (
    RulesCatalog,
    load_rules,
)


def test_load_rules_includes_cmd_rewrites() -> None:
    document = load_rules()

    assert document.cmd_rewrites, "Expected cmd_rewrites to be populated"
    assert "node" in document.cmd_rewrites

    node_rewrites = {rewrite.id: rewrite for rewrite in document.cmd_rewrites["node"]}
    assert "node_shell_to_exec" in node_rewrites

    rewrite = node_rewrites["node_shell_to_exec"]
    assert rewrite.preferred_form == "exec"
    assert rewrite.runtime_cmd is not None
    assert rewrite.runtime_cmd.argv == ("node", "server.js")


def test_rules_catalog_matches_cmd_rewrite() -> None:
    catalog = RulesCatalog.load()

    rewrite = catalog.get_cmd_rewrite(
        "node",
        form="shell",
        command="npm start",
        argv=["npm", "start"],
        flags={"uses_shell_form": True, "installs_packages": False},
        script_flags={},
    )

    assert rewrite is not None
    assert rewrite.id == "node_shell_to_exec"


def test_invalid_cmd_rewrite_schema_raises(tmp_path: Path) -> None:
    bad_rules = tmp_path / "rules.yml"
    bad_rules.write_text(
        """
schema_version: 1
rules:
  - id: demo
    stack: node
    template: "FROM node:20\n"
cmd_rewrites:
  node:
    - match: {}
      runtime_cmd:
        form: exec
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_rules(bad_rules)


def test_llm_promotions_are_parsed() -> None:
    document = load_rules()
    promotions = document.llm_promotions
    assert promotions, "Expected llm promotions to be populated"

    node_entries = [promo for promo in promotions if promo.rule_id == "node_nextjs_alpine_runtime"]
    assert node_entries, "Expected node promotions"
    primary = node_entries[0]
    assert primary.metrics.win_rate > 0
    assert primary.guardrails.allowed_instructions


def test_adapter_compatibility_matrix_available() -> None:
    catalog = RulesCatalog.load()
    compat = catalog.get_adapter_compatibility("qwen15b-lora-v0.1")

    assert compat, "Expected compatibility entries for qwen15b-lora-v0.1"
    assert "node_nextjs_alpine_runtime" in compat[0].compatible_rules
