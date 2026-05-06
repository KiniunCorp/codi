#!/usr/bin/env python3
"""Download datasets from Cloudflare R2 storage.

This script downloads specific datasets from R2, verifies checksums,
and skips files that already exist locally with matching checksums.
"""

import argparse
import sys
from pathlib import Path

from r2_utils import (
    R2Config,
    calculate_checksum,
    console,
    download_file_with_progress,
    format_size,
    get_r2_client,
    list_r2_objects,
)
from rich.panel import Panel
from rich.table import Table

# Available datasets (includes colab-zip-files)
AVAILABLE_DATASETS = ["raw", "curated", "pairs", "splits", "colab-zip-files"]
DATA_ROOT = Path("data")


class DownloadStats:
    """Track statistics for download operation."""

    def __init__(self):
        self.downloaded = 0
        self.skipped = 0
        self.errors = 0
        self.bytes_downloaded = 0
        self.files_checked = 0

    def __str__(self) -> str:
        return (
            f"Downloaded: {self.downloaded}, "
            f"Skipped: {self.skipped}, "
            f"Errors: {self.errors}, "
            f"Size: {format_size(self.bytes_downloaded)}"
        )


def should_download_file(
    local_path: Path, remote_metadata: dict, verify_checksum: bool = True
) -> bool:
    """Check if a file should be downloaded.

    Args:
        local_path: Local file path
        remote_metadata: Remote file metadata from R2
        verify_checksum: Whether to verify checksum

    Returns:
        bool: True if file should be downloaded
    """
    # Download if file doesn't exist
    if not local_path.exists():
        return True

    # Download if sizes don't match
    local_size = local_path.stat().st_size
    remote_size = remote_metadata.get("Size", 0)
    if local_size != remote_size:
        return True

    # If checksum verification disabled, skip download
    if not verify_checksum:
        return False

    # Download if checksum doesn't match (if available)
    remote_checksum = remote_metadata.get("Metadata", {}).get("sha256")
    if remote_checksum:
        local_checksum = calculate_checksum(local_path)
        if local_checksum != remote_checksum:
            return True

    return False


def download_dataset(
    client,
    bucket: str,
    r2_prefix: str,
    local_dir: Path,
    stats: DownloadStats,
    dry_run: bool = False,
    verify_checksum: bool = True,
    force: bool = False,
) -> list[dict]:
    """Download a dataset from R2 to local directory.

    Args:
        client: boto3 S3 client
        bucket: R2 bucket name
        r2_prefix: R2 key prefix (directory path in bucket)
        local_dir: Local destination directory
        stats: DownloadStats object to update
        dry_run: If True, don't actually download files
        verify_checksum: If True, verify checksums after download
        force: If True, download all files even if they exist locally

    Returns:
        list: List of file metadata dictionaries
    """
    console.print(f"\n[bold cyan]📥 Downloading: {r2_prefix} → {local_dir}[/bold cyan]")

    # List objects in R2
    try:
        objects = list_r2_objects(client, bucket, r2_prefix)
    except Exception as e:
        console.print(f"[red]❌ Error listing objects in {r2_prefix}: {e}[/red]")
        return []

    if not objects:
        console.print(f"[yellow]⚠️  No files found in {r2_prefix}[/yellow]")
        return []

    console.print(f"[dim]Found {len(objects)} file(s)[/dim]")

    file_manifests = []

    for obj in objects:
        stats.files_checked += 1

        r2_key = obj["Key"]
        file_size = obj["Size"]

        # Skip if it's a directory marker
        if r2_key.endswith("/"):
            continue

        # Calculate local path
        # Remove the prefix to get relative path
        rel_path = r2_key.replace(r2_prefix + "/", "", 1)
        local_path = local_dir / rel_path

        # Get full metadata (including custom metadata)
        try:
            from r2_utils import get_object_metadata

            metadata = get_object_metadata(client, bucket, r2_key)
        except Exception as e:
            console.print(f"[yellow]⚠️  Error getting metadata for {r2_key}: {e}[/yellow]")
            metadata = {"size": file_size, "metadata": {}}

        # Check if we should download
        skip_download = False
        if not force and local_path.exists():
            if not should_download_file(local_path, metadata, verify_checksum):
                console.print(f"[dim]⏭️  Skipped (exists): {rel_path}[/dim]")
                stats.skipped += 1
                skip_download = True

        # Download file if needed
        if not skip_download:
            if dry_run:
                console.print(
                    f"[blue]🔍 Would download: {rel_path} ({format_size(file_size)})[/blue]"
                )
                stats.downloaded += 1
                stats.bytes_downloaded += file_size
            else:
                try:
                    # Create parent directories
                    local_path.parent.mkdir(parents=True, exist_ok=True)

                    # Download file
                    download_file_with_progress(
                        client,
                        bucket,
                        r2_key,
                        local_path,
                        verify_checksum=verify_checksum,
                        show_progress=file_size > 1024 * 1024,  # Show progress for >1MB files
                    )

                    console.print(
                        f"[green]✅ Downloaded: {rel_path} ({format_size(file_size)})[/green]"
                    )
                    stats.downloaded += 1
                    stats.bytes_downloaded += file_size

                except Exception as e:
                    console.print(f"[red]❌ Error downloading {rel_path}: {e}[/red]")
                    stats.errors += 1
                    continue

        # Add to manifest
        file_manifests.append(
            {
                "r2_key": r2_key,
                "local_path": str(local_path),
                "size": file_size,
                "checksum": metadata.get("metadata", {}).get("sha256"),
            }
        )

    return file_manifests


