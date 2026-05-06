#!/usr/bin/env python3
"""Verify LoRA adapter integrity using checksums from metadata.json.

This script validates that adapter files match their expected checksums,
ensuring that mounted adapters have not been corrupted during transfer
or storage. It is designed to run in air-gapped environments with minimal
dependencies (standard library only).

Usage:
    python3 verify_adapter.py /models/adapters/qwen15b-lora-v0.1

Exit codes:
    0 - All checksums valid
    1 - Checksum mismatch or missing files
    2 - Invalid metadata or missing metadata.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_adapter(adapter_dir: Path) -> bool:
    """Verify adapter files against metadata checksums.

    Args:
        adapter_dir: Path to adapter directory containing metadata.json

    Returns:
        True if all checksums match, False otherwise
    """
    metadata_path = adapter_dir / "metadata.json"

    if not metadata_path.exists():
        print(f"❌ ERROR: metadata.json not found in {adapter_dir}", file=sys.stderr)
        return False

    try:
        with open(metadata_path) as f:
            metadata: dict[str, Any] = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"❌ ERROR: Failed to read metadata.json: {e}", file=sys.stderr)
        return False

    checksums = metadata.get("checksums", {})
    if not checksums:
        print("⚠️  WARNING: No checksums found in metadata.json, skipping verification")
        return True

    print(f"[verify_adapter] Validating {len(checksums)} file(s)...")
    all_valid = True

    for filename, expected_sha256 in checksums.items():
        file_path = adapter_dir / filename

        if not file_path.exists():
            print(f"❌ ERROR: File missing: {filename}", file=sys.stderr)
            all_valid = False
            continue

        actual_sha256 = compute_sha256(file_path)

        if actual_sha256 == expected_sha256:
            print(f"✅ {filename}: checksum valid")
        else:
            print(f"❌ {filename}: checksum mismatch!", file=sys.stderr)
            print(f"   Expected: {expected_sha256}", file=sys.stderr)
            print(f"   Actual:   {actual_sha256}", file=sys.stderr)
            all_valid = False

    return all_valid


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    argv = argv or sys.argv[1:]

    if not argv or "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    adapter_dir = Path(argv[0]).expanduser().resolve()

    if not adapter_dir.is_dir():
        print(f"❌ ERROR: Not a directory: {adapter_dir}", file=sys.stderr)
        return 2

    if verify_adapter(adapter_dir):
        print(f"\n✅ Adapter verification passed: {adapter_dir.name}")
        return 0
    else:
        print(f"\n❌ Adapter verification FAILED: {adapter_dir.name}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
