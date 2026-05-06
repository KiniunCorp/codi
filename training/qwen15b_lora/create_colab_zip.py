#!/usr/bin/env python3
"""
Script to create a ZIP file for Google Colab training.
Creates: data/colab-zip-files/codi-YYYYMMDD.zip (or codi-YYYYMMDD-full.zip)

Usage:
    python create_colab_zip.py              # Essential files only
    python create_colab_zip.py --full       # Include optional files (adds -full suffix)
    python create_colab_zip.py --output custom.zip  # Custom output name
"""

import argparse
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


class ColabZipCreator:
    """Creates a ZIP file with training data for Google Colab."""

    def __init__(self, repo_root: Path, output_path: Path, include_optional: bool = False):
        self.repo_root = repo_root
        self.output_path = output_path
        self.include_optional = include_optional
        self.files_copied = []
        self.files_missing = []

    def add_file(self, source_rel: str, dest_rel: str, required: bool = True) -> bool:
        """Add a file to the staging directory."""
        source = self.repo_root / source_rel
        dest = self.staging_dir / dest_rel

        if source.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            self.files_copied.append(dest_rel)
            return True
        else:
            if required:
                self.files_missing.append(source_rel)
            return False

    def create_zip(self, staging_dir: Path):
        """Create ZIP file from staging directory."""
        self.staging_dir = staging_dir
        staging_codi = staging_dir / "codi"
        staging_codi.mkdir(parents=True, exist_ok=True)

        print("📦 CODI Colab Training ZIP Creator")
        print("=" * 60)
        print(f"Repository root: {self.repo_root}")
        print(f"Output file: {self.output_path}")
        print()

        # Essential files
        print("📋 Copying essential files...")
        self.add_file("data/splits/train.jsonl", "codi/data/splits/train.jsonl")
        self.add_file("data/splits/val.jsonl", "codi/data/splits/val.jsonl")
        self.add_file("training/qwen15b_lora/config.yaml", "codi/training/qwen15b_lora/config.yaml")
        self.add_file("training/qwen15b_lora/train.py", "codi/training/qwen15b_lora/train.py")

        # Recommended files
        print("📋 Copying recommended files...")
        self.add_file("patterns/rules.yml", "codi/patterns/rules.yml", required=False)
        self.add_file("data/splits/stats.json", "codi/data/splits/stats.json", required=False)
        self.add_file(
            "training/qwen15b_lora/README.md",
            "codi/training/qwen15b_lora/README.md",
            required=False,
        )

        # Optional files
        if self.include_optional:
            print("📋 Including optional files (--full mode)...")
            self.add_file("data/splits/test.jsonl", "codi/data/splits/test.jsonl", required=False)
            self.add_file("README.md", "codi/README.md", required=False)
            self.add_file(
                "training/qwen15b_lora/train_colab.ipynb",
                "codi/training/qwen15b_lora/train_colab.ipynb",
                required=False,
            )

        print()

        # Report missing files
        if self.files_missing:
            print("⚠️  Missing required files:")
            for file in self.files_missing:
                print(f"  - {file}")
            print()

        # Create ZIP
        print("🗜️  Creating ZIP archive...")
        with zipfile.ZipFile(self.output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _dirs, files in os.walk(staging_codi):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(staging_dir)
                    zipf.write(file_path, arcname)

        # Calculate statistics
        zip_size_mb = self.output_path.stat().st_size / (1024 * 1024)

        print()
        print("✅ ZIP file created successfully!")
        print("=" * 60)
        print(f"File: {self.output_path}")
        print(f"Size: {zip_size_mb:.2f} MB")
        print()

        # List contents
        print("📁 Contents:")
        for file in sorted(self.files_copied):
            print(f"  ✓ {file}")
        print()

        # Statistics
        print("📊 Statistics:")
        print(f"  Total files: {len(self.files_copied)}")

        train_file = self.repo_root / "data/splits/train.jsonl"
        if train_file.exists():
            train_lines = sum(1 for _ in open(train_file))
            print(f"  Training examples: {train_lines:,}")

        val_file = self.repo_root / "data/splits/val.jsonl"
        if val_file.exists():
            val_lines = sum(1 for _ in open(val_file))
            print(f"  Validation examples: {val_lines:,}")

        print()
        print("📝 Usage:")
        print(f"  1. Find ZIP at: {self.output_path.relative_to(self.repo_root)}")
        print(f"  2. Upload {self.output_path.name} to Google Colab")
        print("  3. Use Option A in notebook cell 7 to extract")
        print("  4. Run cells sequentially to start training")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Create a ZIP file for CODI training on Google Colab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python create_colab_zip.py                     # Creates data/colab-zip-files/codi-YYYYMMDD.zip
  python create_colab_zip.py --full              # Creates data/colab-zip-files/codi-YYYYMMDD-full.zip
  python create_colab_zip.py --output custom.zip # Custom output filename
        """,
    )
    parser.add_argument(
        "--full", action="store_true", help="Include optional files (test.jsonl, notebooks, etc.)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Custom output filename (default: data/colab-zip-files/codi-YYYYMMDD.zip)",
    )

    args = parser.parse_args()

    # Determine repository root
    script_dir = Path(__file__).parent.resolve()
    repo_root = script_dir.parent.parent

    # Determine output path
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = repo_root / output_path
    else:
        timestamp = datetime.now().strftime("%Y%m%d")
        # Create output directory
        output_dir = repo_root / "data" / "colab-zip-files"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Add -full suffix if full mode
        suffix = "-full" if args.full else ""
        output_path = output_dir / f"codi-{timestamp}{suffix}.zip"

    # Create temporary staging directory
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        staging_dir = Path(temp_dir)

        # Create ZIP
        creator = ColabZipCreator(repo_root, output_path, args.full)
        creator.create_zip(staging_dir)

        # Check if any required files are missing
        if creator.files_missing:
            print("❌ Some required files are missing!")
            print("Please ensure you have prepared the training data:")
            print("  make data-prepare")
            return 1

    return 0


if __name__ == "__main__":
    exit(main())
