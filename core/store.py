"""Utilities for managing CODI run artefacts under the ``runs/`` tree.

The store module centralises naming, directory layout, and helper functions for
persisting inputs, generated candidates, metrics, and future reports. It is
designed to be deterministic (run identifiers include UTC timestamps) and
idempotent (directories are only created once per run).

Directory layout for a single run looks like::

    runs/
      20251030T200000Z-node/
        inputs/
          Dockerfile
        candidates/
          001-node_nextjs_alpine_runtime.Dockerfile
        metadata/
          detect.json
          run.json
        logs/
        reports/

New code should access these helpers instead of manually composing paths.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "RAGIndex",
    "RAGMatch",
    "RunPaths",
    "RunStore",
    "create_run_store",
    "generate_run_id",
]


_SAFE_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str | None) -> str:
    if not value:
        return "run"
    normalized = value.lower().strip()
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SAFE_SLUG_RE.sub("-", normalized).strip("-")
    return slug or "run"


def generate_run_id(*, stack: str | None = None, label: str | None = None) -> str:
    """Return a deterministic run identifier using UTC timestamps.

    Args:
        stack: Optional technology stack name (e.g. ``node``) appended to the id.
        label: Optional arbitrary label appended after the stack slug.
    """

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    parts = [timestamp]
    if stack:
        parts.append(_slugify(stack))
    if label:
        parts.append(_slugify(label))
    return "-".join(parts)


@dataclass(frozen=True)
class RunPaths:
    """Resolved locations for all artefact sub-directories for a run."""

    root: Path
    inputs: Path
    candidates: Path
    metadata: Path
    logs: Path
    reports: Path


@dataclass
class RunStore:
    """Helper object representing a single CODI run directory."""

    paths: RunPaths
    run_id: str

    def write_text(
        self, relative_path: str | Path, content: str, *, encoding: str = "utf-8"
    ) -> Path:
        target = self.paths.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding=encoding)
        return target

    def write_bytes(self, relative_path: str | Path, payload: bytes) -> Path:
        target = self.paths.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return target

    def write_json(
        self, relative_path: str | Path, payload: dict[str, Any], *, indent: int = 2
    ) -> Path:
        content = json.dumps(payload, indent=indent, sort_keys=True)
        return self.write_text(relative_path, content)

    def snapshot_file(self, source: Path, *, destination_name: str | None = None) -> Path:
        """Copy a file into ``inputs/`` preserving relative naming."""

        dest_name = destination_name or source.name
        target = self.paths.inputs / dest_name
        data = source.read_bytes()
        target.write_bytes(data)
        return target

    def write_candidate(self, filename: str, content: str) -> Path:
        target = self.paths.candidates / filename
        target.write_text(content, encoding="utf-8")
        return target

    def ensure_reports(self, filenames: Iterable[str]) -> None:
        for name in filenames:
            path = self.paths.reports / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.touch()


@dataclass(frozen=True)
class RAGMatch:
    """Similarity match returned by the lightweight RAG index."""

    run_id: str
    score: float
    stack: str
    run_dir: Path
    label: str | None
    created_at: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "score": round(self.score, 4),
            "stack": self.stack,
            "run_dir": str(self.run_dir),
            "label": self.label,
            "created_at": self.created_at,
            "payload": self.payload,
        }


class RAGIndex:
    """Minimal SQLite-backed store for semantic retrieval over CODI runs."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self._index_dir = self.base_dir / "_rag"
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._index_dir / "index.sqlite3"
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert(
        self,
        *,
        run_id: str,
        stack: str,
        label: str | None,
        created_at: str,
        run_dir: Path,
        tokens: Sequence[str],
        payload: dict[str, Any],
    ) -> None:
        vector = _tokens_to_vector(tokens)
        if not vector:
            return

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO documents (run_id, stack, label, created_at, run_dir, vector, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    stack=excluded.stack,
                    label=excluded.label,
                    created_at=excluded.created_at,
                    run_dir=excluded.run_dir,
                    vector=excluded.vector,
                    payload=excluded.payload
                """,
                (
                    run_id,
                    stack,
                    label,
                    created_at,
                    str(run_dir),
                    json.dumps(vector, sort_keys=True),
                    json.dumps(payload, sort_keys=True),
                ),
            )
            conn.commit()

    def query_similar(
        self,
        *,
        stack: str,
        tokens: Sequence[str],
        limit: int = 3,
        exclude_run_id: str | None = None,
    ) -> list[RAGMatch]:
        query_vector = _tokens_to_vector(tokens)
        if not query_vector:
            return []

        matches: list[RAGMatch] = []

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT run_id, stack, label, created_at, run_dir, vector, payload FROM documents WHERE stack = ?",
                (stack,),
            ).fetchall()

        for row in rows:
            run_id = str(row["run_id"])
            if exclude_run_id and run_id == exclude_run_id:
                continue
            stored_vector = json.loads(row["vector"]) if row["vector"] else {}
            score = _cosine_similarity(query_vector, stored_vector)
            if score <= 0.0:
                continue
            payload = json.loads(row["payload"]) if row["payload"] else {}
            matches.append(
                RAGMatch(
                    run_id=run_id,
                    score=score,
                    stack=str(row["stack"]),
                    run_dir=Path(str(row["run_dir"])),
                    label=row["label"],
                    created_at=str(row["created_at"]),
                    payload=payload,
                )
            )

        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:limit]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    run_id TEXT PRIMARY KEY,
                    stack TEXT NOT NULL,
                    label TEXT,
                    created_at TEXT NOT NULL,
                    run_dir TEXT NOT NULL,
                    vector TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """)
            conn.commit()


def _create_directories(root: Path) -> RunPaths:
    inputs = root / "inputs"
    candidates = root / "candidates"
    metadata = root / "metadata"
    logs = root / "logs"
    reports = root / "reports"
    for path in (inputs, candidates, metadata, logs, reports):
        path.mkdir(parents=True, exist_ok=True)
    return RunPaths(
        root=root,
        inputs=inputs,
        candidates=candidates,
        metadata=metadata,
        logs=logs,
        reports=reports,
    )


def create_run_store(
    base_dir: Path, *, run_id: str | None = None, stack: str | None = None, label: str | None = None
) -> RunStore:
    """Instantiate a :class:`RunStore` rooted under ``base_dir``.

    The function ensures the run directory does not already exist by appending a
    counter suffix if required.
    """

    base_dir.mkdir(parents=True, exist_ok=True)
    base_id = run_id or generate_run_id(stack=stack, label=label)
    candidate_id = base_id
    root = base_dir / base_id
    suffix = 1
    while root.exists():
        candidate_id = f"{base_id}-{suffix}"
        root = base_dir / candidate_id
        suffix += 1
    root.mkdir(parents=True, exist_ok=False)
    paths = _create_directories(root)
    return RunStore(paths=paths, run_id=candidate_id)


def _tokens_to_vector(tokens: Sequence[str]) -> dict[str, float]:
    counts = Counter(_normalize_token(token) for token in tokens if token)
    if not counts:
        return {}
    norm = math.sqrt(sum(value * value for value in counts.values()))
    if norm == 0:
        return {}
    return {token: value / norm for token, value in counts.items()}


def _cosine_similarity(lhs: dict[str, float], rhs: dict[str, float]) -> float:
    if not lhs or not rhs:
        return 0.0
    score = sum(lhs.get(key, 0.0) * rhs.get(key, 0.0) for key in lhs.keys())
    return float(score)


def _normalize_token(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    return normalized.replace(" ", "-")
