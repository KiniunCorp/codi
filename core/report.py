"""Human-friendly reporting for CODI optimisation runs.

This module consumes the structured artefacts emitted by the build runner and
produces Markdown and HTML summaries containing metrics tables, candidate
analysis, rationale excerpts, and unified diffs. Reports are written under the
``reports/`` directory inside an existing run folder.
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = ["ReportArtefacts", "ReportGenerationError", "generate_report"]


class ReportGenerationError(RuntimeError):
    """Raised when a report cannot be produced for the supplied run."""


@dataclass(slots=True)
class VariantMetrics:
    size_bytes: int
    layers: int
    build_seconds: float


@dataclass(slots=True)
class OriginalVariant:
    path: Path
    metrics: VariantMetrics
    content: str


@dataclass(slots=True)
class CandidateVariant:
    rule_id: str
    name: str | None
    description: str | None
    path: Path
    metrics: VariantMetrics
    rationale: Sequence[str]
    policy_notes: Sequence[str]
    diff: str


@dataclass(slots=True)
class ReportContext:
    run_id: str
    created_at: datetime
    stack: str
    mode: str
    project_root: str
    detection: dict[str, Any]
    original: OriginalVariant
    candidates: Sequence[CandidateVariant]
    assist_summary: str | None = None
    assist_recommendation: dict[str, Any] | None = None
    environment: dict[str, Any] | None = None
    cmd_analysis: dict[str, Any] | None = None
    cmd_runtime: dict[str, Any] | None = None
    llm_section: LLMReportSection | None = None


@dataclass(slots=True)
class LLMReportSection:
    ranking: Sequence[dict[str, Any]]
    rationale: str | None
    adapter_version: str | None
    metrics: dict[str, Any] | None


@dataclass(slots=True)
class ReportArtefacts:
    """Paths to the generated report artefacts."""

    markdown_path: Path
    html_path: Path


def generate_report(run_dir: Path) -> ReportArtefacts:
    """Render Markdown and HTML reports for a CODI run directory.

    Args:
        run_dir: Path to a run folder produced by :class:`core.build.BuildRunner`.

    Returns:
        :class:`ReportArtefacts` with the filesystem locations of the generated
        Markdown and HTML files.

    Raises:
        ReportGenerationError: If the required metadata files are missing or
            malformed.
    """

    resolved_dir = run_dir.expanduser().resolve()
    metadata_path = resolved_dir / "metadata" / "run.json"
    if not metadata_path.exists():
        raise ReportGenerationError(
            f"Run directory {resolved_dir} does not contain metadata/run.json"
        )

    try:
        summary = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
        raise ReportGenerationError(f"Unable to parse run summary: {exc}") from exc

    context = _build_context(summary, resolved_dir)

    reports_dir = resolved_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    markdown_content = _render_markdown(context)
    html_content = _render_html(context, markdown_content)

    markdown_path = reports_dir / "report.md"
    html_path = reports_dir / "report.html"

    markdown_path.write_text(markdown_content, encoding="utf-8")
    html_path.write_text(html_content, encoding="utf-8")

    return ReportArtefacts(markdown_path=markdown_path, html_path=html_path)


# ---------------------------------------------------------------------------
# Context loading helpers
# ---------------------------------------------------------------------------


def _build_context(summary: dict[str, Any], run_dir: Path) -> ReportContext:
    run_id = _require_key(summary, "run_id")
    stack = _require_key(summary, "stack")
    mode = _require_key(summary, "mode")
    project_root = summary.get("project_root", "<unknown>")
    detection = summary.get("detection", {})

    created_at_raw = summary.get("created_at")
    created_at = (
        _parse_timestamp(created_at_raw) if isinstance(created_at_raw, str) else datetime.now(UTC)
    )

    original_summary = _require_key(summary, "original")
    original_variant = _load_original(original_summary, run_dir)

    candidate_summaries = summary.get("candidates") or []
    candidates = [
        _load_candidate(summary, run_dir, original_variant.content)
        for summary in candidate_summaries
    ]

    if not candidates:
        raise ReportGenerationError("Run does not contain any candidate results to report on.")

    cmd_analysis: dict[str, Any] | None = None
    cmd_runtime: dict[str, Any] | None = None
    cmd_summary = summary.get("cmd")
    if isinstance(cmd_summary, dict):
        maybe_analysis = cmd_summary.get("analysis")
        if isinstance(maybe_analysis, dict):
            cmd_analysis = maybe_analysis
        maybe_runtime = cmd_summary.get("runtime")
        if isinstance(maybe_runtime, dict):
            cmd_runtime = maybe_runtime

    analysis_detail = summary.get("analysis")
    if cmd_analysis is None and isinstance(analysis_detail, dict):
        fallback = analysis_detail.get("cmd_analysis")
        if isinstance(fallback, dict):
            cmd_analysis = fallback

    assist_payload = summary.get("assist") if isinstance(summary, dict) else None
    assist_summary: str | None = None
    assist_recommendation: dict[str, Any] | None = None
    if isinstance(assist_payload, dict):
        raw_summary = assist_payload.get("summary")
        if isinstance(raw_summary, str) and raw_summary.strip():
            assist_summary = raw_summary.strip()
        raw_recommendation = assist_payload.get("recommendation")
        if isinstance(raw_recommendation, dict) and raw_recommendation:
            assist_recommendation = raw_recommendation

    environment = summary.get("environment") if isinstance(summary, dict) else None

    llm_section = _build_llm_section(summary.get("llm") if isinstance(summary, dict) else None)

    return ReportContext(
        run_id=run_id,
        created_at=created_at,
        stack=stack,
        mode=mode,
        project_root=project_root,
        detection=detection,
        original=original_variant,
        candidates=candidates,
        assist_summary=assist_summary,
        assist_recommendation=assist_recommendation,
        environment=environment if isinstance(environment, dict) else None,
        cmd_analysis=cmd_analysis,
        cmd_runtime=cmd_runtime,
        llm_section=llm_section,
    )


def _build_llm_section(payload: Any) -> LLMReportSection | None:
    if not isinstance(payload, dict):
        return None

    ranking_payload = payload.get("ranking")
    if isinstance(ranking_payload, list):
        ranking = tuple(entry for entry in ranking_payload if isinstance(entry, dict))
    else:
        ranking = ()

    rationale = payload.get("rationale")
    adapter_version = payload.get("adapter_version")
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else None

    if not (ranking or rationale or adapter_version or metrics):
        return None

    return LLMReportSection(
        ranking=ranking,
        rationale=rationale if isinstance(rationale, str) else None,
        adapter_version=adapter_version if isinstance(adapter_version, str) else None,
        metrics=metrics,
    )


def _require_key(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise ReportGenerationError(f"Run summary missing required key: {key}")
    return payload[key]


def _parse_timestamp(value: str) -> datetime:
    try:
        dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
        return dt.replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def _load_original(summary: dict[str, Any], run_dir: Path) -> OriginalVariant:
    metrics = _extract_metrics(summary.get("metrics"))
    raw_path = summary.get("dockerfile_path")
    if not raw_path:
        raise ReportGenerationError("Original variant missing dockerfile path")
    path = _resolve_within_run(raw_path, run_dir)
    if not path.exists():
        raise ReportGenerationError(f"Original Dockerfile not found: {path}")
    content = path.read_text(encoding="utf-8")
    return OriginalVariant(path=path, metrics=metrics, content=content)


def _load_candidate(
    summary: dict[str, Any], run_dir: Path, original_content: str
) -> CandidateVariant:
    metrics = _extract_metrics(summary.get("metrics"))
    rule_id = summary.get("rule_id", "<unknown>")
    raw_path = summary.get("dockerfile_path")
    if not raw_path:
        raise ReportGenerationError(f"Candidate {rule_id} missing dockerfile path")
    path = _resolve_within_run(raw_path, run_dir)
    if not path.exists():
        raise ReportGenerationError(f"Candidate Dockerfile not found: {path}")
    content = path.read_text(encoding="utf-8")
    diff_text = _make_diff(original_content, content, from_label="original", to_label=path.name)

    return CandidateVariant(
        rule_id=rule_id,
        name=summary.get("name"),
        description=summary.get("description"),
        path=path,
        metrics=metrics,
        rationale=tuple(summary.get("rationale") or ()),
        policy_notes=tuple(summary.get("policy_notes") or ()),
        diff=diff_text,
    )


def _extract_metrics(payload: dict[str, Any] | None) -> VariantMetrics:
    if not payload:
        raise ReportGenerationError("Metrics payload is missing")
    try:
        size_bytes = int(payload["size_bytes"])
        layers = int(payload["layers"])
        build_seconds = float(payload["build_seconds"])
    except (KeyError, TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
        raise ReportGenerationError(f"Invalid metrics payload: {payload}") from exc
    return VariantMetrics(size_bytes=size_bytes, layers=layers, build_seconds=build_seconds)


def _resolve_within_run(path_value: str, run_dir: Path) -> Path:
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = run_dir / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(run_dir)
    except ValueError:  # pragma: no cover - security guard
        raise ReportGenerationError(f"Path escapes run directory: {resolved}") from None
    return resolved


def _make_diff(original: str, candidate: str, *, from_label: str, to_label: str) -> str:
    original_lines = _split_lines(original)
    candidate_lines = _split_lines(candidate)
    diff = difflib.unified_diff(
        original_lines,
        candidate_lines,
        fromfile=from_label,
        tofile=to_label,
        lineterm="",
    )
    diff_output = "\n".join(diff)
    return diff_output or "No differences detected."


def _split_lines(text: str) -> list[str]:
    return text.splitlines()


# ---------------------------------------------------------------------------
# Markdown & HTML rendering
# ---------------------------------------------------------------------------


def _render_markdown(context: ReportContext) -> str:
    header = [
        "# CODI Optimisation Report",
        "",
        f"- **Run ID:** {context.run_id}",
        f"- **Generated:** {context.created_at.isoformat()}",
        f"- **Stack:** {context.stack}",
        f"- **Mode:** {context.mode}",
        f"- **Project root:** `{context.project_root}`",
        "",
    ]

    header.append("## Summary Metrics")
    header.append(_build_metrics_table(context))
    header.append("")

    detection_rows = _flatten_detection(context.detection)
    if detection_rows:
        header.append("## Detection Signals")
        for item in detection_rows:
            header.append(f"- {item}")
        header.append("")

    if context.environment:
        header.append("## Environment Configuration")
        header.extend(_format_environment_markdown(context.environment))
        header.append("")

    if context.cmd_analysis or context.cmd_runtime:
        header.extend(_render_cmd_section_markdown(context.cmd_analysis, context.cmd_runtime))

    if context.assist_summary:
        header.append("## LLM Assist")
        header.append(context.assist_summary)
        recommendation = context.assist_recommendation
        if recommendation:
            rule_id = recommendation.get("rule_id")
            reason = recommendation.get("reason")
            confidence = recommendation.get("confidence")
            source = recommendation.get("source")
            line = "- Recommended template:"
            if rule_id:
                line += f" `{rule_id}`"
            if reason:
                separator = " ?" if rule_id else ""
                line += f"{separator} {reason}"
            if confidence is not None:
                try:
                    conf_float = float(confidence)
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    conf_float = None
                if conf_float is not None:
                    line += f" (confidence {conf_float:.2f})"
            if source:
                line += f" [{source}]"
            header.append(line)
        header.append("")

    if context.llm_section:
        header.extend(_render_llm_section_markdown(context))

    sections: list[str] = header

    for index, candidate in enumerate(context.candidates, start=1):
        sections.extend(_render_candidate_section(index, candidate, context.original))

    return "\n".join(sections).strip() + "\n"


def _build_metrics_table(context: ReportContext) -> str:
    rows = [
        "Variant | Layers | Size (MB) | ? Size | Build (s) | ? Time",
        "---|---:|---:|---:|---:|---:",
    ]

    orig = context.original.metrics
    rows.append(
        f"Original | {orig.layers} | {_bytes_to_mb(orig.size_bytes):.1f} | ? | {orig.build_seconds:.2f} | ?"
    )

    for candidate in context.candidates:
        metrics = candidate.metrics
        rows.append(
            "{label} | {layers} | {size:.1f} | {delta_size} | {seconds:.2f} | {delta_time}".format(
                label=_candidate_label(candidate),
                layers=metrics.layers,
                size=_bytes_to_mb(metrics.size_bytes),
                delta_size=_format_delta(metrics.size_bytes, orig.size_bytes, unit="MB"),
                seconds=metrics.build_seconds,
                delta_time=_format_delta(
                    metrics.build_seconds, orig.build_seconds, unit="s", decimals=2
                ),
            )
        )

    return "\n".join(rows)


def _candidate_label(candidate: CandidateVariant) -> str:
    if candidate.name:
        return f"{candidate.rule_id} ? {candidate.name}"
    return candidate.rule_id


def _render_candidate_section(
    index: int, candidate: CandidateVariant, original: OriginalVariant
) -> list[str]:
    metrics = candidate.metrics
    orig_metrics = original.metrics

    lines = [
        f"## Candidate {index}: {_candidate_label(candidate)}",
    ]
    if candidate.description:
        lines.extend([candidate.description, ""])

    lines.extend(
        [
            "**Metrics**",
            f"- Size: {_bytes_to_mb(metrics.size_bytes):.1f} MB ({_format_delta(metrics.size_bytes, orig_metrics.size_bytes, unit='MB')})",
            f"- Layers: {metrics.layers} ({_format_delta(metrics.layers, orig_metrics.layers, unit='layers', decimals=0)})",
            f"- Build time: {metrics.build_seconds:.2f} s ({_format_delta(metrics.build_seconds, orig_metrics.build_seconds, unit='s', decimals=2)})",
            "",
        ]
    )

    if candidate.rationale:
        lines.append("**Rationale**")
        for item in candidate.rationale:
            lines.append(f"- {item}")
        lines.append("")

    if candidate.policy_notes:
        lines.append("**Policy Notes**")
        for item in candidate.policy_notes:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend(
        [
            "**Diff vs original**",
            "```diff",
            candidate.diff,
            "```",
            "",
        ]
    )

    return lines


def _render_llm_section_markdown(context: ReportContext) -> list[str]:
    section = context.llm_section
    if section is None:
        return []

    lines: list[str] = ["## LLM Rationale & Ranking"]
    metadata_lines: list[str] = []
    if section.adapter_version:
        metadata_lines.append(f"- Adapter version: {section.adapter_version}")

    metrics = section.metrics or {}
    mode = metrics.get("mode")
    if mode:
        metadata_lines.append(f"- Mode: {mode}")
    candidate_count = metrics.get("candidate_count")
    if candidate_count:
        metadata_lines.append(f"- Candidates ranked: {candidate_count}")
    mean_confidence = metrics.get("mean_confidence")
    if isinstance(mean_confidence, (int, float)):
        metadata_lines.append(f"- Mean confidence: {mean_confidence:.2f}")

    if metadata_lines:
        lines.extend(metadata_lines)
        lines.append("")

    if section.rationale:
        lines.append(section.rationale.strip())
        lines.append("")

    ranking = section.ranking
    if ranking:
        lines.append("Rank | Candidate | Score | Rule")
        lines.append("---:|---|---:|---")
        for entry in ranking:
            rank = entry.get("rank", "—")
            label = _format_llm_candidate_label(entry, context)
            score_value = entry.get("score")
            score = f"{float(score_value):.2f}" if isinstance(score_value, (int, float)) else "—"
            rule_id = entry.get("rule_id", "—")
            lines.append(f"{rank} | {label} | {score} | `{rule_id}`")
        lines.append("")

    return lines


def _format_llm_candidate_label(entry: dict[str, Any], context: ReportContext) -> str:
    label = entry.get("label")
    if isinstance(label, str) and label.strip():
        return label
    candidate = _candidate_from_id(context.candidates, entry.get("candidate_id"))
    if candidate:
        return _candidate_label(candidate)
    rule_id = entry.get("rule_id")
    if isinstance(rule_id, str):
        return rule_id
    return "unknown"


def _candidate_from_id(
    candidates: Sequence[CandidateVariant],
    candidate_id: Any,
) -> CandidateVariant | None:
    if not isinstance(candidate_id, str) or not candidate_id.startswith("candidate_"):
        return None
    try:
        index = int(candidate_id.split("_", 1)[1]) - 1
    except (ValueError, IndexError):
        return None
    if 0 <= index < len(candidates):
        return candidates[index]
    return None


def _flatten_detection(detection: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for key, value in detection.items():
        rows.append(f"{key}: {value}")
    return rows


def _format_environment_markdown(environment: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    output_root = environment.get("output_root")
    if output_root:
        lines.append(f"- Output root: `{output_root}`")

    rules_path = environment.get("rules_path")
    if rules_path:
        source = environment.get("rules_source") or "default"
        lines.append(f"- Rules path: `{rules_path}` ({source})")

    airgap = environment.get("airgap") or {}
    if isinstance(airgap, dict):
        state = "enabled" if airgap.get("enabled") else "disabled"
        lines.append(f"- AIRGAP: {state}")
        allowlist = airgap.get("allowlist")
        if allowlist:
            joined = ", ".join(str(item) for item in allowlist)
            lines.append(f"  - Allowlist: {joined}")

    llm = environment.get("llm") or {}
    if isinstance(llm, dict):
        llm_state = "enabled" if llm.get("enabled") else "disabled"
        lines.append(f"- LLM assist: {llm_state}")
        endpoint = llm.get("endpoint")
        if endpoint:
            lines.append(f"  - Endpoint: {endpoint}")
        host = llm.get("host")
        port = llm.get("port")
        if host and port:
            lines.append(f"  - Host: {host}:{port}")
        model_id = llm.get("model_id")
        if model_id:
            lines.append(f"  - Model ID: {model_id}")
        max_tokens = llm.get("max_tokens")
        if isinstance(max_tokens, int):
            lines.append(f"  - Max tokens: {max_tokens}")

    if not lines:
        lines.append("- No environment metadata recorded.")

    return lines


def _render_cmd_section_markdown(
    analysis: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
) -> list[str]:
    lines: list[str] = ["## CMD/ENTRYPOINT Analysis (MVP+)"]

    if analysis:
        instruction = analysis.get("instruction")
        form = analysis.get("form")
        original = analysis.get("original")
        stage = analysis.get("stage") if isinstance(analysis.get("stage"), dict) else {}
        stage_label = stage.get("name") or (f"#{stage.get('index')}" if stage else "runtime")

        lines.extend(
            [
                "**Original Instruction**",
                f"- Instruction: {instruction or '—'}",
                f"- Form: {form or '—'}",
                f"- Stage: {stage_label}",
                f"- Source: `{original or 'n/a'}`",
            ]
        )

        parsed = analysis.get("parsed") if isinstance(analysis.get("parsed"), dict) else {}
        executable = parsed.get("executable")
        if executable:
            lines.append(f"- Executable: `{executable}`")
        argv = parsed.get("argv")
        if isinstance(argv, list) and argv:
            joined = ", ".join(str(item) for item in argv)
            lines.append(f"- argv: [{joined}]")

        flags = analysis.get("flags") if isinstance(analysis.get("flags"), dict) else {}
        if flags:
            lines.append("- Flags:")
            for key, value in sorted(flags.items()):
                lines.append(f"  - {key}: {'yes' if value else 'no'}")

        scripts = analysis.get("scripts") if isinstance(analysis.get("scripts"), list) else []
        if scripts:
            lines.append("- Script references:")
            for script in scripts:
                if not isinstance(script, dict):
                    continue
                exists = "yes" if script.get("exists") else "no"
                path = script.get("path", "?")
                lines.append(f"  - `{path}` (exists: {exists})")
                script_flags = script.get("flags") if isinstance(script.get("flags"), dict) else {}
                for flag_key, flag_val in sorted(script_flags.items()):
                    lines.append(f"    - {flag_key}: {'yes' if flag_val else 'no'}")
                warnings = (
                    script.get("warnings") if isinstance(script.get("warnings"), list) else []
                )
                for warning in warnings:
                    lines.append(f"    - Warning: {warning}")

        warnings = analysis.get("warnings") if isinstance(analysis.get("warnings"), list) else []
        if warnings:
            lines.append("- Warnings:")
            for warning in warnings:
                lines.append(f"  - {warning}")

        recommendations = (
            analysis.get("recommendations")
            if isinstance(analysis.get("recommendations"), list)
            else []
        )
        if recommendations:
            lines.append("- Recommendations:")
            for item in recommendations:
                lines.append(f"  - {item}")

        lines.append("")

    if runtime:
        lines.append("**Applied Rewrite**" if runtime.get("applied") else "**Rewrite Guidance**")
        lines.append(f"- Rewrite applied: {'yes' if runtime.get('applied') else 'no'}")
        rewrite_id = runtime.get("rewrite_id")
        if rewrite_id:
            lines.append(f"- Rewrite ID: `{rewrite_id}`")
        preferred_form = runtime.get("preferred_form")
        if preferred_form:
            lines.append(f"- Preferred form: {preferred_form}")
        runtime_instruction = runtime.get("runtime_instruction")
        if runtime_instruction:
            lines.append(f"- Runtime instruction: `{runtime_instruction}`")
        original_instruction = runtime.get("original_instruction")
        if original_instruction and original_instruction != runtime_instruction:
            lines.append(f"- Original instruction: `{original_instruction}`")
        rationale = runtime.get("rationale_comment")
        if rationale:
            lines.append(f"- Rationale: {rationale}")

        builder_promotions = runtime.get("builder_promotions")
        if isinstance(builder_promotions, list) and builder_promotions:
            lines.append("- Builder promotions:")
            for item in builder_promotions:
                lines.append(f"  - {item}")

        post_copy_steps = runtime.get("post_copy_steps")
        if isinstance(post_copy_steps, list) and post_copy_steps:
            lines.append("- Post-copy steps:")
            for item in post_copy_steps:
                lines.append(f"  - {item}")

        runtime_flags = runtime.get("flags") if isinstance(runtime.get("flags"), dict) else {}
        if runtime_flags:
            lines.append("- Runtime flags:")
            for key, value in sorted(runtime_flags.items()):
                lines.append(f"  - {key}: {'yes' if value else 'no'}")

        runtime_script_flags = (
            runtime.get("script_flags") if isinstance(runtime.get("script_flags"), dict) else {}
        )
        if runtime_script_flags:
            lines.append("- Script flags:")
            for key, value in sorted(runtime_script_flags.items()):
                lines.append(f"  - {key}: {'yes' if value else 'no'}")

        benefits = _derive_cmd_benefits(analysis, runtime)
        if benefits:
            lines.append("- Benefits:")
            for benefit in benefits:
                lines.append(f"  - {benefit}")

        lines.append("")

    if len(lines) == 1:
        lines.append("No CMD analysis metadata recorded.")
        lines.append("")

    return lines


def _render_cmd_section_html(
    analysis: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
) -> list[str]:
    lines = ["  <h2>CMD/ENTRYPOINT Analysis (MVP+)</h2>"]

    if analysis:
        instruction = (
            _escape_html(str(analysis.get("instruction"))) if analysis.get("instruction") else "—"
        )
        form = _escape_html(str(analysis.get("form"))) if analysis.get("form") else "—"
        original = (
            _escape_html(str(analysis.get("original"))) if analysis.get("original") else "n/a"
        )
        stage = analysis.get("stage") if isinstance(analysis.get("stage"), dict) else {}
        stage_label = stage.get("name") or (f"#{stage.get('index')}" if stage else "runtime")

        lines.append("  <h3>Original Instruction</h3>")
        lines.append("  <ul>")
        lines.append(f"    <li><strong>Instruction:</strong> {instruction}</li>")
        lines.append(f"    <li><strong>Form:</strong> {form}</li>")
        lines.append(f"    <li><strong>Stage:</strong> {_escape_html(str(stage_label))}</li>")
        lines.append(f"    <li><strong>Source:</strong> <code>{original}</code></li>")

        parsed = analysis.get("parsed") if isinstance(analysis.get("parsed"), dict) else {}
        executable = parsed.get("executable")
        if executable:
            lines.append(
                f"    <li><strong>Executable:</strong> <code>{_escape_html(str(executable))}</code></li>"
            )
        argv = parsed.get("argv")
        if isinstance(argv, list) and argv:
            joined = ", ".join(_escape_html(str(item)) for item in argv)
            lines.append(f"    <li><strong>argv:</strong> [{joined}]</li>")

        flags = analysis.get("flags") if isinstance(analysis.get("flags"), dict) else {}
        if flags:
            lines.append("    <li><strong>Flags:</strong><ul>")
            for key, value in sorted(flags.items()):
                lines.append(f"      <li>{_escape_html(str(key))}: {'yes' if value else 'no'}</li>")
            lines.append("    </ul></li>")

        scripts = analysis.get("scripts") if isinstance(analysis.get("scripts"), list) else []
        if scripts:
            lines.append("    <li><strong>Script references:</strong><ul>")
            for script in scripts:
                if not isinstance(script, dict):
                    continue
                exists = "yes" if script.get("exists") else "no"
                path = _escape_html(str(script.get("path", "?")))
                lines.append(f"      <li><code>{path}</code> (exists: {exists})")
                script_flags = script.get("flags") if isinstance(script.get("flags"), dict) else {}
                if script_flags:
                    lines.append("        <ul>")
                    for flag_key, flag_val in sorted(script_flags.items()):
                        lines.append(
                            f"          <li>{_escape_html(str(flag_key))}: {'yes' if flag_val else 'no'}</li>"
                        )
                    lines.append("        </ul>")
                warnings = (
                    script.get("warnings") if isinstance(script.get("warnings"), list) else []
                )
                if warnings:
                    lines.append("        <ul>")
                    for warning in warnings:
                        lines.append(f"          <li>Warning: {_escape_html(str(warning))}</li>")
                    lines.append("        </ul>")
                lines.append("      </li>")
            lines.append("    </ul></li>")

        warnings = analysis.get("warnings") if isinstance(analysis.get("warnings"), list) else []
        if warnings:
            lines.append("    <li><strong>Warnings:</strong><ul>")
            for warning in warnings:
                lines.append(f"      <li>{_escape_html(str(warning))}</li>")
            lines.append("    </ul></li>")

        recommendations = (
            analysis.get("recommendations")
            if isinstance(analysis.get("recommendations"), list)
            else []
        )
        if recommendations:
            lines.append("    <li><strong>Recommendations:</strong><ul>")
            for message in recommendations:
                lines.append(f"      <li>{_escape_html(str(message))}</li>")
            lines.append("    </ul></li>")

        lines.append("  </ul>")

    if runtime:
        heading = "Applied Rewrite" if runtime.get("applied") else "Rewrite Guidance"
        lines.append(f"  <h3>{heading}</h3>")
        lines.append("  <ul>")
        lines.append(
            f"    <li><strong>Rewrite applied:</strong> {'yes' if runtime.get('applied') else 'no'}</li>"
        )
        rewrite_id = runtime.get("rewrite_id")
        if rewrite_id:
            lines.append(
                f"    <li><strong>Rewrite ID:</strong> <code>{_escape_html(str(rewrite_id))}</code></li>"
            )
        preferred_form = runtime.get("preferred_form")
        if preferred_form:
            lines.append(
                f"    <li><strong>Preferred form:</strong> {_escape_html(str(preferred_form))}</li>"
            )
        runtime_instruction = runtime.get("runtime_instruction")
        if runtime_instruction:
            lines.append(
                f"    <li><strong>Runtime instruction:</strong> <code>{_escape_html(str(runtime_instruction))}</code></li>"
            )
        original_instruction = runtime.get("original_instruction")
        if original_instruction and original_instruction != runtime_instruction:
            lines.append(
                f"    <li><strong>Original instruction:</strong> <code>{_escape_html(str(original_instruction))}</code></li>"
            )
        rationale = runtime.get("rationale_comment")
        if rationale:
            lines.append(f"    <li><strong>Rationale:</strong> {_escape_html(str(rationale))}</li>")

        builder_promotions = runtime.get("builder_promotions")
        if isinstance(builder_promotions, list) and builder_promotions:
            lines.append("    <li><strong>Builder promotions:</strong><ul>")
            for item in builder_promotions:
                lines.append(f"      <li>{_escape_html(str(item))}</li>")
            lines.append("    </ul></li>")

        post_copy_steps = runtime.get("post_copy_steps")
        if isinstance(post_copy_steps, list) and post_copy_steps:
            lines.append("    <li><strong>Post-copy steps:</strong><ul>")
            for item in post_copy_steps:
                lines.append(f"      <li>{_escape_html(str(item))}</li>")
            lines.append("    </ul></li>")

        runtime_flags = runtime.get("flags") if isinstance(runtime.get("flags"), dict) else {}
        if runtime_flags:
            lines.append("    <li><strong>Runtime flags:</strong><ul>")
            for key, value in sorted(runtime_flags.items()):
                lines.append(f"      <li>{_escape_html(str(key))}: {'yes' if value else 'no'}</li>")
            lines.append("    </ul></li>")

        runtime_script_flags = (
            runtime.get("script_flags") if isinstance(runtime.get("script_flags"), dict) else {}
        )
        if runtime_script_flags:
            lines.append("    <li><strong>Script flags:</strong><ul>")
            for key, value in sorted(runtime_script_flags.items()):
                lines.append(f"      <li>{_escape_html(str(key))}: {'yes' if value else 'no'}</li>")
            lines.append("    </ul></li>")

        benefits = _derive_cmd_benefits(analysis, runtime)
        if benefits:
            lines.append("    <li><strong>Benefits:</strong><ul>")
            for benefit in benefits:
                lines.append(f"      <li>{_escape_html(str(benefit))}</li>")
            lines.append("    </ul></li>")

        lines.append("  </ul>")

    if len(lines) == 1:
        lines.append("  <p>No CMD analysis metadata recorded.</p>")

    return lines


def _derive_cmd_benefits(
    analysis: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
) -> list[str]:
    if not analysis or not runtime:
        return []

    benefits: list[str] = []
    flags = analysis.get("flags") if isinstance(analysis.get("flags"), dict) else {}
    builder_promotions = (
        runtime.get("builder_promotions")
        if isinstance(runtime.get("builder_promotions"), list)
        else []
    )
    preferred_form = runtime.get("preferred_form")

    if flags.get("uses_shell_form") and preferred_form == "exec" and runtime.get("applied"):
        benefits.append(
            "Converted shell-form runtime command to exec-form for improved signal handling."
        )

    if flags.get("installs_packages") and builder_promotions:
        benefits.append("Promoted runtime package installations into build-stage steps.")

    if flags.get("runs_migrations") and builder_promotions:
        benefits.append("Highlighted database migration commands for build-time execution.")

    script_flags = (
        runtime.get("script_flags") if isinstance(runtime.get("script_flags"), dict) else {}
    )
    if flags.get("missing_script") and not script_flags.get("missing_script", False):
        benefits.append("Surfaced missing script references for remediation in source control.")

    return benefits


def _bytes_to_mb(size_bytes: int) -> float:
    return size_bytes / (1024 * 1024)


def _format_delta(
    current: float | int, baseline: float | int, *, unit: str, decimals: int = 1
) -> str:
    delta = float(current) - float(baseline)
    sign = "+" if delta > 0 else ""
    if unit == "MB":
        delta_value = delta / (1024 * 1024)
    else:
        delta_value = delta
    formatted = f"{sign}{delta_value:.{decimals}f} {unit}"
    if baseline:
        percent = (delta / float(baseline)) * 100
        formatted += f" ({sign}{percent:.1f}%)" if percent != 0 else " (0.0%)"
    return formatted


def _render_html(context: ReportContext, markdown_body: str) -> str:
    # HTML rendering keeps things straightforward by embedding the Markdown
    # content in <pre> for readers while also surfacing key metrics in tables.
    sections = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8" />',
        f"  <title>CODI Report ? {context.run_id}</title>",
        "  <style>body{font-family:Consolas,Menlo,monospace;background:#0f1117;color:#f1f5f9;padding:2rem;}"
        "h1,h2,h3{color:#38bdf8;} table{border-collapse:collapse;margin-bottom:1.5rem;}"
        "th,td{border:1px solid #334155;padding:0.5rem;}"
        "code,pre{background:#1e293b;padding:0.75rem;border-radius:6px;display:block;overflow:auto;}"
        "</style>",
        "</head>",
        "<body>",
        "  <h1>CODI Optimisation Report</h1>",
        f"  <p><strong>Run ID:</strong> {context.run_id}<br />"
        f"<strong>Generated:</strong> {context.created_at.isoformat()}<br />"
        f"<strong>Stack:</strong> {context.stack}<br />"
        f"<strong>Mode:</strong> {context.mode}<br />"
        f"<strong>Project root:</strong> {context.project_root}</p>",
    ]

    sections.append("  <h2>Summary Metrics</h2>")
    sections.append(_render_metrics_table_html(context))

    if context.detection:
        sections.append("  <h2>Detection Signals</h2>")
        sections.append("  <ul>")
        for key, value in context.detection.items():
            sections.append(f"    <li><strong>{key}:</strong> {value}</li>")
        sections.append("  </ul>")

    if context.environment:
        sections.extend(_render_environment_html(context.environment))

    if context.cmd_analysis or context.cmd_runtime:
        sections.extend(_render_cmd_section_html(context.cmd_analysis, context.cmd_runtime))

    if context.assist_summary:
        sections.append("  <h2>LLM Assist</h2>")
        sections.append(f"  <p>{_escape_html(context.assist_summary)}</p>")
        recommendation = context.assist_recommendation
        if recommendation:
            rule_id = recommendation.get("rule_id")
            reason = recommendation.get("reason")
            confidence = recommendation.get("confidence")
            source = recommendation.get("source")
            parts: list[str] = []
            if rule_id:
                parts.append(f"Template: <code>{_escape_html(str(rule_id))}</code>")
            if reason:
                parts.append(_escape_html(str(reason)))
            if confidence is not None:
                try:
                    conf_val = float(confidence)
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    conf_val = None
                if conf_val is not None:
                    parts.append(f"Confidence {conf_val:.2f}")
            if source:
                parts.append(f"Source {_escape_html(str(source))}")
            if parts:
                sections.append(f"  <p>{' ? '.join(parts)}</p>")

    if context.llm_section:
        sections.extend(_render_llm_section_html(context))

    for index, candidate in enumerate(context.candidates, start=1):
        label = _candidate_label(candidate)
        sections.append(f"  <h2>Candidate {index}: {label}</h2>")
        if candidate.description:
            sections.append(f"  <p>{candidate.description}</p>")

        sections.append("  <h3>Metrics</h3>")
        sections.append(_render_candidate_metrics_table_html(candidate, context.original))

        if candidate.rationale:
            sections.append("  <h3>Rationale</h3>")
            sections.append("  <ul>")
            for item in candidate.rationale:
                sections.append(f"    <li>{item}</li>")
            sections.append("  </ul>")

        if candidate.policy_notes:
            sections.append("  <h3>Policy Notes</h3>")
            sections.append("  <ul>")
            for item in candidate.policy_notes:
                sections.append(f"    <li>{item}</li>")
            sections.append("  </ul>")

        sections.append("  <h3>Diff vs original</h3>")
        sections.append("  <pre><code>")
        sections.append(_escape_html(candidate.diff))
        sections.append("  </code></pre>")

    sections.extend(
        [
            "  <hr />",
            "  <h2>Raw Markdown</h2>",
            "  <pre><code>",
            _escape_html(markdown_body),
            "  </code></pre>",
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(sections)


def _render_environment_html(environment: dict[str, Any]) -> list[str]:
    lines = ["  <h2>Environment Configuration</h2>", "  <ul>"]

    output_root = environment.get("output_root")
    if output_root:
        lines.append(f"    <li><strong>Output root:</strong> {_escape_html(str(output_root))}</li>")

    rules_path = environment.get("rules_path")
    if rules_path:
        source = environment.get("rules_source") or "default"
        lines.append(
            f"    <li><strong>Rules path:</strong> {_escape_html(str(rules_path))} ({_escape_html(str(source))})</li>"
        )

    airgap = environment.get("airgap") or {}
    if isinstance(airgap, dict):
        state = "enabled" if airgap.get("enabled") else "disabled"
        lines.append(f"    <li><strong>AIRGAP:</strong> {state}</li>")
        allowlist = airgap.get("allowlist")
        if allowlist:
            joined = ", ".join(str(item) for item in allowlist)
            lines.append(f"    <li><strong>AIRGAP allowlist:</strong> {joined}</li>")

    llm = environment.get("llm") or {}
    if isinstance(llm, dict):
        llm_state = "enabled" if llm.get("enabled") else "disabled"
        lines.append(f"    <li><strong>LLM assist:</strong> {llm_state}</li>")
        endpoint = llm.get("endpoint")
        if endpoint:
            lines.append(
                f"    <li><strong>LLM endpoint:</strong> {_escape_html(str(endpoint))}</li>"
            )
        host = llm.get("host")
        port = llm.get("port")
        if host and port:
            lines.append(f"    <li><strong>LLM host:</strong> {host}:{port}</li>")
        model_id = llm.get("model_id")
        if model_id:
            lines.append(f"    <li><strong>LLM model:</strong> {_escape_html(str(model_id))}</li>")
        max_tokens = llm.get("max_tokens")
        if isinstance(max_tokens, int):
            lines.append(f"    <li><strong>LLM max tokens:</strong> {max_tokens}</li>")

    if len(lines) == 2:
        lines.append("    <li>No environment metadata recorded.</li>")

    lines.append("  </ul>")
    return lines


def _render_metrics_table_html(context: ReportContext) -> str:
    rows = [
        "  <table>",
        "    <thead>",
        "      <tr><th>Variant</th><th>Layers</th><th>Size (MB)</th><th>? Size</th><th>Build (s)</th><th>? Time</th></tr>",
        "    </thead>",
        "    <tbody>",
    ]

    orig = context.original.metrics
    rows.append(
        f"      <tr><td>Original</td><td>{orig.layers}</td><td>{_bytes_to_mb(orig.size_bytes):.1f}</td><td>?</td><td>{orig.build_seconds:.2f}</td><td>?</td></tr>"
    )

    for candidate in context.candidates:
        metrics = candidate.metrics
        rows.append(
            "      <tr><td>{label}</td><td>{layers}</td><td>{size:.1f}</td><td>{delta_size}</td><td>{seconds:.2f}</td><td>{delta_time}</td></tr>".format(
                label=_candidate_label(candidate),
                layers=metrics.layers,
                size=_bytes_to_mb(metrics.size_bytes),
                delta_size=_escape_html(
                    _format_delta(metrics.size_bytes, orig.size_bytes, unit="MB")
                ),
                seconds=metrics.build_seconds,
                delta_time=_escape_html(
                    _format_delta(metrics.build_seconds, orig.build_seconds, unit="s", decimals=2)
                ),
            )
        )

    rows.extend(["    </tbody>", "  </table>"])
    return "\n".join(rows)


def _render_candidate_metrics_table_html(
    candidate: CandidateVariant, original: OriginalVariant
) -> str:
    metrics = candidate.metrics
    orig = original.metrics
    return "\n".join(
        [
            "  <table>",
            "    <thead>",
            "      <tr><th>Metric</th><th>Candidate</th><th>? vs original</th></tr>",
            "    </thead>",
            "    <tbody>",
            "      <tr><td>Size (MB)</td><td>{size:.1f}</td><td>{delta}</td></tr>".format(
                size=_bytes_to_mb(metrics.size_bytes),
                delta=_escape_html(_format_delta(metrics.size_bytes, orig.size_bytes, unit="MB")),
            ),
            "      <tr><td>Layers</td><td>{layers}</td><td>{delta}</td></tr>".format(
                layers=metrics.layers,
                delta=_escape_html(
                    _format_delta(metrics.layers, orig.layers, unit="layers", decimals=0)
                ),
            ),
            "      <tr><td>Build time (s)</td><td>{seconds:.2f}</td><td>{delta}</td></tr>".format(
                seconds=metrics.build_seconds,
                delta=_escape_html(
                    _format_delta(metrics.build_seconds, orig.build_seconds, unit="s", decimals=2)
                ),
            ),
            "    </tbody>",
            "  </table>",
        ]
    )


def _render_llm_section_html(context: ReportContext) -> list[str]:
    section = context.llm_section
    if section is None:
        return []

    lines: list[str] = ["  <h2>LLM Rationale & Ranking</h2>"]
    meta_items: list[str] = []
    if section.adapter_version:
        meta_items.append(
            f"    <li><strong>Adapter version:</strong> {_escape_html(section.adapter_version)}</li>"
        )

    metrics = section.metrics or {}
    mode = metrics.get("mode")
    if mode:
        meta_items.append(f"    <li><strong>Mode:</strong> {_escape_html(str(mode))}</li>")
    candidate_count = metrics.get("candidate_count")
    if candidate_count:
        meta_items.append(f"    <li><strong>Candidates ranked:</strong> {candidate_count}</li>")
    mean_confidence = metrics.get("mean_confidence")
    if isinstance(mean_confidence, (int, float)):
        meta_items.append(f"    <li><strong>Mean confidence:</strong> {mean_confidence:.2f}</li>")

    if meta_items:
        lines.append("  <ul>")
        lines.extend(meta_items)
        lines.append("  </ul>")

    if section.rationale:
        lines.append(f"  <p>{_escape_html(section.rationale)}</p>")

    ranking = section.ranking
    if ranking:
        lines.extend(
            [
                "  <table>",
                "    <thead>",
                "      <tr><th>Rank</th><th>Candidate</th><th>Score</th><th>Rule</th></tr>",
                "    </thead>",
                "    <tbody>",
            ]
        )
        for entry in ranking:
            rank = entry.get("rank", "—")
            label = _escape_html(_format_llm_candidate_label(entry, context))
            score_value = entry.get("score")
            score = f"{float(score_value):.2f}" if isinstance(score_value, (int, float)) else "—"
            rule_id = entry.get("rule_id", "—")
            lines.append(
                f"      <tr><td>{rank}</td><td>{label}</td><td>{score}</td><td><code>{_escape_html(str(rule_id))}</code></td></tr>"
            )
        lines.extend(["    </tbody>", "  </table>"])

    return lines


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
