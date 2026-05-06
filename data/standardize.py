#!/usr/bin/env python3
"""
Dataset Standardization Tool

Normalizes raw Dockerfiles, removes duplicates, and prepares curated dataset.

Usage:
    python3 standardize.py --input data/raw/ --output data/curated/
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@dataclass
class StandardizedFile:
    """Standardized Dockerfile record"""

    id: str
    original_file: str
    content_hash: str
    stack: str | None
    size: int
    line_count: int
    normalized_content: str
    metadata: dict


class DatasetStandardizer:
    """Standardizes and curates Dockerfiles"""

    def __init__(self, incremental: bool = True):
        self.seen_hashes = set()
        self.duplicate_count = 0
        self.incremental = incremental
        self.processed_files = {}  # Maps original_file -> output_id
        self.existing_outputs = {}  # Maps output_id -> StandardizedFile data

    def normalize_content(self, content: str) -> str:
        """Normalize Dockerfile content"""
        # Normalize line endings
        content = content.replace("\r\n", "\n").replace("\r", "\n")

        # Remove trailing whitespace
        lines = [line.rstrip() for line in content.splitlines()]

        # Remove excessive blank lines (more than 2 consecutive)
        normalized_lines = []
        blank_count = 0

        for line in lines:
            if not line.strip():
                blank_count += 1
                if blank_count <= 2:
                    normalized_lines.append(line)
            else:
                blank_count = 0
                normalized_lines.append(line)

        # Join and ensure single trailing newline
        normalized = "\n".join(normalized_lines).rstrip() + "\n"

        return normalized

    def compute_content_hash(self, content: str) -> str:
        """Compute hash of normalized content for deduplication"""
        # Remove comments and whitespace for semantic comparison
        semantic = re.sub(r"#.*$", "", content, flags=re.MULTILINE)
        semantic = re.sub(r"\s+", " ", semantic).strip()

        return hashlib.sha256(semantic.encode()).hexdigest()

    def get_first_instruction(self, content: str) -> str | None:
        """Get the first non-comment, non-blank instruction from Dockerfile"""
        for line in content.splitlines():
            stripped = line.strip()
            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue
            # Extract the instruction (first word)
            match = re.match(r"^([A-Z]+)\s+", stripped, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        return None

    def is_valid_dockerfile(self, content: str) -> tuple[bool, str]:
        """Check if Dockerfile is valid enough to include"""
        if len(content) < 50:
            return False, "too_short"

        # Check for FROM instruction anywhere in the file
        if not re.search(r"FROM\s+", content, re.IGNORECASE):
            return False, "missing_from"

        # Get first instruction (ignoring comments and blank lines)
        first_instruction = self.get_first_instruction(content)

        # Valid Dockerfiles can start with ARG (build args before FROM), # (comments), or FROM
        if first_instruction and first_instruction not in ["FROM", "ARG"]:
            return False, "invalid_start"

        # Check for minimum structure
        instruction_count = len(
            re.findall(
                r"^(FROM|RUN|COPY|ADD|CMD|ENTRYPOINT|WORKDIR|ENV|EXPOSE)\s+",
                content,
                re.MULTILINE | re.IGNORECASE,
            )
        )
        if instruction_count < 3:
            return False, "too_simple"

        return True, "valid"

    def filter_quality(self, content: str, labels: dict | None = None) -> tuple[bool, str]:
        """Filter out low-quality Dockerfiles"""
        # Check for test/example markers
        markers = ["test", "example", "demo", "tutorial", "sample"]
        if any(marker in content.lower() for marker in markers):
            # Check if it's actually substantial
            if len(content) < 500:
                return False, "test_example"

        # Check quality score from labels
        if labels:
            quality_score = labels.get("quality_score", 0.0)
            if quality_score < 0.2:
                return False, "low_quality"

        return True, "pass"

    def load_labels(self, input_dir: Path) -> dict[str, dict]:
        """Load labels if available"""
        labels_file = input_dir / "labels" / "labels.jsonl"
        if not labels_file.exists():
            logger.warning("Labels file not found - proceeding without quality filtering")
            return {}

        labels_map = {}
        try:
            with labels_file.open() as f:
                for line in f:
                    if line.strip():
                        labels = json.loads(line)
                        file_path = Path(labels["file"]).name
                        labels_map[file_path] = labels
        except Exception as e:
            logger.error(f"Error loading labels: {e}")

        logger.info(f"Loaded labels for {len(labels_map)} files")
        return labels_map

    def load_existing_index(self, output_dir: Path) -> None:
        """Load existing index to track already processed files"""
        index_path = output_dir / "index.json"
        if not index_path.exists():
            logger.info("No existing index found - will process all files")
            return

        try:
            index = json.loads(index_path.read_text())
            for file_info in index.get("files", []):
                file_id = file_info["id"]
                # Try to load the metadata to get original file mapping
                meta_path = output_dir / f"{file_id}.meta.json"
                if meta_path.exists():
                    meta_data = json.loads(meta_path.read_text())
                    original_file = meta_data.get("original_file")
                    if original_file:
                        self.processed_files[original_file] = file_id
                        self.existing_outputs[file_id] = meta_data
                        # Add existing hash to avoid duplicates
                        if "content_hash" in meta_data:
                            self.seen_hashes.add(meta_data["content_hash"])

            logger.info(f"Loaded {len(self.processed_files)} previously processed files")
        except Exception as e:
            logger.warning(f"Error loading existing index: {e}")

    def is_marked_invalid(self, dockerfile_path: Path, output_dir: Path) -> bool:
        """Check if file was previously marked as invalid and unchanged"""
        file_id = hashlib.sha256(dockerfile_path.name.encode()).hexdigest()[:16]
        invalid_marker = output_dir / f"{file_id}.invalid.json"

        if not invalid_marker.exists():
            return False

        try:
            marker_data = json.loads(invalid_marker.read_text())
            stored_mtime = marker_data.get("source_mtime")
            current_mtime = dockerfile_path.stat().st_mtime

            # If file hasn't changed since being marked invalid, skip it
            if stored_mtime and current_mtime <= stored_mtime:
                logger.debug(
                    f"Skipping previously invalid file: {dockerfile_path.name} (reason: {marker_data.get('reason')})"
                )
                return True
        except Exception as e:
            logger.warning(f"Error reading invalid marker for {dockerfile_path.name}: {e}")

        return False

    def needs_reprocessing(self, dockerfile_path: Path, output_dir: Path) -> bool:
        """Check if a file needs to be reprocessed"""
        if not self.incremental:
            return True

        # Check if marked as invalid and unchanged
        if self.is_marked_invalid(dockerfile_path, output_dir):
            return False

        original_file_str = str(dockerfile_path)

        # If never processed, needs processing
        if original_file_str not in self.processed_files:
            return True

        # Check if file has been modified since last processing
        try:
            file_id = self.processed_files[original_file_str]
            if file_id not in self.existing_outputs:
                return True

            # Check modification time
            current_mtime = dockerfile_path.stat().st_mtime
            existing_meta = self.existing_outputs[file_id]

            # If we don't have stored mtime, reprocess to be safe
            if "source_mtime" not in existing_meta:
                return True

            stored_mtime = existing_meta["source_mtime"]
            if current_mtime > stored_mtime:
                logger.debug(f"File modified: {dockerfile_path.name}")
                return True

            logger.debug(f"Skipping unchanged file: {dockerfile_path.name}")
            return False

        except Exception as e:
            logger.warning(f"Error checking {dockerfile_path.name}: {e}")
            return True

    def save_invalid_marker(self, dockerfile_path: Path, output_dir: Path, reason: str) -> None:
        """Save a marker file for invalid Dockerfiles to skip in future runs"""
        file_id = hashlib.sha256(dockerfile_path.name.encode()).hexdigest()[:16]
        invalid_marker = output_dir / f"{file_id}.invalid.json"

        marker_data = {
            "id": file_id,
            "original_file": str(dockerfile_path),
            "reason": reason,
            "source_mtime": dockerfile_path.stat().st_mtime,
            "marked_at": dockerfile_path.stat().st_mtime,
        }

        invalid_marker.write_text(json.dumps(marker_data, indent=2))
        logger.debug(f"Marked as invalid: {dockerfile_path.name} (reason: {reason})")

    def standardize_file(
        self, dockerfile_path: Path, labels_map: dict, output_dir: Path
    ) -> StandardizedFile | None:
        """Standardize a single Dockerfile"""
        try:
            content = dockerfile_path.read_text(errors="ignore")

            # Validate
            is_valid, reason = self.is_valid_dockerfile(content)
            if not is_valid:
                logger.debug(f"Skipping {dockerfile_path.name}: {reason}")
                # Save invalid marker for files that are structurally invalid
                if reason in ["missing_from", "invalid_start"]:
                    self.save_invalid_marker(dockerfile_path, output_dir, reason)
                return None

            # Normalize
            normalized = self.normalize_content(content)

            # Deduplication check
            content_hash = self.compute_content_hash(normalized)
            if content_hash in self.seen_hashes:
                self.duplicate_count += 1
                logger.debug(f"Duplicate: {dockerfile_path.name}")
                return None

            self.seen_hashes.add(content_hash)

            # Quality filter
            labels = labels_map.get(dockerfile_path.name, {})
            passes_quality, reason = self.filter_quality(normalized, labels)
            if not passes_quality:
                logger.debug(f"Filtered {dockerfile_path.name}: {reason}")
                return None

            # Load metadata
            metadata = {}
            meta_path = dockerfile_path.with_suffix(dockerfile_path.suffix + ".meta.json")
            if meta_path.exists():
                try:
                    metadata = json.loads(meta_path.read_text())
                except Exception:
                    pass

            # Get file modification time for incremental processing
            source_mtime = dockerfile_path.stat().st_mtime

            # Create standardized record
            file_id = hashlib.sha256(dockerfile_path.name.encode()).hexdigest()[:16]

            return StandardizedFile(
                id=file_id,
                original_file=str(dockerfile_path),
                content_hash=content_hash,
                stack=labels.get("stack") or metadata.get("stack_hint"),
                size=len(normalized),
                line_count=len(normalized.splitlines()),
                normalized_content=normalized,
                metadata={
                    "repo": metadata.get("repo"),
                    "url": metadata.get("url"),
                    "quality_score": labels.get("quality_score"),
                    "smells": labels.get("smells", []),
                    "cmd_flags": labels.get("cmd_flags", {}),
                    "source_mtime": source_mtime,
                    "validation": "valid",
                },
            )

        except Exception as e:
            logger.error(f"Error standardizing {dockerfile_path}: {e}")
            return None

    def process_directory(self, input_dir: Path, output_dir: Path) -> dict[str, Any]:
        """Process all Dockerfiles"""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load existing index for incremental processing
        if self.incremental:
            self.load_existing_index(output_dir)

        # Load labels
        labels_map = self.load_labels(input_dir)

        # Find Dockerfiles
        dockerfiles = sorted(input_dir.glob("*.Dockerfile"))
        logger.info(f"Found {len(dockerfiles)} Dockerfiles in input directory")

        # Separate files that need processing
        files_to_process = []
        skipped_count = 0
        skipped_invalid_count = 0

        for dockerfile in dockerfiles:
            if self.is_marked_invalid(dockerfile, output_dir):
                skipped_invalid_count += 1
            elif self.needs_reprocessing(dockerfile, output_dir):
                files_to_process.append(dockerfile)
            else:
                skipped_count += 1

        if self.incremental:
            logger.info(
                f"Incremental mode: processing {len(files_to_process)} files, skipping {skipped_count} unchanged files, {skipped_invalid_count} invalid files"
            )
        else:
            logger.info(f"Full mode: processing all {len(files_to_process)} files")

        # Process files
        newly_standardized = []
        filtered_stats = Counter()

        for dockerfile in files_to_process:
            result = self.standardize_file(dockerfile, labels_map, output_dir)
            if result:
                newly_standardized.append(result)
            else:
                # Track why it was filtered
                if dockerfile.name in labels_map:
                    labels = labels_map[dockerfile.name]
                    if labels.get("quality_score", 1.0) < 0.2:
                        filtered_stats["low_quality"] += 1
                    else:
                        filtered_stats["invalid"] += 1
                else:
                    filtered_stats["invalid"] += 1

        logger.info(f"Processed {len(newly_standardized)} new/updated files")

        # Save newly standardized files
        for item in newly_standardized:
            # Save normalized Dockerfile
            output_file = output_dir / f"{item.id}.Dockerfile"
            output_file.write_text(item.normalized_content)

            # Save metadata
            meta_file = output_dir / f"{item.id}.meta.json"
            meta_data = {
                "id": item.id,
                "original_file": item.original_file,
                "content_hash": item.content_hash,
                "stack": item.stack,
                "size": item.size,
                "line_count": item.line_count,
                "metadata": item.metadata,
                "source_mtime": item.metadata.get("source_mtime"),
            }
            meta_file.write_text(json.dumps(meta_data, indent=2))

        # Merge with existing outputs for final index
        all_standardized = []
        processed_ids = {item.id for item in newly_standardized}

        # Add newly processed files
        all_standardized.extend(newly_standardized)

        # Add existing files that weren't reprocessed and still exist in input
        if self.incremental:
            input_file_paths = {str(df) for df in dockerfiles}
            for file_id, meta_data in self.existing_outputs.items():
                # Only keep if source file still exists and wasn't just reprocessed
                if (
                    file_id not in processed_ids
                    and meta_data.get("original_file") in input_file_paths
                ):
                    # Reconstruct StandardizedFile from metadata
                    dockerfile_file = output_dir / f"{file_id}.Dockerfile"
                    if dockerfile_file.exists():
                        try:
                            content = dockerfile_file.read_text()
                            existing_item = StandardizedFile(
                                id=file_id,
                                original_file=meta_data.get("original_file", ""),
                                content_hash=meta_data.get("content_hash", ""),
                                stack=meta_data.get("stack"),
                                size=meta_data.get("size", 0),
                                line_count=meta_data.get("line_count", 0),
                                normalized_content=content,
                                metadata=meta_data.get("metadata", {}),
                            )
                            all_standardized.append(existing_item)
                        except Exception as e:
                            logger.warning(f"Could not load existing file {file_id}: {e}")

        # Create index
        index = {
            "total_input": len(dockerfiles),
            "total_output": len(all_standardized),
            "newly_processed": len(newly_standardized),
            "skipped_unchanged": skipped_count,
            "skipped_invalid": skipped_invalid_count,
            "duplicates_removed": self.duplicate_count,
            "filtered": dict(filtered_stats),
            "by_stack": {},
            "files": [],
        }

        for item in all_standardized:
            stack = item.stack or "unknown"
            index["by_stack"][stack] = index["by_stack"].get(stack, 0) + 1

            index["files"].append(
                {
                    "id": item.id,
                    "stack": item.stack,
                    "size": item.size,
                    "quality_score": item.metadata.get("quality_score"),
                }
            )

        index_path = output_dir / "index.json"
        index_path.write_text(json.dumps(index, indent=2))

        # Summary report
        report = output_dir / "standardization_report.txt"
        with report.open("w") as f:
            f.write("Dataset Standardization Report\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Mode: {'Incremental' if self.incremental else 'Full'}\n")
            f.write(f"Input Dockerfiles: {index['total_input']}\n")
            f.write(f"Output (curated): {index['total_output']}\n")
            if self.incremental:
                f.write(f"Newly processed: {index['newly_processed']}\n")
                f.write(f"Skipped (unchanged): {index['skipped_unchanged']}\n")
                f.write(f"Skipped (invalid): {index['skipped_invalid']}\n")
            f.write(f"Duplicates removed: {index['duplicates_removed']}\n")
            f.write(f"Filtered: {sum(filtered_stats.values())}\n\n")
            f.write("Filtering breakdown:\n")
            for reason, count in filtered_stats.items():
                f.write(f"  {reason}: {count}\n")
            f.write("\nStack distribution:\n")
            for stack, count in sorted(index["by_stack"].items(), key=lambda x: -x[1]):
                f.write(f"  {stack}: {count}\n")

        logger.info("=" * 50)
        logger.info("Standardization complete:")
        logger.info(f"  Mode: {'Incremental' if self.incremental else 'Full'}")
        logger.info(f"  Input: {index['total_input']}")
        logger.info(f"  Output: {index['total_output']}")
        if self.incremental:
            logger.info(f"  Newly processed: {index['newly_processed']}")
            logger.info(f"  Skipped unchanged: {index['skipped_unchanged']}")
            logger.info(f"  Skipped invalid: {index['skipped_invalid']}")
        logger.info(f"  Duplicates: {index['duplicates_removed']}")
        logger.info(f"  Filtered: {sum(filtered_stats.values())}")
        logger.info(f"  By stack: {index['by_stack']}")
        logger.info(f"  Index: {index_path}")
        logger.info(f"  Report: {report}")

        return index


def main():
    parser = argparse.ArgumentParser(description="Standardize and curate Dockerfile dataset")
    parser.add_argument(
        "--input", type=Path, required=True, help="Input directory with raw Dockerfiles"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Output directory for curated data"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Process all files (disable incremental mode)",
    )

    args = parser.parse_args()

    if not args.input.exists():
        logger.error(f"Input directory not found: {args.input}")
        sys.exit(1)

    standardizer = DatasetStandardizer(incremental=not args.full)
    standardizer.process_directory(args.input, args.output)


if __name__ == "__main__":
    main()
