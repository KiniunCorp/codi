from __future__ import annotations

import json
from pathlib import Path

from core.store import RAGIndex, create_run_store


def test_create_run_store_creates_expected_structure(tmp_path: Path) -> None:
    store = create_run_store(tmp_path, stack="node", label="Demo Project")

    assert store.paths.root.exists()
    assert store.paths.inputs.exists()
    assert store.paths.candidates.exists()
    assert store.paths.metadata.exists()

    candidate_path = store.write_candidate("001-sample.Dockerfile", "FROM node:20-alpine")
    assert candidate_path.read_text() == "FROM node:20-alpine"

    store.write_json("metadata/sample.json", {"hello": "world"})
    payload = json.loads((store.paths.metadata / "sample.json").read_text())
    assert payload == {"hello": "world"}


def test_rag_index_similarity(tmp_path: Path) -> None:
    index = RAGIndex(tmp_path)

    run_dir = tmp_path / "runs" / "20250101T120000Z-node-demo"
    run_dir.mkdir(parents=True, exist_ok=True)

    index.upsert(
        run_id="run-1",
        stack="node",
        label="demo",
        created_at="20250101T120000Z",
        run_dir=run_dir,
        tokens=["stack:node", "feature:nextjs", "rule:001", "metric:layers:<= 8"],
        payload={"note": "first"},
    )

    matches = index.query_similar(stack="node", tokens=["feature:nextjs", "rule:001"], limit=1)
    assert matches, "Expected at least one match"

    match = matches[0]
    assert match.run_id == "run-1"
    assert match.to_dict()["payload"] == {"note": "first"}
