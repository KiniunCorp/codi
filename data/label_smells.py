#!/usr/bin/env python3
"""
Dockerfile Smell & Quality Labeling Tool

Labels Dockerfiles with quality issues, smells, and patterns using:
- Built-in heuristics (patterns from CODI rules)
- CMD/ENTRYPOINT analysis flags
- Security gates validation
- Optional external hadolint (if available)

Usage:
    python3 label_smells.py --input data/raw/ --output data/raw/labels/
"""

import argparse
import json
import logging
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar

# Import CODI modules for analysis
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.cmd_parser import extract_cmd_analysis
from core.detect import detect_stack
from core.parse import parse_dockerfile
from core.security import validate_or_raise

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@dataclass
class DockerfileLabels:
    """Labels for a Dockerfile"""

    file: str
    stack: str | None
    smells: list[str]
    cmd_flags: dict[str, Any]
    security_issues: list[str]
    quality_score: float
    hadolint_codes: list[str] | None = None
    analysis: dict[str, Any] | None = None


class DockerfileLabeler:
    """Labels Dockerfiles with quality and smell information"""

    # Smell patterns (heuristics)
    SMELL_PATTERNS: ClassVar[dict] = {
        "root_user": r"USER\s+root\b",
        "latest_tag": r"FROM\s+[^:\s]+:latest",
        "apt_no_clean": r"apt-get\s+install.*(?!rm -rf /var/lib/apt)",
        "missing_workdir": lambda content: "WORKDIR" not in content.upper(),
        "copy_before_deps": lambda content: bool(
            re.search(r"COPY.*\nRUN.*(?:npm|pip|mvn)", content, re.MULTILINE)
        ),
        "shell_form_cmd": r"^CMD\s+[^[]",  # Shell form
        "privileged": r"--privileged",
        "sudo_usage": r"\bsudo\b",
        "curl_pipe_sh": r"curl.*\|\s*(?:bash|sh)",
        "add_http": r"ADD\s+https?://",
        "expose_privileged_port": r"EXPOSE\s+(?:[1-9]|[1-9]\d|[1-9]\d{2}|10[0-1]\d|102[0-3])\b",
    }

    def __init__(self, use_hadolint: bool = False):
        self.use_hadolint = use_hadolint and self._check_hadolint_available()

    def _check_hadolint_available(self) -> bool:
        """Check if hadolint is available"""
        try:
            subprocess.run(
                ["hadolint", "--version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
            return True
        except Exception:
            return False

    def run_hadolint(self, dockerfile_path: Path) -> list[str]:
        """Run hadolint on Dockerfile and extract error codes"""
        if not self.use_hadolint:
            return []

        try:
            result = subprocess.run(
                ["hadolint", "--format", "json", str(dockerfile_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return []

            # Parse JSON output
            issues = json.loads(result.stdout) if result.stdout else []
            codes = [issue.get("code", "") for issue in issues if "code" in issue]
            return sorted(set(codes))

        except Exception as e:
            logger.warning(f"Hadolint error for {dockerfile_path}: {e}")
            return []

    def detect_smells(self, content: str) -> list[str]:
        """Detect smells using heuristic patterns"""
        smells = []

        for smell_name, pattern in self.SMELL_PATTERNS.items():
            if callable(pattern):
                if pattern(content):
                    smells.append(smell_name)
            else:
                if re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
                    smells.append(smell_name)

        return sorted(smells)

    def analyze_with_codi(self, content: str, context_dir: Path) -> dict[str, Any]:
        """Use CODI analyzer to extract detailed information"""
        try:
            # Parse Dockerfile
            parsed = parse_dockerfile(content)

            # Detect stack
            stack_result = detect_stack(context_dir, dockerfile_content=content)
            stack = stack_result.stack if hasattr(stack_result, "stack") else stack_result

            # CMD analysis
            cmd_flags = {}
            cmd_result = extract_cmd_analysis(parsed)
            if cmd_result:
                cmd_flags = {
                    "uses_shell_form": cmd_result.form == "shell",
                    "installs_packages": any(
                        flag in cmd_result.flags
                        for flag in ["installs_packages", "package_install"]
                    ),
                    "runs_migrations": "runs_migrations" in cmd_result.flags,
                }

            # Security validation
            security_issues = []
            try:
                validate_or_raise(parsed)
            except Exception as e:
                security_issues.append(str(e))

            return {
                "stack": stack,
                "cmd_flags": cmd_flags,
                "security_issues": security_issues,
                "stages": len(
                    parsed.stages if hasattr(parsed, "stages") else parsed.get("stages", [])
                ),
                "base_images": [
                    s.from_image if hasattr(s, "from_image") else s.get("from", "")
                    for s in (
                        parsed.stages if hasattr(parsed, "stages") else parsed.get("stages", [])
                    )
                ],
            }

        except Exception as e:
            logger.warning(f"CODI analysis error: {e}")
            return {"stack": None, "cmd_flags": {}, "security_issues": [], "stages": 0}

    def calculate_quality_score(
        self, smells: list[str], security_issues: list[str], cmd_flags: dict
    ) -> float:
        """Calculate quality score (0-1, higher is better)"""
        score = 1.0

        # Deduct for smells
        smell_penalties = {
            "root_user": 0.15,
            "latest_tag": 0.10,
            "apt_no_clean": 0.05,
            "missing_workdir": 0.05,
            "shell_form_cmd": 0.05,
            "privileged": 0.20,
            "sudo_usage": 0.10,
            "curl_pipe_sh": 0.15,
            "add_http": 0.10,
        }

        for smell in smells:
            score -= smell_penalties.get(smell, 0.03)

        # Deduct for security issues
        score -= len(security_issues) * 0.10

        # Deduct for CMD flags
        if cmd_flags.get("installs_packages"):
            score -= 0.15
        if cmd_flags.get("uses_shell_form"):
            score -= 0.05

        return max(0.0, min(1.0, score))

    def label_dockerfile(
        self, dockerfile_path: Path, context_dir: Path | None = None
    ) -> DockerfileLabels:
        """Label a single Dockerfile"""
        try:
            content = dockerfile_path.read_text()

            # Detect smells
            smells = self.detect_smells(content)

            # Run CODI analysis
            context = context_dir or dockerfile_path.parent
            analysis = self.analyze_with_codi(content, context)

            # Run hadolint
            hadolint_codes = self.run_hadolint(dockerfile_path) if self.use_hadolint else None

            # Calculate quality score
            quality_score = self.calculate_quality_score(
                smells, analysis["security_issues"], analysis["cmd_flags"]
            )

            return DockerfileLabels(
                file=str(dockerfile_path),
                stack=analysis.get("stack"),
                smells=smells,
                cmd_flags=analysis["cmd_flags"],
                security_issues=analysis["security_issues"],
                quality_score=quality_score,
                hadolint_codes=hadolint_codes,
                analysis=analysis,
            )

        except Exception as e:
            logger.error(f"Error labeling {dockerfile_path}: {e}")
            return DockerfileLabels(
                file=str(dockerfile_path),
                stack=None,
                smells=[],
                cmd_flags={},
                security_issues=[f"labeling_error: {e!s}"],
                quality_score=0.0,
            )

    def process_directory(self, input_dir: Path, output_dir: Path) -> dict[str, Any]:
        """Process all Dockerfiles in directory"""
        output_dir.mkdir(parents=True, exist_ok=True)

        dockerfiles = sorted(input_dir.glob("*.Dockerfile"))
        logger.info(f"Found {len(dockerfiles)} Dockerfiles to label")

        labels_file = output_dir / "labels.jsonl"
        summary = {
            "total": len(dockerfiles),
            "by_stack": {},
            "common_smells": {},
            "avg_quality_score": 0.0,
        }

        total_score = 0.0

        with labels_file.open("w") as f:
            for dockerfile in dockerfiles:
                labels = self.label_dockerfile(dockerfile)

                # Write JSONL
                f.write(json.dumps(asdict(labels)) + "\n")

                # Update summary
                stack = labels.stack or "unknown"
                summary["by_stack"][stack] = summary["by_stack"].get(stack, 0) + 1

                for smell in labels.smells:
                    summary["common_smells"][smell] = summary["common_smells"].get(smell, 0) + 1

                total_score += labels.quality_score

        summary["avg_quality_score"] = total_score / len(dockerfiles) if dockerfiles else 0.0

        # Save summary
        summary_path = output_dir / "labeling_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2))

        logger.info("Labeling complete:")
        logger.info(f"  Total labeled: {summary['total']}")
        logger.info(f"  Avg quality: {summary['avg_quality_score']:.2f}")
        logger.info(f"  Top smells: {list(summary['common_smells'].items())[:5]}")
        logger.info(f"  Labels: {labels_file}")
        logger.info(f"  Summary: {summary_path}")

        return summary


def main():
    parser = argparse.ArgumentParser(description="Label Dockerfiles with quality metrics")
    parser.add_argument("--input", type=Path, required=True, help="Directory with Dockerfiles")
    parser.add_argument("--output", type=Path, required=True, help="Output directory for labels")
    parser.add_argument(
        "--use-hadolint",
        action="store_true",
        help="Use hadolint if available (requires hadolint installed)",
    )

    args = parser.parse_args()

    if not args.input.exists():
        logger.error(f"Input directory not found: {args.input}")
        sys.exit(1)

    labeler = DockerfileLabeler(use_hadolint=args.use_hadolint)
    labeler.process_directory(args.input, args.output)


if __name__ == "__main__":
    main()
