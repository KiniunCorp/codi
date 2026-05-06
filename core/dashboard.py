"""Utilities for summarising CODI run artefacts into dashboard-friendly data."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "DashboardCandidate",
    "DashboardRun",
    "StackAggregate",
    "collect_dashboard_data",
    "load_dashboard_run",
]


def _bytes_to_mb(value: int) -> float:
    return round(value / (1024 * 1024), 2)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_summary(data: dict[str, Any]) -> dict[str, Any]:
    required_keys = {"run_id", "stack", "mode", "original", "candidates"}
    if not required_keys.issubset(data):
        missing = required_keys.difference(data)
        raise ValueError(f"run.json missing required keys: {', '.join(sorted(missing))}")
    return data


def _resolve_path(value: str | None, *, run_dir: Path) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = run_dir / candidate
    if candidate.exists():
        return candidate
    return None


@dataclass(slots=True)
class DashboardCandidate:
    rule_id: str
    name: str | None
    description: str | None
    size_mb: float
    layers: int
    build_seconds: float
    size_delta_mb: float
    size_delta_pct: float
    layers_delta: int
    build_delta_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "size_mb": self.size_mb,
            "layers": self.layers,
            "build_seconds": self.build_seconds,
            "size_delta_mb": self.size_delta_mb,
            "size_delta_pct": self.size_delta_pct,
            "layers_delta": self.layers_delta,
            "build_delta_seconds": self.build_delta_seconds,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        original_size_bytes: int,
        original_layers: int,
        original_build_seconds: float,
    ) -> DashboardCandidate:
        metrics = payload.get("metrics") or {}
        size_bytes = _safe_int(metrics.get("size_bytes"))
        layers = _safe_int(metrics.get("layers"))
        build_seconds = _safe_float(metrics.get("build_seconds"))

        delta_bytes = size_bytes - original_size_bytes
        delta_mb = round(delta_bytes / (1024 * 1024), 2)
        delta_pct = 0.0
        if original_size_bytes:
            delta_pct = round((delta_bytes / original_size_bytes) * 100, 2)

        delta_layers = layers - original_layers
        delta_build = round(build_seconds - original_build_seconds, 2)

        return cls(
            rule_id=str(payload.get("rule_id") or "unknown"),
            name=payload.get("name"),
            description=payload.get("description"),
            size_mb=_bytes_to_mb(size_bytes),
            layers=layers,
            build_seconds=build_seconds,
            size_delta_mb=delta_mb,
            size_delta_pct=delta_pct,
            layers_delta=delta_layers,
            build_delta_seconds=delta_build,
        )


@dataclass(slots=True)
class DashboardRun:
    run_id: str
    stack: str
    mode: str
    project_name: str
    created_at: str
    original_size_mb: float
    original_layers: int
    original_build_seconds: float
    candidate_count: int
    best_candidate: DashboardCandidate | None
    assist_summary: str | None
    run_dir: Path
    report_markdown: Path | None
    report_html: Path | None
    airgap_enabled: bool | None = None
    llm_enabled: bool | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "stack": self.stack,
            "mode": self.mode,
            "project_name": self.project_name,
            "created_at": self.created_at,
            "original": {
                "size_mb": self.original_size_mb,
                "layers": self.original_layers,
                "build_seconds": self.original_build_seconds,
            },
            "candidate_count": self.candidate_count,
            "best_candidate": self.best_candidate.to_dict() if self.best_candidate else None,
            "assist_summary": self.assist_summary,
            "paths": {
                "run_dir": str(self.run_dir),
                "report_markdown": str(self.report_markdown) if self.report_markdown else None,
                "report_html": str(self.report_html) if self.report_html else None,
            },
            "environment": {
                "airgap_enabled": self.airgap_enabled,
                "llm_enabled": self.llm_enabled,
            },
            "tags": list(self.tags),
        }


@dataclass(slots=True)
class StackAggregate:
    stack: str
    run_count: int
    avg_size_delta_pct: float
    avg_build_delta_seconds: float
    best_run_id: str | None
    best_rule_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stack": self.stack,
            "run_count": self.run_count,
            "avg_size_delta_pct": self.avg_size_delta_pct,
            "avg_build_delta_seconds": self.avg_build_delta_seconds,
            "best_run_id": self.best_run_id,
            "best_rule_id": self.best_rule_id,
        }


def load_dashboard_run(run_dir: Path) -> DashboardRun:
    run_dir = run_dir.expanduser().resolve()
    metadata_path = run_dir / "metadata" / "run.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Run directory missing metadata: {metadata_path}")

    summary = json.loads(metadata_path.read_text(encoding="utf-8"))
    data = _extract_summary(summary)

    original_payload = data["original"]
    original_metrics = original_payload.get("metrics") or {}

    original_size_bytes = _safe_int(original_metrics.get("size_bytes"))
    original_layers = _safe_int(original_metrics.get("layers"))
    original_build_seconds = _safe_float(original_metrics.get("build_seconds"))

    candidates_payload: Iterable[dict[str, Any]] = data.get("candidates") or []
    candidates: list[DashboardCandidate] = []
    for payload in candidates_payload:
        try:
            candidate = DashboardCandidate.from_payload(
                payload,
                original_size_bytes=original_size_bytes,
                original_layers=original_layers,
                original_build_seconds=original_build_seconds,
            )
        except Exception:
            continue
        candidates.append(candidate)

    def _candidate_sort_key(item: DashboardCandidate) -> tuple[float, float]:
        # Prefer largest negative size delta (i.e. best improvement). Fallback to build delta.
        return (item.size_delta_pct, item.build_delta_seconds)

    best_candidate: DashboardCandidate | None = None
    if candidates:
        best_candidate = min(candidates, key=_candidate_sort_key)

    project_root = Path(str(data.get("project_root") or "")).name or "unknown"
    assist_payload = data.get("assist") or {}
    assist_summary: str | None = None
    if isinstance(assist_payload, dict):
        summary_text = assist_payload.get("summary")
        if isinstance(summary_text, str):
            assist_summary = summary_text.strip() or None

    environment_payload = data.get("environment") or {}
    airgap_enabled: bool | None = None
    llm_enabled: bool | None = None
    if isinstance(environment_payload, dict):
        airgap = environment_payload.get("airgap") or {}
        if isinstance(airgap, dict):
            airgap_enabled = airgap.get("enabled")
        llm = environment_payload.get("llm") or {}
        if isinstance(llm, dict):
            llm_enabled = llm.get("enabled")

    created_at = str(data.get("created_at") or data.get("run_id") or "")
    created_at = created_at.strip()
    if created_at:
        try:
            # Normalise to ISO format if run id style timestamp provided.
            parsed = datetime.strptime(created_at[:15], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
            created_at = parsed.isoformat()
        except ValueError:
            pass

    report_md = _resolve_path("reports/report.md", run_dir=run_dir)
    report_html = _resolve_path("reports/report.html", run_dir=run_dir)

    tags: list[str] = []
    if airgap_enabled:
        tags.append("airgap")
    if llm_enabled:
        tags.append("llm")

    return DashboardRun(
        run_id=str(data["run_id"]),
        stack=str(data["stack"]),
        mode=str(data["mode"]),
        project_name=project_root,
        created_at=created_at or str(data["run_id"]),
        original_size_mb=_bytes_to_mb(original_size_bytes),
        original_layers=original_layers,
        original_build_seconds=round(original_build_seconds, 2),
        candidate_count=len(candidates),
        best_candidate=best_candidate,
        assist_summary=assist_summary,
        run_dir=run_dir,
        report_markdown=report_md,
        report_html=report_html,
        airgap_enabled=airgap_enabled,
        llm_enabled=llm_enabled,
        tags=tags,
    )


def _aggregate_by_stack(runs: list[DashboardRun]) -> list[StackAggregate]:
    aggregates: dict[str, list[DashboardRun]] = {}
    for item in runs:
        aggregates.setdefault(item.stack, []).append(item)

    results: list[StackAggregate] = []
    for stack, items in sorted(aggregates.items()):
        if not items:
            continue
        delta_sum = 0.0
        build_delta_sum = 0.0
        count_with_candidates = 0
        best_run_id: str | None = None
        best_rule_id: str | None = None
        best_delta_pct: float | None = None

        for run in items:
            candidate = run.best_candidate
            if not candidate:
                continue
            count_with_candidates += 1
            delta_sum += candidate.size_delta_pct
            build_delta_sum += candidate.build_delta_seconds
            improvement = -candidate.size_delta_pct  # negative means better
            if best_delta_pct is None or improvement > best_delta_pct:
                best_delta_pct = improvement
                best_run_id = run.run_id
                best_rule_id = candidate.rule_id

        avg_delta_pct = (
            round(delta_sum / count_with_candidates, 2) if count_with_candidates else 0.0
        )
        avg_build_delta = (
            round(build_delta_sum / count_with_candidates, 2) if count_with_candidates else 0.0
        )

        results.append(
            StackAggregate(
                stack=stack,
                run_count=len(items),
                avg_size_delta_pct=avg_delta_pct,
                avg_build_delta_seconds=avg_build_delta,
                best_run_id=best_run_id,
                best_rule_id=best_rule_id,
            )
        )
    return results


def _rewrite_paths(payload: dict[str, Any], *, base: Path | None) -> dict[str, Any]:
    if base is None:
        return payload

    resolved_base = base.expanduser().resolve()

    def normalise(path_str: str | None) -> str | None:
        if not path_str:
            return None
        candidate = Path(path_str).expanduser().resolve()
        try:
            return candidate.relative_to(resolved_base).as_posix()
        except ValueError:
            rel = os.path.relpath(candidate, resolved_base)
            return Path(rel).as_posix()

    paths = payload.get("paths") or {}
    if isinstance(paths, dict):
        paths["run_dir"] = normalise(paths.get("run_dir"))
        paths["report_markdown"] = normalise(paths.get("report_markdown"))
        paths["report_html"] = normalise(paths.get("report_html"))
        payload["paths"] = paths
    return payload


def collect_dashboard_data(runs_root: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    runs_root = runs_root.expanduser().resolve()
    if not runs_root.exists():
        raise FileNotFoundError(f"Runs root does not exist: {runs_root}")

    run_summaries: list[DashboardRun] = []
    for child in sorted(runs_root.iterdir()):
        if not child.is_dir():
            continue
        metadata_dir = child / "metadata"
        if not metadata_dir.exists():
            continue
        run_json = metadata_dir / "run.json"
        if not run_json.exists():
            continue
        try:
            run_summary = load_dashboard_run(child)
        except Exception:
            continue
        run_summaries.append(run_summary)

    aggregates = _aggregate_by_stack(run_summaries)

    generated_at = datetime.now(UTC).isoformat()

    relative_base = relative_to.expanduser().resolve() if relative_to else None

    return {
        "generated_at": generated_at,
        "runs_root": str(runs_root),
        "run_count": len(run_summaries),
        "runs": [_rewrite_paths(run.to_dict(), base=relative_base) for run in run_summaries],
        "stacks": [aggregate.to_dict() for aggregate in aggregates],
    }
