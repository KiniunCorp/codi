#!/usr/bin/env python3
"""
Synthetic Pair Generation from CODI Rules

Generates instruction-output pairs from CODI's rules and real analyzer outputs.
Creates training data that reflects the rules-first rewrite philosophy.

Usage:
    python3 synth_pairs_from_rules.py --curated data/curated/ --output data/pairs/
"""

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Import CODI modules
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.cmd_parser import extract_cmd_analysis
from core.detect import detect_stack
from core.parse import parse_dockerfile
from core.render import RenderContext, extract_cmd_render_context, render_for_stack
from core.rules import load_rules

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@dataclass
class TrainingPair:
    """Instruction-output pair for training"""

    id: str
    instruction: str
    input: dict[str, Any]
    output: dict[str, Any]
    metadata: dict[str, Any]


class PairGenerator:
    """Generates training pairs from CODI rules and analysis"""

    def __init__(self, rules_path: Path, incremental: bool = True):
        self.rules = load_rules(rules_path)
        self.incremental = incremental
        self.processed_files = set()  # Track already processed Dockerfile IDs

    def create_rewrite_instruction(self, stack: str, smells: list[str]) -> str:
        """Create instruction for rewriting task"""
        base = f"Optimize this {stack} Dockerfile"

        if smells:
            issues = ", ".join(smells[:3])
            base += f" addressing: {issues}"

        base += ". Provide reasoning and generate optimized candidates."

        return base

    def create_ranking_instruction(self, stack: str, candidate_count: int) -> str:
        """Create instruction for ranking task"""
        return f"Rank these {candidate_count} {stack} Dockerfile candidates by optimization quality. Explain your reasoning."

    def create_explanation_instruction(self, stack: str) -> str:
        """Create instruction for explanation task"""
        return f"Explain the changes in this optimized {stack} Dockerfile and their benefits."

    def extract_input_features(self, dockerfile_content: str, metadata: dict) -> dict[str, Any]:
        """Extract features for input"""
        try:
            parsed = parse_dockerfile(dockerfile_content)
            stack_result = detect_stack(dockerfile_content)
            stack = stack_result.stack if hasattr(stack_result, "stack") else stack_result

            # CMD analysis
            cmd_flags = {}
            cmd_result = extract_cmd_analysis(parsed)
            if cmd_result and cmd_result.dominant:
                cmd_flags = {
                    "uses_shell_form": cmd_result.dominant.form == "shell",
                    "installs_packages": any(
                        flag in cmd_result.dominant.flags
                        for flag in ["installs_packages", "package_install"]
                    ),
                    "runs_migrations": "runs_migrations" in cmd_result.dominant.flags,
                }

            return {
                "dockerfile": dockerfile_content,
                "stack": stack,
                "stages": len(parsed.stages),
                "base_images": [s.base_image for s in parsed.stages],
                "smells": metadata.get("metadata", {}).get("smells", []),
                "cmd_flags": cmd_flags,
                "quality_score": metadata.get("metadata", {}).get("quality_score", 0.5),
            }
        except Exception as e:
            logger.error(f"Error extracting features: {e}")
            return {
                "dockerfile": dockerfile_content,
                "stack": None,
                "smells": [],
                "cmd_flags": {},
            }

    def generate_rewrite_output(
        self, stack: str, original_content: str, input_features: dict
    ) -> dict[str, Any]:
        """Generate rewrite output using CODI rules"""
        try:
            # Create render context
            parsed = parse_dockerfile(original_content)

            # Build CMD render context if available
            cmd_context = None
            cmd_result = extract_cmd_analysis(parsed)
            if cmd_result:
                cmd_context = extract_cmd_render_context(cmd_result)

            # Create render context
            render_ctx = RenderContext(stack=stack, cmd=cmd_context)

            # Infer files and features from Dockerfile content
            content_lower = original_content.lower()

            # Add common files based on stack
            if stack == "node":
                render_ctx.add_file("package.json")
                render_ctx.add_lockfile("package-lock.json")
                if "next" in content_lower or "nextjs" in content_lower:
                    render_ctx.add_feature("nextjs")
            elif stack == "python":
                render_ctx.add_file("requirements.txt")
                if "fastapi" in content_lower or "uvicorn" in content_lower:
                    render_ctx.add_feature("fastapi")
                elif "flask" in content_lower:
                    render_ctx.add_feature("flask")
                elif "django" in content_lower:
                    render_ctx.add_feature("django")
            elif stack == "java":
                render_ctx.add_file("pom.xml")
                if "spring" in content_lower or "springboot" in content_lower:
                    render_ctx.add_feature("spring-boot")

            # Run CODI rewrite
            candidates = render_for_stack(render_ctx, rules_doc=self.rules)

            output = {
                "reasoning": [],
                "candidates": [],
                "recommendations": [],
            }

            # Extract reasoning from rules
            for candidate in candidates:
                reasoning_parts = list(candidate.rationale) if candidate.rationale else []

                # Stack-specific reasoning
                if not reasoning_parts:
                    reasoning_parts.append(f"Applied {stack} optimization pattern")

                # CMD reasoning
                cmd_flags = input_features.get("cmd_flags", {})
                if cmd_flags.get("uses_shell_form"):
                    if not any("exec-form" in r.lower() for r in reasoning_parts):
                        reasoning_parts.append(
                            "Converted CMD to exec-form for better signal handling"
                        )
                if cmd_flags.get("installs_packages"):
                    if not any("build stage" in r.lower() for r in reasoning_parts):
                        reasoning_parts.append("Promoted runtime package installs to build stage")

                # Smell-based reasoning
                smells = input_features.get("smells", [])
                if "latest_tag" in smells:
                    if not any("version" in r.lower() for r in reasoning_parts):
                        reasoning_parts.append("Pinned base image versions for reproducibility")
                if "root_user" in smells:
                    if not any("non-root" in r.lower() for r in reasoning_parts):
                        reasoning_parts.append("Added non-root user for security")
                if "apt_no_clean" in smells:
                    if not any("cleanup" in r.lower() for r in reasoning_parts):
                        reasoning_parts.append("Added apt cleanup to reduce layer size")

                output["reasoning"].extend(reasoning_parts)
                output["candidates"].append(
                    {
                        "name": candidate.name or "optimized",
                        "dockerfile": candidate.content,
                        "rationale": " | ".join(reasoning_parts),
                    }
                )

            # Add recommendations
            if not candidates:
                output["recommendations"].append(
                    "No automatic optimization available - manual review needed"
                )
            else:
                output["recommendations"].append(
                    f"Generated {len(candidates)} optimized candidate(s)"
                )

            return output

        except Exception as e:
            logger.error(f"Error generating rewrite output: {e}")
            return {
                "reasoning": ["Error generating candidates"],
                "candidates": [],
                "recommendations": ["Manual review required"],
            }

    def generate_ranking_output(self, candidates: list[dict], metrics: dict) -> dict[str, Any]:
        """Generate ranking output with rationale"""
        # Simple heuristic ranking for synthetic data
        ranked = []

        for i, candidate in enumerate(candidates):
            score = 0.5  # Base score

            rationale = candidate.get("rationale", "")

            # Score based on rationale keywords
            if "multi-stage" in rationale.lower():
                score += 0.2
            if "exec-form" in rationale.lower():
                score += 0.1
            if "promoted" in rationale.lower() or "build stage" in rationale.lower():
                score += 0.15
            if "non-root" in rationale.lower():
                score += 0.1

            ranked.append(
                {
                    "candidate": candidate.get("name", f"candidate_{i+1}"),
                    "score": min(1.0, score),
                    "reasoning": rationale,
                }
            )

        # Sort by score
        ranked.sort(key=lambda x: x["score"], reverse=True)

        return {
            "ranking": ranked,
            "winner": ranked[0]["candidate"] if ranked else None,
            "confidence": ranked[0]["score"] if ranked else 0.0,
        }

    def load_existing_pairs(self, output_dir: Path) -> None:
        """Load existing pairs to track already processed files"""
        pairs_file = output_dir / "training_pairs.jsonl"
        if not pairs_file.exists():
            logger.info("No existing pairs found - will process all files")
            return

        try:
            with pairs_file.open() as f:
                for line in f:
                    if line.strip():
                        try:
                            pair = json.loads(line)
                            # Extract the base dockerfile ID (remove task suffix)
                            pair_id = pair.get("id", "")
                            # Extract base ID before task suffix (e.g., "abc123_rewrite" -> "abc123")
                            base_id = pair_id.rsplit("_", 1)[0] if "_" in pair_id else pair_id
                            self.processed_files.add(base_id)
                        except json.JSONDecodeError:
                            pass

            logger.info(f"Found {len(self.processed_files)} previously processed Dockerfiles")
        except Exception as e:
            logger.warning(f"Error loading existing pairs: {e}")

    def needs_processing(self, dockerfile_path: Path, meta_path: Path) -> bool:
        """Check if a Dockerfile needs to be processed"""
        if not self.incremental:
            return True

        # Get the file ID from path (e.g., "abc123" from "abc123.Dockerfile")
        file_id = dockerfile_path.stem

        # If never processed, needs processing
        if file_id not in self.processed_files:
            return True

        # Check if source file has been modified
        if not meta_path.exists():
            return True

        try:
            meta_data = json.loads(meta_path.read_text())
            source_mtime = meta_data.get("metadata", {}).get("source_mtime")

            if source_mtime is None:
                # No timestamp info, process to be safe
                return True

            # Check if the curated file itself has been updated
            current_mtime = dockerfile_path.stat().st_mtime
            # Add a small tolerance for filesystem timestamp precision
            if current_mtime > source_mtime + 1:
                logger.debug(f"File updated: {dockerfile_path.name}")
                return True

            logger.debug(f"Skipping unchanged file: {dockerfile_path.name}")
            return False

        except Exception as e:
            logger.warning(f"Error checking {dockerfile_path.name}: {e}")
            return True

    def generate_pair_from_file(self, dockerfile_path: Path, meta_path: Path) -> list[TrainingPair]:
        """Generate training pairs from a curated Dockerfile"""
        try:
            content = dockerfile_path.read_text()
            metadata = json.loads(meta_path.read_text()) if meta_path.exists() else {}

            stack = metadata.get("stack")
            if not stack or stack == "unknown":
                logger.debug(f"Skipping {dockerfile_path.name}: unknown stack")
                return []

            file_id = dockerfile_path.stem

            # Extract input features
            input_features = self.extract_input_features(content, metadata)

            pairs = []

            # Pair 1: Rewrite task
            rewrite_instruction = self.create_rewrite_instruction(
                stack, input_features.get("smells", [])
            )
            rewrite_output = self.generate_rewrite_output(stack, content, input_features)

            if rewrite_output["candidates"]:
                pairs.append(
                    TrainingPair(
                        id=f"{file_id}_rewrite",
                        instruction=rewrite_instruction,
                        input=input_features,
                        output=rewrite_output,
                        metadata={
                            "task": "rewrite",
                            "stack": stack,
                            "original_file": str(dockerfile_path),
                        },
                    )
                )

            # Pair 2: Ranking task (if multiple candidates)
            if len(rewrite_output["candidates"]) > 1:
                ranking_instruction = self.create_ranking_instruction(
                    stack, len(rewrite_output["candidates"])
                )
                ranking_output = self.generate_ranking_output(rewrite_output["candidates"], {})

                pairs.append(
                    TrainingPair(
                        id=f"{file_id}_rank",
                        instruction=ranking_instruction,
                        input={
                            "candidates": rewrite_output["candidates"],
                            "stack": stack,
                            "original_features": input_features,
                        },
                        output=ranking_output,
                        metadata={
                            "task": "ranking",
                            "stack": stack,
                            "original_file": str(dockerfile_path),
                        },
                    )
                )

            # Pair 3: Explanation task
            if rewrite_output["candidates"]:
                explanation_instruction = self.create_explanation_instruction(stack)
                explanation_output = {
                    "summary": " | ".join(rewrite_output["reasoning"][:3]),
                    "detailed_reasoning": rewrite_output["reasoning"],
                    "key_changes": [
                        "Multi-stage build for smaller runtime image",
                        "Optimized layer caching",
                        "Security improvements (non-root, pinned versions)",
                    ],
                }

                pairs.append(
                    TrainingPair(
                        id=f"{file_id}_explain",
                        instruction=explanation_instruction,
                        input={
                            "original": content,
                            "optimized": rewrite_output["candidates"][0]["dockerfile"],
                            "stack": stack,
                        },
                        output=explanation_output,
                        metadata={
                            "task": "explanation",
                            "stack": stack,
                            "original_file": str(dockerfile_path),
                        },
                    )
                )

            return pairs

        except Exception as e:
            logger.error(f"Error generating pairs from {dockerfile_path}: {e}")
            return []

    def process_directory(self, curated_dir: Path, output_dir: Path) -> dict[str, Any]:
        """Process all curated Dockerfiles and generate pairs"""
        output_dir.mkdir(parents=True, exist_ok=True)

        pairs_file = output_dir / "training_pairs.jsonl"

        # Load existing pairs for incremental processing
        if self.incremental:
            self.load_existing_pairs(output_dir)

        dockerfiles = sorted(curated_dir.glob("*.Dockerfile"))
        logger.info(f"Found {len(dockerfiles)} curated Dockerfiles")

        # Separate files that need processing
        files_to_process = []
        skipped_count = 0

        for dockerfile in dockerfiles:
            meta_path = dockerfile.with_suffix(".meta.json")
            if self.needs_processing(dockerfile, meta_path):
                files_to_process.append((dockerfile, meta_path))
            else:
                skipped_count += 1

        if self.incremental:
            logger.info(
                f"Incremental mode: processing {len(files_to_process)} files, skipping {skipped_count} unchanged files"
            )
        else:
            logger.info(f"Full mode: processing all {len(files_to_process)} files")

        new_pairs = []
        stats = {
            "total_dockerfiles": len(dockerfiles),
            "newly_processed": len(files_to_process),
            "skipped_unchanged": skipped_count,
            "new_pairs": 0,
            "by_task": {},
            "by_stack": {},
        }

        # In incremental mode, append to existing file; in full mode, overwrite
        file_mode = "a" if (self.incremental and pairs_file.exists()) else "w"

        # If in full mode, remove old pairs file
        if not self.incremental and pairs_file.exists():
            pairs_file.unlink()

        with pairs_file.open(file_mode) as f:
            for dockerfile, meta_path in files_to_process:
                pairs = self.generate_pair_from_file(dockerfile, meta_path)

                for pair in pairs:
                    f.write(json.dumps(asdict(pair)) + "\n")
                    new_pairs.append(pair)

                    # Update stats
                    task = pair.metadata.get("task", "unknown")
                    stack = pair.metadata.get("stack", "unknown")
                    stats["by_task"][task] = stats["by_task"].get(task, 0) + 1
                    stats["by_stack"][stack] = stats["by_stack"].get(stack, 0) + 1

        stats["new_pairs"] = len(new_pairs)

        # Count total pairs in the file for reporting
        total_pairs_count = 0
        try:
            with pairs_file.open() as f:
                for line in f:
                    if line.strip():
                        total_pairs_count += 1
        except Exception:
            total_pairs_count = len(new_pairs)

        stats["total_pairs"] = total_pairs_count

        # Save stats
        stats["mode"] = "incremental" if self.incremental else "full"
        stats_path = output_dir / "pair_generation_stats.json"
        stats_path.write_text(json.dumps(stats, indent=2))

        logger.info("=" * 50)
        logger.info("Pair generation complete:")
        logger.info(f"  Mode: {'Incremental' if self.incremental else 'Full'}")
        logger.info(f"  Total Dockerfiles: {stats['total_dockerfiles']}")
        if self.incremental:
            logger.info(f"  Newly processed: {stats['newly_processed']}")
            logger.info(f"  Skipped unchanged: {stats['skipped_unchanged']}")
            logger.info(f"  New pairs generated: {stats['new_pairs']}")
        logger.info(f"  Total pairs in file: {stats['total_pairs']}")
        logger.info(f"  New pairs by task: {stats['by_task']}")
        logger.info(f"  New pairs by stack: {stats['by_stack']}")
        logger.info(f"  Pairs file: {pairs_file}")

        return stats


def main():
    parser = argparse.ArgumentParser(description="Generate training pairs from curated Dockerfiles")
    parser.add_argument(
        "--curated", type=Path, required=True, help="Directory with curated Dockerfiles"
    )
    parser.add_argument("--output", type=Path, required=True, help="Output directory for pairs")
    parser.add_argument(
        "--rules",
        type=Path,
        default=Path("patterns/rules.yml"),
        help="Path to rules.yml",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Process all files (disable incremental mode)",
    )

    args = parser.parse_args()

    if not args.curated.exists():
        logger.error(f"Curated directory not found: {args.curated}")
        sys.exit(1)

    if not args.rules.exists():
        logger.error(f"Rules file not found: {args.rules}")
        sys.exit(1)

    generator = PairGenerator(args.rules, incremental=not args.full)
    generator.process_directory(args.curated, args.output)


if __name__ == "__main__":
    main()
