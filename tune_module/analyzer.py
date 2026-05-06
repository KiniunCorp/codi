#!/usr/bin/env python3
"""Analyze Dockerfiles with hadolint and docker build metrics."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


class AnalyzerError(Exception):
    """Raised when analysis fails."""


def run_hadolint(dockerfile: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["hadolint", "-f", "json", str(dockerfile)],
        capture_output=True,
        text=True,
    )
    stdout = result.stdout.strip()
    try:
        data = json.loads(stdout) if stdout else []
    except json.JSONDecodeError as exc:
        raise AnalyzerError("Hadolint output was not valid JSON") from exc
    if result.returncode != 0 and not data:
        raise AnalyzerError("Hadolint failed without JSON output")
    smells = [item.get("code") for item in data if item.get("code")]
    return {"smells": smells}


def build_image(dockerfile: Path) -> tuple[str, dict[str, Any]]:
    tag = f"dockerfile-analyzer-{uuid.uuid4().hex}"
    context_dir = str(dockerfile.parent)
    result = subprocess.run(
        [
            "docker",
            "build",
            "-f",
            str(dockerfile),
            "-t",
            tag,
            context_dir,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise AnalyzerError("Docker build failed")
    inspect = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(inspect.stdout)[0]
    size_mb = round(data.get("Size", 0) / 1_000_000, 2)
    layers = len(data.get("RootFS", {}).get("Layers", []) or [])
    return tag, {"size": size_mb, "layers": layers}


def remove_image(tag: str) -> None:
    subprocess.run(
        ["docker", "image", "rm", "-f", tag],
        capture_output=True,
        text=True,
    )


def analyze_dockerfile(dockerfile: Path) -> dict[str, Any]:
    metrics = {}
    lint_metrics = run_hadolint(dockerfile)
    metrics.update(lint_metrics)

    tag = None
    try:
        tag, build_metrics = build_image(dockerfile)
        metrics.update(build_metrics)
    finally:
        if tag:
            remove_image(tag)

    return metrics


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Dockerfiles for lint/build metrics")
    parser.add_argument("dockerfiles", nargs="+", help="Paths to Dockerfiles")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    exit_code = 0

    for dockerfile_str in args.dockerfiles:
        dockerfile = Path(dockerfile_str)
        if not dockerfile.exists():
            print("invalid")
            exit_code = 1
            continue
        try:
            metrics = analyze_dockerfile(dockerfile)
        except (AnalyzerError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            print("invalid")
            exit_code = 1
            continue
        output = {"file": str(dockerfile), "metrics": metrics}
        print(json.dumps(output))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
