from __future__ import annotations

import pytest
from core.render import (
    CandidateValidationError,
    CmdRenderContext,
    NoMatchingRulesError,
    RenderContext,
    TemplateRenderingError,
    add_llm_rationale_comment,
    render_for_stack,
)
from core.rules import RulesDocument


def test_render_for_stack_selects_node_rule() -> None:
    context = RenderContext(stack="node")
    context.add_file("package.json")
    context.add_lockfile("package-lock.json")
    context.add_feature("nextjs")

    candidates = render_for_stack(context)

    # Both the generic and nextjs-specific rules match; the nextjs rule must be present.
    assert len(candidates) >= 1
    rule_ids = [c.rule_id for c in candidates]
    assert "node_nextjs_alpine_runtime" in rule_ids
    nextjs_candidate = next(c for c in candidates if c.rule_id == "node_nextjs_alpine_runtime")
    assert nextjs_candidate.document.stages[0].base_image == "node:20-slim"
    assert "# RATIONALE:" in nextjs_candidate.content
    assert nextjs_candidate.rationale, "Expected rationale metadata to be extracted"


def test_render_no_matching_rule_raises() -> None:
    context = RenderContext(stack="node")
    context.add_file("package.json")
    # Missing required features_any predicate (e.g. nextjs)

    with pytest.raises(NoMatchingRulesError):
        render_for_stack(context)


def test_render_template_variables_injection() -> None:
    rules_doc = RulesDocument(
        schema_version=1,
        rules=[
            {
                "id": "node_runtime_entry",
                "stack": "node",
                "template": (
                    "# RATIONALE: Custom entry point\n"
                    "FROM node:20\n"
                    'CMD ["node", "{{ entry_point }}"]\n'
                ),
            }
        ],
    )

    context = RenderContext(stack="node", variables={"entry_point": "server.js"})

    candidates = render_for_stack(context, rules_doc=rules_doc)
    assert len(candidates) == 1
    assert "server.js" in candidates[0].content


def test_render_missing_template_variables_raise() -> None:
    rules_doc = RulesDocument(
        schema_version=1,
        rules=[
            {
                "id": "missing_var",
                "stack": "node",
                "template": 'FROM node:20\nCMD ["node", "{{ entry_point }}"]\n',
            }
        ],
    )

    context = RenderContext(stack="node")

    with pytest.raises(TemplateRenderingError):
        render_for_stack(context, rules_doc=rules_doc)


def test_render_security_violation_is_reported() -> None:
    rules_doc = RulesDocument(
        schema_version=1,
        rules=[
            {
                "id": "bad_base",
                "stack": "node",
                "template": "FROM ubuntu:latest\nRUN echo 'hello'\n",
            }
        ],
    )

    context = RenderContext(stack="node")

    with pytest.raises(CandidateValidationError):
        render_for_stack(context, rules_doc=rules_doc)


def test_render_applies_cmd_rewrite_for_node_shell_form() -> None:
    context = RenderContext(stack="node")
    context.add_file("package.json")
    context.add_lockfile("package-lock.json")
    context.add_feature("nextjs")
    context.cmd = CmdRenderContext(
        instruction="CMD",
        form="shell",
        command="npm start",
        argv=("npm", "start"),
        flags={"uses_shell_form": True},
        script_flags={},
        original="CMD npm start",
    )

    candidates = render_for_stack(context)

    assert candidates, "Expected at least one candidate"
    # Pick the nextjs-specific candidate which applies the CMD rewrite.
    nextjs = next((c for c in candidates if c.rule_id == "node_nextjs_alpine_runtime"), None)
    assert nextjs is not None, "Expected node_nextjs_alpine_runtime candidate"
    content = nextjs.content

    assert "CMD npm start" not in content
    assert 'CMD ["node", "server.js"]' in content
    assert "# Fallback to default next start" not in content
    assert "# RATIONALE: CMD rewrite" in content


def test_add_llm_rationale_comment_is_idempotent() -> None:
    original = "FROM node:20-slim\nRUN npm install\n"
    updated = add_llm_rationale_comment(
        original,
        rank=1,
        total=2,
        score=0.82,
        adapter_version="adapter-test",
        rationale="Ranks this template highest for size savings.",
    )
    assert updated.startswith("# LLM RANK: #1/2")
    assert "adapter-test" in updated
    assert "Ranks this template" in updated
    updated_again = add_llm_rationale_comment(updated, rank=1, total=2)
    assert updated_again == updated
