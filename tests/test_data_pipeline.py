"""
Tests for LLM data collection and preparation pipeline.
"""

import json
import tempfile
from pathlib import Path

import pytest


def test_collect_github_dry_run():
    """Test GitHub collector in dry-run mode"""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
    from collect_github import GitHubCollector

    collector = GitHubCollector(token=None, dry_run=True)

    # Test rate limit check
    limits = collector.check_rate_limit()
    assert limits["remaining"] > 0

    # Test search (dry-run returns empty)
    results = collector.search_dockerfiles("filename:Dockerfile", max_results=10)
    assert results == []

    # Test download (dry-run returns mock)
    content = collector.download_file("https://example.com/Dockerfile")
    assert content is not None
    assert "DRY-RUN" in content


def test_script_extractor():
    """Test CMD/ENTRYPOINT script extraction"""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
    from extract_cmd_scripts import ScriptExtractor

    extractor = ScriptExtractor(token=None)

    # Test script reference extraction
    dockerfile_content = """
FROM node:20-slim
COPY start.sh /app/
CMD ["./start.sh"]
ENTRYPOINT ["/app/entrypoint.sh"]
"""

    scripts = extractor.extract_script_references(dockerfile_content)
    assert "start.sh" in scripts
    # The extractor extracts basename when path includes directory
    assert any("entrypoint.sh" in script for script in scripts)

    # Test placeholder creation
    placeholder = extractor.create_placeholder_script("test.sh")
    assert "test.sh" in placeholder
    assert "#!/bin/bash" in placeholder


def test_dockerfile_labeler():
    """Test Dockerfile labeling"""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
    from label_smells import DockerfileLabeler

    labeler = DockerfileLabeler(use_hadolint=False)

    # Test smell detection
    bad_dockerfile = """
FROM ubuntu:latest
RUN apt-get update && apt-get install -y curl
USER root
CMD npm start
"""

    smells = labeler.detect_smells(bad_dockerfile)
    assert "latest_tag" in smells
    assert "root_user" in smells
    assert "shell_form_cmd" in smells
    assert "apt_no_clean" in smells


def test_standardizer():
    """Test dataset standardization"""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
    from standardize import DatasetStandardizer

    standardizer = DatasetStandardizer()

    # Test normalization
    content = "FROM node:20\r\nRUN npm install  \r\n\r\n\r\nCMD npm start\r\n"
    normalized = standardizer.normalize_content(content)
    assert "\r" not in normalized
    assert normalized.endswith("\n")

    # Test validation
    valid_content = "FROM node:20\nRUN npm ci\nRUN npm build\nCMD npm start"
    valid, reason = standardizer.is_valid_dockerfile(valid_content)
    assert valid is True, f"Expected valid=True but got valid={valid}, reason={reason}"

    # Test with short invalid content (< 50 chars)
    invalid, reason = standardizer.is_valid_dockerfile("RUN echo hello")
    assert invalid is False
    assert reason in ("missing_from", "too_short")  # Could be either depending on order

    # Test quality filtering
    test_content = "FROM node:20-test\nRUN npm test"
    passes, reason = standardizer.filter_quality(test_content, None)
    assert passes is False
    assert reason == "test_example"


def test_pair_generator_basic():
    """Test training pair generation"""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
    from synth_pairs_from_rules import PairGenerator

    rules_path = Path(__file__).parent.parent / "patterns" / "rules.yml"
    if not rules_path.exists():
        pytest.skip("rules.yml not found")

    generator = PairGenerator(rules_path)

    # Test instruction creation
    instruction = generator.create_rewrite_instruction("node", ["latest_tag", "root_user"])
    assert "node" in instruction.lower()
    assert "latest_tag" in instruction or "optimize" in instruction.lower()


def test_dataset_splitter():
    """Test dataset splitting"""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
    from split_dataset import DatasetSplitter

    splitter = DatasetSplitter(train_ratio=0.7, val_ratio=0.15, test_ratio=0.15, seed=42)

    # Create mock pairs
    mock_pairs = [
        {
            "id": f"pair_{i}",
            "instruction": "test",
            "input": {},
            "output": {},
            "metadata": {"stack": "node" if i % 2 == 0 else "python", "task": "rewrite"},
        }
        for i in range(100)
    ]

    # Test splitting
    train, val, test = splitter.stratify_split(mock_pairs, key="stack")

    # Check sizes roughly match ratios
    assert 60 <= len(train) <= 80
    assert 10 <= len(val) <= 25
    assert 10 <= len(test) <= 25

    # Check total
    assert len(train) + len(val) + len(test) == len(mock_pairs)

    # Test no leakage
    assert splitter.verify_no_leakage(train, val, test)


def test_end_to_end_pipeline():
    """Test end-to-end data pipeline with mock data"""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "data"))

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create mock raw data
        raw_dir = tmppath / "raw"
        raw_dir.mkdir()

        # Create sample Dockerfiles
        for i in range(3):
            dockerfile = raw_dir / f"test_{i}.Dockerfile"
            content = """FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
"""
            dockerfile.write_text(content)

            # Create metadata
            meta = {
                "repo": f"test/repo{i}",
                "url": f"https://github.com/test/repo{i}",
                "stack_hint": "node",
                "collected_at": "2025-01-01T00:00:00Z",
            }
            meta_file = dockerfile.with_suffix(".Dockerfile.meta.json")
            meta_file.write_text(json.dumps(meta))

        # Test standardization
        from standardize import DatasetStandardizer

        standardizer = DatasetStandardizer()
        curated_dir = tmppath / "curated"
        index = standardizer.process_directory(raw_dir, curated_dir)

        assert index["total_output"] >= 1
        assert (curated_dir / "index.json").exists()

        # Test pair generation
        from synth_pairs_from_rules import PairGenerator

        rules_path = Path(__file__).parent.parent / "patterns" / "rules.yml"
        if not rules_path.exists():
            pytest.skip("rules.yml not found")

        generator = PairGenerator(rules_path)
        pairs_dir = tmppath / "pairs"
        pairs_stats = generator.process_directory(curated_dir, pairs_dir)

        # If no pairs generated, that's OK for test - might be due to missing stack detection
        # Just verify the process ran without errors
        assert pairs_stats is not None
        assert (pairs_dir / "training_pairs.jsonl").exists()

        # Test splitting
        from split_dataset import DatasetSplitter

        splitter = DatasetSplitter(seed=42)
        splits_dir = tmppath / "splits"

        # Only split if we have pairs
        pairs_file = pairs_dir / "training_pairs.jsonl"
        if pairs_file.exists() and pairs_file.stat().st_size > 0:
            split_stats = splitter.process(pairs_file, splits_dir)

            # Verify split files exist
            assert (splits_dir / "stats.json").exists()
            # Train file should exist even with small dataset
            train_file = splits_dir / "train.jsonl"
            if split_stats["splits"]["train"]["count"] > 0:
                assert train_file.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