def print_summary(stats: DownloadStats, dry_run: bool = False):
    """Print a summary table of download results.

    Args:
        stats: DownloadStats object
        dry_run: Whether this was a dry run
    """
    table = Table(title="Download Summary" + (" (Dry Run)" if dry_run else ""))

    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right", style="green")

    table.add_row("Files Checked", str(stats.files_checked))
    table.add_row("Files Downloaded", str(stats.downloaded))
    table.add_row("Files Skipped", str(stats.skipped))
    table.add_row("Errors", str(stats.errors), style="red" if stats.errors > 0 else "green")
    table.add_row("Data Downloaded", format_size(stats.bytes_downloaded))

    console.print("\n")
    console.print(table)


def main():
    """Main entry point for download_from_r2 script."""
    parser = argparse.ArgumentParser(
        description="Download datasets from Cloudflare R2 storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download only splits (for training)
  python data/download_from_r2.py --datasets splits

  # Download multiple datasets (including colab-zip-files)
  python data/download_from_r2.py --datasets raw,colab-zip-files,splits

  # Download all available datasets
  python data/download_from_r2.py --datasets all

  # Dry run (show what would be downloaded)
  python data/download_from_r2.py --datasets splits --dry-run

  # Force download (skip existence check)
  python data/download_from_r2.py --datasets splits --force

  # Download to custom location
  python data/download_from_r2.py --datasets splits --output /tmp/data

Environment variables required:
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
        """,
    )

    parser.add_argument(
        "--datasets",
        type=str,
        required=True,
        help=f"Comma-separated list of datasets to download (available: {', '.join(AVAILABLE_DATASETS)}, all)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_ROOT,
        help="Output directory (default: data/)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without actually downloading",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Download all files, skipping existence check",
    )

    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip checksum verification after download",
    )

    args = parser.parse_args()

    # Parse datasets
    if args.datasets.lower() == "all":
        datasets = AVAILABLE_DATASETS
    else:
        datasets = [d.strip() for d in args.datasets.split(",")]

        # Validate dataset names
        invalid = [d for d in datasets if d not in AVAILABLE_DATASETS]
        if invalid:
            console.print(
                f"[red]❌ Invalid dataset(s): {', '.join(invalid)}[/red]\n"
                f"Available: {', '.join(AVAILABLE_DATASETS)}"
            )
            sys.exit(1)

    # Print header
    mode_str = "DRY RUN" if args.dry_run else "DOWNLOAD"
    console.print(
        Panel.fit(
            f"[bold cyan]CODI Data Download from R2[/bold cyan]\n\n"
            f"Mode: [bold yellow]{mode_str}[/bold yellow]\n"
            f"Datasets: [bold]{', '.join(datasets)}[/bold]\n"
            f"Output: [bold]{args.output}[/bold]",
            border_style="cyan",
        )
    )

    # Load R2 configuration
    try:
        config = R2Config.from_env()
        console.print("[green]✅ R2 configuration loaded[/green]")
        console.print(f"[dim]   Bucket: {config.bucket_name}[/dim]")
        console.print(f"[dim]   Endpoint: {config.endpoint_url}[/dim]")
    except ValueError as e:
        console.print(f"[red]❌ Configuration error: {e}[/red]")
        sys.exit(1)

    # Initialize R2 client
    try:
        client = get_r2_client(config)
        console.print("[green]✅ Connected to R2[/green]")
    except Exception as e:
        console.print(f"[red]❌ Failed to connect to R2: {e}[/red]")
        sys.exit(1)

    # Download each dataset
    stats = DownloadStats()
    all_file_manifests = []

    for dataset_name in datasets:
        local_dir = args.output / dataset_name
        r2_prefix = f"datasets/{dataset_name}"

        manifests = download_dataset(
            client,
            config.bucket_name,
            r2_prefix,
            local_dir,
            stats,
            dry_run=args.dry_run,
            verify_checksum=not args.no_verify,
            force=args.force,
        )

        all_file_manifests.extend(manifests)

    # Print summary
    print_summary(stats, args.dry_run)

    # Exit with error code if there were errors
    if stats.errors > 0:
        console.print(f"\n[yellow]⚠️  Completed with {stats.errors} error(s)[/yellow]")
        sys.exit(1)
    else:
        console.print("\n[bold green]✅ Download completed successfully![/bold green]")
        sys.exit(0)


if __name__ == "__main__":
    main()
