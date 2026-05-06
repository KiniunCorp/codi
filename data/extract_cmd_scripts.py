#!/usr/bin/env python3
"""
CMD/ENTRYPOINT Script Extraction Tool

Extracts scripts referenced in CMD/ENTRYPOINT instructions from Dockerfiles
and attempts to fetch them from the source repository.

Usage:
    python3 extract_cmd_scripts.py --input data/raw/ --output data/raw/scripts/
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, ClassVar

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class ScriptExtractor:
    """Extracts CMD/ENTRYPOINT referenced scripts"""

    # Patterns to detect script references
    SCRIPT_PATTERNS: ClassVar[list[str]] = [
        r'CMD\s+\[.*?"([^"]*\.sh)".*?\]',  # CMD ["./start.sh"] or CMD ["sh", "start.sh"]
        r'ENTRYPOINT\s+\[.*?"([^"]*\.sh)".*?\]',  # ENTRYPOINT ["/app/entrypoint.sh"]
        r"CMD\s+([^\s]+\.sh)",  # CMD ./start.sh (shell form)
        r"ENTRYPOINT\s+([^\s]+\.sh)",  # ENTRYPOINT ./entrypoint.sh (shell form)
        r'CMD.*?(?:bash|sh)\s+-c\s+"?([^"\s]+\.sh)"?',  # CMD bash -c "script.sh"
        r"COPY\s+([^\s]+\.sh)\s+",  # COPY start.sh /app/
    ]

    def __init__(self, token: str | None = None):
        self.token = token
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})

    def extract_script_references(self, dockerfile_content: str) -> list[str]:
        """Extract script references from Dockerfile"""
        scripts = set()

        # Look for .sh files in CMD/ENTRYPOINT/COPY instructions
        for line in dockerfile_content.splitlines():
            line_upper = line.strip().upper()

            # Check if line starts with CMD, ENTRYPOINT, or COPY
            if line_upper.startswith(("CMD ", "ENTRYPOINT ", "COPY ")):
                # Find all .sh references in the line
                sh_matches = re.findall(r'([^\s"\[\],]+\.sh)', line)
                for match in sh_matches:
                    # Clean up path - remove leading ./ and /
                    script_path = match.lstrip("./").lstrip("/")
                    if script_path and script_path.endswith(".sh"):
                        scripts.add(script_path)

        return sorted(scripts)

    def fetch_script_from_repo(
        self, repo: str, script_path: str, branch: str = "main"
    ) -> str | None:
        """Attempt to fetch script from GitHub repository"""
        if not self.token:
            return None

        # Try common branches
        branches = [branch, "main", "master", "develop"]

        for branch_name in branches:
            url = f"https://raw.githubusercontent.com/{repo}/{branch_name}/{script_path}"
            try:
                resp = self.session.get(url, timeout=10)
                if resp.status_code == 200:
                    logger.info(f"Fetched {script_path} from {repo}@{branch_name}")
                    return resp.text
            except Exception:
                continue

        return None

    def create_placeholder_script(self, script_name: str) -> str:
        """Create placeholder script content for missing scripts"""
        return f"""#!/bin/bash
# Placeholder for {script_name}
# Original script was not available in repository

echo "Script: {script_name}"
echo "This is a placeholder - actual script was not found"
"""

    def process_dockerfile(
        self, dockerfile_path: Path, metadata_path: Path, output_dir: Path
    ) -> dict[str, Any]:
        """Process a single Dockerfile and extract scripts"""
        try:
            content = dockerfile_path.read_text()
            scripts = self.extract_script_references(content)

            if not scripts:
                return {"dockerfile": str(dockerfile_path), "scripts": [], "status": "no_scripts"}

            # Load metadata to get repo info
            metadata = {}
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text())

            repo = metadata.get("repo", "")
            results = {
                "dockerfile": str(dockerfile_path),
                "repo": repo,
                "scripts": [],
                "status": "processed",
            }

            # Create per-dockerfile script directory
            dockerfile_id = dockerfile_path.stem
            script_dir = output_dir / dockerfile_id
            script_dir.mkdir(parents=True, exist_ok=True)

            for script_path in scripts:
                script_name = Path(script_path).name
                output_file = script_dir / script_name

                # Try to fetch from repo
                script_content = None
                if repo:
                    script_content = self.fetch_script_from_repo(repo, script_path)

                # Use placeholder if not found
                if not script_content:
                    script_content = self.create_placeholder_script(script_name)
                    logger.debug(f"Created placeholder for {script_name}")

                # Save script
                output_file.write_text(script_content)

                results["scripts"].append(
                    {
                        "name": script_name,
                        "original_path": script_path,
                        "saved_path": str(output_file),
                        "found_in_repo": bool(
                            repo and script_content and "Placeholder" not in script_content
                        ),
                    }
                )

            return results

        except Exception as e:
            logger.error(f"Error processing {dockerfile_path}: {e}")
            return {
                "dockerfile": str(dockerfile_path),
                "scripts": [],
                "status": "error",
                "error": str(e),
            }

    def process_directory(self, input_dir: Path, output_dir: Path) -> dict[str, Any]:
        """Process all Dockerfiles in directory"""
        output_dir.mkdir(parents=True, exist_ok=True)

        dockerfiles = sorted(input_dir.glob("*.Dockerfile"))
        logger.info(f"Found {len(dockerfiles)} Dockerfiles to process")

        results = {
            "total_dockerfiles": len(dockerfiles),
            "dockerfiles_with_scripts": 0,
            "total_scripts_extracted": 0,
            "scripts_found_in_repo": 0,
            "files": [],
        }

        for dockerfile in dockerfiles:
            metadata_path = dockerfile.with_suffix(".Dockerfile.meta.json")
            file_result = self.process_dockerfile(dockerfile, metadata_path, output_dir)
            results["files"].append(file_result)

            if file_result.get("scripts"):
                results["dockerfiles_with_scripts"] += 1
                results["total_scripts_extracted"] += len(file_result["scripts"])
                results["scripts_found_in_repo"] += sum(
                    1 for s in file_result["scripts"] if s.get("found_in_repo")
                )

        # Save summary
        summary_path = output_dir / "extraction_summary.json"
        summary_path.write_text(json.dumps(results, indent=2))

        logger.info("Extraction complete:")
        logger.info(f"  Dockerfiles with scripts: {results['dockerfiles_with_scripts']}")
        logger.info(f"  Total scripts extracted: {results['total_scripts_extracted']}")
        logger.info(f"  Scripts found in repos: {results['scripts_found_in_repo']}")
        logger.info(f"  Summary: {summary_path}")

        return results


def main():
    parser = argparse.ArgumentParser(description="Extract CMD/ENTRYPOINT scripts from Dockerfiles")
    parser.add_argument(
        "--input", type=Path, required=True, help="Directory with collected Dockerfiles"
    )
    parser.add_argument("--output", type=Path, required=True, help="Output directory for scripts")
    parser.add_argument("--token", help="GitHub API token (or set GITHUB_TOKEN env)")

    args = parser.parse_args()

    if not args.input.exists():
        logger.error(f"Input directory not found: {args.input}")
        sys.exit(1)

    import os

    token = args.token or os.getenv("GITHUB_TOKEN")
    if not token:
        logger.warning("No GitHub token - will use placeholders for all scripts")

    extractor = ScriptExtractor(token=token)
    extractor.process_directory(args.input, args.output)


if __name__ == "__main__":
    main()
