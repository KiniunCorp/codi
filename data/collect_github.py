#!/usr/bin/env python3
"""
GitHub Dockerfile & Compose Collection Script

Crawls GitHub for diverse Dockerfiles and compose files to build training dataset.
Respects rate limits and provides provenance metadata.

Usage:
    python3 collect_github.py --count 500 --output data/raw/
    python3 collect_github.py --dry-run  # Test without API calls
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """Metadata for collected files"""

    url: str
    repo: str
    path: str
    sha: str
    size: int
    collected_at: str
    stack_hint: str | None = None
    has_compose: bool = False
    checksum: str | None = None


class GitHubCollector:
    """Collects Dockerfiles and compose files from GitHub"""

    GITHUB_API = "https://api.github.com"
    SEARCH_ENDPOINT = f"{GITHUB_API}/search/code"
    RATE_LIMIT_ENDPOINT = f"{GITHUB_API}/rate_limit"

    def build_existing_index(self, output_dir: Path) -> dict[str, set[str]]:
        """
        Build index of existing files to avoid re-downloading.
        Returns dict mapping repo names to sets of content hashes.
        """
        index = {}

        for existing_file in output_dir.glob("*.Dockerfile"):
            # Parse filename: reponame_{hash}.Dockerfile
            stem = existing_file.stem
            parts = stem.rsplit("_", 1)

            if len(parts) == 2:
                repo_name, content_hash = parts
                if repo_name not in index:
                    index[repo_name] = set()
                index[repo_name].add(content_hash)

        logger.info(
            f"Found {sum(len(v) for v in index.values())} existing Dockerfiles from {len(index)} repos"
        )
        return index

    # Stack-specific search patterns
    STACK_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "node": ["package.json", "next.config.js", "npm", "node:"],
        "python": ["requirements.txt", "pyproject.toml", "pip", "python:"],
        "java": ["pom.xml", "build.gradle", "maven:", "openjdk:", "temurin:"],
    }

    def __init__(self, token: str | None = None, dry_run: bool = False):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.dry_run = dry_run
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})
        self.session.headers.update({"Accept": "application/vnd.github.v3+json"})

    def check_rate_limit(self) -> dict[str, Any]:
        """Check GitHub API rate limit status"""
        if self.dry_run:
            return {"remaining": 1000, "reset": time.time() + 3600}

        try:
            resp = self.session.get(self.RATE_LIMIT_ENDPOINT, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            search_limits = data["resources"]["search"]
            logger.info(
                f"Rate limit: {search_limits['remaining']}/{search_limits['limit']} "
                f"(resets at {datetime.fromtimestamp(search_limits['reset'])})"
            )
            return search_limits
        except Exception as e:
            logger.warning(f"Failed to check rate limit: {e}")
            return {"remaining": 0, "reset": time.time() + 3600}

    def search_dockerfiles(
        self, query: str, max_results: int = 100, per_page: int = 30
    ) -> list[dict]:
        """Search GitHub for Dockerfiles matching query"""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would search: {query}")
            return []

        results = []
        page = 1
        while len(results) < max_results:
            try:
                params = {"q": query, "per_page": per_page, "page": page}
                resp = self.session.get(self.SEARCH_ENDPOINT, params=params, timeout=30)

                if resp.status_code == 403:
                    logger.warning("Rate limit hit, waiting...")
                    limits = self.check_rate_limit()
                    wait_time = max(limits["reset"] - time.time(), 60)
                    time.sleep(wait_time)
                    continue

                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])

                if not items:
                    break

                results.extend(items)
                logger.info(f"Fetched {len(results)}/{max_results} results (page {page})")
                page += 1

                # Respect rate limits - search API allows 30 req/min
                time.sleep(2)

            except Exception as e:
                logger.error(f"Search error on page {page}: {e}")
                break

        return results[:max_results]

    def download_file(self, url: str) -> str | None:
        """Download file content from GitHub"""
        if self.dry_run:
            return "# DRY-RUN: Mock Dockerfile content"

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error(f"Download error for {url}: {e}")
            return None

    def detect_stack(self, content: str, repo_url: str) -> str | None:
        """Heuristically detect stack from Dockerfile content"""
        content_lower = content.lower()

        for stack, patterns in self.STACK_PATTERNS.items():
            if any(pattern in content_lower for pattern in patterns):
                return stack

        return None

    def has_compose_file(self, repo: str) -> bool:
        """Check if repo has docker-compose file"""
        if self.dry_run:
            return False

        compose_names = ["docker-compose.yml", "docker-compose.yaml", "compose.yml"]
        repo_api = f"{self.GITHUB_API}/repos/{repo}/contents"

        try:
            resp = self.session.get(repo_api, timeout=10)
            if resp.status_code != 200:
                return False

            files = resp.json()
            if isinstance(files, list):
                filenames = [f.get("name", "") for f in files]
                return any(name in filenames for name in compose_names)
        except Exception:
            pass

        return False

    def save_file(self, content: str, metadata: FileMetadata, output_dir: Path) -> Path | None:
        """Save file with metadata"""
        try:
            # Create checksum-based filename to avoid collisions
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
            repo_name = metadata.repo.replace("/", "_")
            filename = f"{repo_name}_{content_hash}.Dockerfile"

            file_path = output_dir / filename
            file_path.write_text(content)

            # Save metadata
            metadata.checksum = hashlib.sha256(content.encode()).hexdigest()
            meta_path = output_dir / f"{filename}.meta.json"
            meta_path.write_text(json.dumps(asdict(metadata), indent=2))

            logger.info(f"Saved: {filename}")
            return file_path

        except Exception as e:
            logger.error(f"Save error: {e}")
            return None

    def collect(self, count: int, output_dir: Path, stack_filter: str | None = None):
        """Collect Dockerfiles from GitHub"""
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = output_dir / "logs"
        logs_dir.mkdir(exist_ok=True)

        # Log to file
        log_file = logs_dir / f"collection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(file_handler)

        logger.info(f"Starting collection: target={count}, output={output_dir}")

        # Build index of existing files to avoid re-downloading
        existing_index = self.build_existing_index(output_dir)

        # Build search queries
        queries = []
        if stack_filter:
            queries.append(f"filename:Dockerfile {stack_filter} in:file")
        else:
            # Diverse queries to get variety
            queries.extend(
                [
                    "filename:Dockerfile node in:file",
                    "filename:Dockerfile python in:file",
                    "filename:Dockerfile java spring in:file",
                    "filename:Dockerfile multi-stage in:file",
                    "filename:Dockerfile size:>1000 in:file",
                ]
            )

        collected = []
        skipped_count = 0
        manifest = {"collected_at": datetime.now().isoformat(), "files": []}

        per_query = max(count // len(queries), 50)

        for query in queries:
            if len(collected) >= count:
                break

            logger.info(f"Searching: {query}")
            results = self.search_dockerfiles(query, max_results=per_query)

            for item in results:
                if len(collected) >= count:
                    break

                try:
                    repo = item["repository"]["full_name"]
                    path = item["path"]
                    sha = item["sha"]

                    # Pre-check: Skip if this file already exists
                    repo_name = repo.replace("/", "_")
                    content_hash = sha[:12]  # GitHub SHA as proxy for content

                    if repo_name in existing_index and content_hash in existing_index[repo_name]:
                        logger.debug(f"Skipping already-collected: {repo}/{path}")
                        skipped_count += 1
                        continue

                    download_url = (
                        item.get("html_url", "")
                        .replace("github.com", "raw.githubusercontent.com")
                        .replace("/blob/", "/")
                    )

                    # Download content
                    content = self.download_file(download_url)
                    if not content or len(content) < 50:
                        continue

                    # Verify the content hash matches (double-check)
                    actual_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
                    if repo_name in existing_index and actual_hash in existing_index[repo_name]:
                        logger.debug(f"Skipping (verified by content hash): {repo}/{path}")
                        skipped_count += 1
                        continue

                    # Detect stack
                    stack_hint = self.detect_stack(content, repo)

                    # Check for compose
                    has_compose = self.has_compose_file(repo)

                    # Create metadata
                    metadata = FileMetadata(
                        url=item["html_url"],
                        repo=repo,
                        path=path,
                        sha=sha,
                        size=len(content),
                        collected_at=datetime.now().isoformat(),
                        stack_hint=stack_hint,
                        has_compose=has_compose,
                    )

                    # Save file
                    saved_path = self.save_file(content, metadata, output_dir)
                    if saved_path:
                        collected.append(metadata)
                        manifest["files"].append(asdict(metadata))

                except Exception as e:
                    logger.error(f"Error processing item: {e}")
                    continue

        # Save manifest
        manifest["total_collected"] = len(collected)
        manifest["skipped_existing"] = skipped_count
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # Save stats
        stats = {
            "total": len(collected),
            "by_stack": {},
            "with_compose": sum(1 for m in collected if m.has_compose),
        }

        for meta in collected:
            stack = meta.stack_hint or "unknown"
            stats["by_stack"][stack] = stats["by_stack"].get(stack, 0) + 1

        stats_path = output_dir / "stats.json"
        stats_path.write_text(json.dumps(stats, indent=2))

        logger.info(
            f"Collection complete: {len(collected)} files collected, {skipped_count} skipped (already existed)"
        )
        logger.info(f"Stack distribution: {stats['by_stack']}")
        logger.info(f"With compose: {stats['with_compose']}")
        logger.info(f"Manifest: {manifest_path}")

        return manifest


def main():
    parser = argparse.ArgumentParser(description="Collect Dockerfiles from GitHub")
    parser.add_argument("--count", type=int, default=500, help="Number of Dockerfiles to collect")
    parser.add_argument("--output", type=Path, default=Path("data/raw"), help="Output directory")
    parser.add_argument("--stack", choices=["node", "python", "java"], help="Filter by stack")
    parser.add_argument("--dry-run", action="store_true", help="Test without API calls")
    parser.add_argument("--token", help="GitHub API token (or set GITHUB_TOKEN env)")

    args = parser.parse_args()

    if not args.dry_run and not (args.token or os.getenv("GITHUB_TOKEN")):
        logger.warning("No GitHub token provided - rate limits will be very low!")
        logger.warning("Set GITHUB_TOKEN env var or use --token")

    collector = GitHubCollector(token=args.token, dry_run=args.dry_run)

    # Check rate limit before starting
    if not args.dry_run:
        limits = collector.check_rate_limit()
        if limits["remaining"] < 10:
            logger.error("Rate limit too low. Wait or provide a token.")
            sys.exit(1)

    collector.collect(args.count, args.output, args.stack)


if __name__ == "__main__":
    main()
