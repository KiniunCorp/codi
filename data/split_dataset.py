#!/usr/bin/env python3
"""
Dataset Splitting Tool

Splits training pairs into train/val/test sets with stratification by stack.

Usage:
    python3 split_dataset.py --input data/pairs/ --output data/splits/ --seed 42
"""

import argparse
import json
import logging
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class DatasetSplitter:
    """Splits dataset with stratification"""

    def __init__(
        self,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        seed: int = 42,
        incremental: bool = True,
    ):
        if not abs(train_ratio + val_ratio + test_ratio - 1.0) < 0.01:
            raise ValueError("Split ratios must sum to 1.0")

        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.seed = seed
        self.incremental = incremental

        random.seed(seed)

    def load_pairs(self, pairs_file: Path) -> list[dict]:
        """Load training pairs from JSONL"""
        pairs = []

        try:
            with pairs_file.open() as f:
                for line_no, line in enumerate(f, 1):
                    if line.strip():
                        try:
                            pair = json.loads(line)
                            pairs.append(pair)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Invalid JSON at line {line_no}: {e}")

            logger.info(f"Loaded {len(pairs)} training pairs")
            return pairs

        except Exception as e:
            logger.error(f"Error loading pairs: {e}")
            return []

    def load_existing_splits(self, output_dir: Path) -> dict[str, set[str]]:
        """Load existing split assignments (returns dict of split_name -> set of IDs)"""
        splits = {"train": set(), "val": set(), "test": set()}

        for split_name in ["train", "val", "test"]:
            split_file = output_dir / f"{split_name}.jsonl"
            if split_file.exists():
                try:
                    with split_file.open() as f:
                        for line in f:
                            if line.strip():
                                pair = json.loads(line)
                                splits[split_name].add(pair["id"])
                except Exception as e:
                    logger.warning(f"Error loading {split_name} split: {e}")

        total_existing = sum(len(s) for s in splits.values())
        if total_existing > 0:
            logger.info(
                f"Found existing splits: train={len(splits['train'])}, val={len(splits['val'])}, test={len(splits['test'])}"
            )

        return splits

    def stratify_split(
        self, pairs: list[dict], key: str = "stack"
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """Split with stratification by given key"""
        # Group by stratification key
        groups = defaultdict(list)
        for pair in pairs:
            group_key = pair.get("metadata", {}).get(key, "unknown")
            groups[group_key].append(pair)

        train_set = []
        val_set = []
        test_set = []

        for group_key, group_pairs in groups.items():
            # Shuffle within group
            shuffled = group_pairs.copy()
            random.shuffle(shuffled)

            n = len(shuffled)
            train_end = int(n * self.train_ratio)
            val_end = train_end + int(n * self.val_ratio)

            train_set.extend(shuffled[:train_end])
            val_set.extend(shuffled[train_end:val_end])
            test_set.extend(shuffled[val_end:])

            logger.info(
                f"  {group_key}: {len(shuffled[:train_end])} train, "
                f"{len(shuffled[train_end:val_end])} val, "
                f"{len(shuffled[val_end:])} test"
            )

        # Final shuffle
        random.shuffle(train_set)
        random.shuffle(val_set)
        random.shuffle(test_set)

        return train_set, val_set, test_set

    def compute_statistics(self, splits: dict[str, list[dict]]) -> dict[str, Any]:
        """Compute statistics for each split"""
        stats = {}

        for split_name, split_data in splits.items():
            stack_counts = Counter(
                pair.get("metadata", {}).get("stack", "unknown") for pair in split_data
            )
            task_counts = Counter(
                pair.get("metadata", {}).get("task", "unknown") for pair in split_data
            )

            stats[split_name] = {
                "count": len(split_data),
                "by_stack": dict(stack_counts),
                "by_task": dict(task_counts),
            }

        return stats

    def save_split(self, split_data: list[dict], output_file: Path):
        """Save split to JSONL file"""
        try:
            with output_file.open("w") as f:
                for pair in split_data:
                    f.write(json.dumps(pair) + "\n")
            logger.info(f"Saved {len(split_data)} pairs to {output_file}")
        except Exception as e:
            logger.error(f"Error saving split: {e}")

    def verify_no_leakage(self, train: list[dict], val: list[dict], test: list[dict]) -> bool:
        """Verify no data leakage between splits"""
        train_ids = {p["id"] for p in train}
        val_ids = {p["id"] for p in val}
        test_ids = {p["id"] for p in test}

        train_val_overlap = train_ids & val_ids
        train_test_overlap = train_ids & test_ids
        val_test_overlap = val_ids & test_ids

        if train_val_overlap or train_test_overlap or val_test_overlap:
            logger.error("Data leakage detected!")
            logger.error(f"  Train-Val overlap: {len(train_val_overlap)}")
            logger.error(f"  Train-Test overlap: {len(train_test_overlap)}")
            logger.error(f"  Val-Test overlap: {len(val_test_overlap)}")
            return False

        logger.info("✓ No data leakage detected")
        return True

    def process(self, pairs_file: Path, output_dir: Path) -> dict[str, Any]:
        """Process pairs and create splits"""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load pairs
        all_pairs = self.load_pairs(pairs_file)
        if not all_pairs:
            logger.error("No pairs to split")
            sys.exit(1)

        logger.info(f"Total pairs: {len(all_pairs)}")
        logger.info(
            f"  Ratios: train={self.train_ratio}, val={self.val_ratio}, test={self.test_ratio}"
        )

        if self.incremental:
            # Load existing split assignments
            existing_splits = self.load_existing_splits(output_dir)
            all_existing_ids = set().union(*existing_splits.values())

            # Identify new pairs that need to be assigned
            new_pairs = [p for p in all_pairs if p["id"] not in all_existing_ids]
            existing_pairs_dict = {p["id"]: p for p in all_pairs if p["id"] in all_existing_ids}

            logger.info(
                f"Incremental mode: {len(new_pairs)} new pairs to assign, {len(existing_pairs_dict)} existing"
            )

            if len(new_pairs) == 0:
                logger.info("No new pairs to split - using existing splits")
                train = [
                    existing_pairs_dict[pid]
                    for pid in existing_splits["train"]
                    if pid in existing_pairs_dict
                ]
                val = [
                    existing_pairs_dict[pid]
                    for pid in existing_splits["val"]
                    if pid in existing_pairs_dict
                ]
                test = [
                    existing_pairs_dict[pid]
                    for pid in existing_splits["test"]
                    if pid in existing_pairs_dict
                ]
            else:
                # Split only the new pairs
                logger.info(f"Splitting {len(new_pairs)} new pairs...")
                new_train, new_val, new_test = self.stratify_split(new_pairs, key="stack")

                # Merge with existing splits
                train = [
                    existing_pairs_dict[pid]
                    for pid in existing_splits["train"]
                    if pid in existing_pairs_dict
                ] + new_train
                val = [
                    existing_pairs_dict[pid]
                    for pid in existing_splits["val"]
                    if pid in existing_pairs_dict
                ] + new_val
                test = [
                    existing_pairs_dict[pid]
                    for pid in existing_splits["test"]
                    if pid in existing_pairs_dict
                ] + new_test

                logger.info(
                    f"New split assignment: +{len(new_train)} train, +{len(new_val)} val, +{len(new_test)} test"
                )
        else:
            # Full mode: resplit everything
            logger.info(f"Full mode: splitting all {len(all_pairs)} pairs...")
            train, val, test = self.stratify_split(all_pairs, key="stack")

        logger.info(f"Final split sizes: train={len(train)}, val={len(val)}, test={len(test)}")

        # Verify no leakage
        if not self.verify_no_leakage(train, val, test):
            logger.error("Leakage verification failed!")
            sys.exit(1)

        # Save splits (overwrite with complete splits)
        self.save_split(train, output_dir / "train.jsonl")
        self.save_split(val, output_dir / "val.jsonl")
        self.save_split(test, output_dir / "test.jsonl")

        # Compute and save statistics
        splits = {"train": train, "val": val, "test": test}
        stats = self.compute_statistics(splits)

        stats_with_meta = {
            "mode": "incremental" if self.incremental else "full",
            "seed": self.seed,
            "ratios": {
                "train": self.train_ratio,
                "val": self.val_ratio,
                "test": self.test_ratio,
            },
            "total_pairs": len(all_pairs),
            "splits": stats,
        }

        stats_path = output_dir / "stats.json"
        stats_path.write_text(json.dumps(stats_with_meta, indent=2))

        # Create readable report
        report_path = output_dir / "split_report.txt"
        with report_path.open("w") as f:
            f.write("Dataset Split Report\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Mode: {'Incremental' if self.incremental else 'Full'}\n")
            f.write(f"Total pairs: {len(all_pairs)}\n")
            f.write(f"Seed: {self.seed}\n")
            f.write(
                f"Ratios: {self.train_ratio:.1%} / {self.val_ratio:.1%} / {self.test_ratio:.1%}\n\n"
            )

            for split_name in ["train", "val", "test"]:
                split_stats = stats[split_name]
                f.write(f"{split_name.upper()}:\n")
                f.write(f"  Total: {split_stats['count']}\n")
                f.write("  By stack:\n")
                for stack, count in sorted(split_stats["by_stack"].items()):
                    pct = (count / split_stats["count"]) * 100
                    f.write(f"    {stack}: {count} ({pct:.1f}%)\n")
                f.write("  By task:\n")
                for task, count in sorted(split_stats["by_task"].items()):
                    pct = (count / split_stats["count"]) * 100
                    f.write(f"    {task}: {count} ({pct:.1f}%)\n")
                f.write("\n")

        logger.info("=" * 50)
        logger.info("Dataset splitting complete:")
        logger.info(f"  Mode: {'Incremental' if self.incremental else 'Full'}")
        logger.info(f"  Train: {len(train)} pairs ({self.train_ratio:.1%})")
        logger.info(f"  Val: {len(val)} pairs ({self.val_ratio:.1%})")
        logger.info(f"  Test: {len(test)} pairs ({self.test_ratio:.1%})")
        logger.info(f"  Stats: {stats_path}")
        logger.info(f"  Report: {report_path}")

        return stats_with_meta


def main():
    parser = argparse.ArgumentParser(description="Split training pairs into train/val/test")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/pairs/training_pairs.jsonl"),
        help="Input pairs file (JSONL)",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/splits/"), help="Output directory"
    )
    parser.add_argument(
        "--train-ratio", type=float, default=0.7, help="Train set ratio (default: 0.7)"
    )
    parser.add_argument(
        "--val-ratio", type=float, default=0.15, help="Validation set ratio (default: 0.15)"
    )
    parser.add_argument(
        "--test-ratio", type=float, default=0.15, help="Test set ratio (default: 0.15)"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Resplit all pairs (disable incremental mode)",
    )

    args = parser.parse_args()

    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)

    splitter = DatasetSplitter(
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
        incremental=not args.full,
    )

    splitter.process(args.input, args.output)


if __name__ == "__main__":
    main()
