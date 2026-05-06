#!/usr/bin/env python3
"""Upload local data directories to Cloudflare R2 storage.

This script syncs local data directories to R2, skipping files that already exist
with matching checksums. It generates a manifest file with checksums and timestamps.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from botocore.exceptions import ClientError
from r2_utils import (
    R2Config,
    calculate_checksum,
    console,
    file_exists_in_r2,
    format_size,
    get_r2_client,
    upload_file_with_progress,
)
from rich.panel import Panel
from rich.table import Table

# Default directories to sync (includes colab-zip-files)
DEFAULT_DIRECTORIES = ["raw", "curated", "pairs", "splits", "colab-zip-files"]
DATA_ROOT = Path("data")


class SyncStats:
    """Track statistics for sync operation."""

    def __init__(self):
        self.uploaded = 0
        self.skipped = 0
        self.errors = 0
        self.bytes_uploaded = 0
        self.files_checked = 0

    def __str__(self) -> str:
        return (
            f"Uploaded: {self.uploaded}, "
            f"Skipped: {self.skipped}, "
            f"Errors: {self.errors}, "
            f"Size: {format_size(self.bytes_uploaded)}"
        )


def sync_directory(
    client,
    bucket: str,
    local_dir: Path,
    r2_prefix: str,
    stats: SyncStats,
    dry_run: bool = False,
    force: bool = False,
) -> list[dict]:
    """Sync a local directory to R2.

    Args:
        client: boto3 S3 client
        bucket: R2 bucket name
        local_dir: Local directory path
        r2_prefix: R2 key prefix (directory path in bucket)
        stats: SyncStats object to update
        dry_run: If True, don't actually upload files
        force: If True, skip checksum check and upload all files

    Returns:
        list: List of file metadata dictionaries
    """
    if not local_dir.exists():
        console.print(f"[yellow]⚠️  Directory not found: {local_dir}[/yellow]")
        return []

    console.print(f"\n[bold cyan]📁 Syncing: {local_dir} → {r2_prefix}[/bold cyan]")

    file_manifests = []

    # Walk through directory
    for file_path in sorted(local_dir.rglob("*")):
        if not file_path.is_file():
            continue

        stats.files_checked += 1

        # Calculate relative path and R2 key
        rel_path = file_path.relative_to(local_dir)
        r2_key = f"{r2_prefix}/{rel_path}".replace("\\", "/")  # Handle Windows paths

        # Calculate checksum
        try:
            checksum = calculate_checksum(file_path)
        except Exception as e:
            console.print(f"[red]❌ Error calculating checksum for {file_path}: {e}[/red]")
            stats.errors += 1
            continue

        # Check if file exists in R2 with matching checksum
        skip_upload = False
        if not force:
            try:
                if file_exists_in_r2(client, bucket, r2_key, checksum):
                    console.print(f"[dim]⏭️  Skipped (unchanged): {rel_path}[/dim]")
                    stats.skipped += 1
                    skip_upload = True
            except ClientError as e:
                console.print(f"[yellow]⚠️  Error checking {r2_key}: {e}[/yellow]")
                # Continue with upload if we can't check

        # Upload file if needed
        if not skip_upload:
            file_size = file_path.stat().st_size

            if dry_run:
                console.print(
                    f"[blue]🔍 Would upload: {rel_path} ({format_size(file_size)})[/blue]"
                )
                stats.uploaded += 1
                stats.bytes_uploaded += file_size
            else:
                try:
                    metadata = {
                        "sha256": checksum,
                        "source_path": str(rel_path),
                        "upload_time": datetime.now(UTC).isoformat(),
                    }

                    upload_file_with_progress(
                        client,
                        file_path,
                        bucket,
                        r2_key,
                        metadata=metadata,
                        show_progress=file_size > 1024 * 1024,  # Show progress for >1MB files
                    )

                    console.print(
                        f"[green]✅ Uploaded: {rel_path} ({format_size(file_size)})[/green]"
                    )
                    stats.uploaded += 1
                    stats.bytes_uploaded += file_size

                except Exception as e:
                    console.print(f"[red]❌ Error uploading {rel_path}: {e}[/red]")
                    stats.errors += 1
                    continue

        # Add to manifest
        file_manifests.append(
            {
                "local_path": str(rel_path),
                "r2_key": r2_key,
                "size": file_path.stat().st_size,
                "checksum": checksum,
                "last_modified": datetime.fromtimestamp(
                    file_path.stat().st_mtime, tz=UTC
                ).isoformat(),
            }
        )

    return file_manifests


def generate_manifest(
    client,
    bucket: str,
    sync_stats: SyncStats,
    file_manifests: list[dict],
    dry_run: bool = False,
) -> str | None:
    """Generate and upload a manifest file with sync metadata.

    Args:
        client: boto3 S3 client
        bucket: R2 bucket name
        sync_stats: SyncStats object
        file_manifests: List of file metadata dictionaries
        dry_run: If True, don't actually upload manifest

    Returns:
        str: Manifest key in R2, or None if dry run
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    manifest_key = f"manifests/sync_{timestamp}.json"

    manifest = {
        "sync_time": datetime.now(UTC).isoformat(),
        "statistics": {
            "files_checked": sync_stats.files_checked,
            "files_uploaded": sync_stats.uploaded,
            "files_skipped": sync_stats.skipped,
            "errors": sync_stats.errors,
            "bytes_uploaded": sync_stats.bytes_uploaded,
        },
        "files": file_manifests,
    }

    # Save local copy
    manifest_dir = Path("data/manifests")
    manifest_dir.mkdir(exist_ok=True)
    local_manifest_path = manifest_dir / f"sync_{timestamp}.json"

    with open(local_manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"\n[bold green]📄 Manifest saved: {local_manifest_path}[/bold green]")

    if not dry_run:
        try:
            # Upload manifest to R2
            manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
            client.put_object(
                Bucket=bucket,
                Key=manifest_key,
                Body=manifest_bytes,
                ContentType="application/json",
                Metadata={
                    "sync_time": timestamp,
                    "files_uploaded": str(sync_stats.uploaded),
                },
            )
            console.print(f"[bold green]✅ Manifest uploaded: {manifest_key}[/bold green]")
            return manifest_key
        except Exception as e:
            console.print(f"[red]❌ Error uploading manifest: {e}[/red]")
            return None

    return None


def print_summary(stats: SyncStats, dry_run: bool = False):
    """Print a summary table of sync results.

    Args:
        stats: SyncStats object
        dry_run: Whether this was a dry run
    """
    table = Table(title="Sync Summary" + (" (Dry Run)" if dry_run else ""))

    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right", style="green")

    table.add_row("Files Checked", str(stats.files_checked))
    table.add_row("Files Uploaded", str(stats.uploaded))
    table.add_row("Files Skipped", str(stats.skipped))
    table.add_row("Errors", str(stats.errors), style="red" if stats.errors > 0 else "green")
    table.add_row("Data Uploaded", format_size(stats.bytes_uploaded))

    console.print("\n")
    console.print(table)


def main():
    """Main entry point for sync_to_r2 script."""
    parser = argparse.ArgumentParser(
        description="Upload local data directories to Cloudflare R2 storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync all default directories (including colab-zip-files)
  python data/sync_to_r2.py

  # Sync specific directories
  python data/sync_to_r2.py --directories raw,splits,colab-zip-files

  # Dry run (don't upload)
  python data/sync_to_r2.py --dry-run

  # Force upload (skip checksum check)
  python data/sync_to_r2.py --force

Environment variables required:
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
        """,
    )

    parser.add_argument(
        "--directories",
        type=str,
        default=",".join(DEFAULT_DIRECTORIES),
        help=f"Comma-separated list of directories to sync (default: {','.join(DEFAULT_DIRECTORIES)})",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without actually uploading",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Upload all files, skipping checksum comparison",
    )

    parser.add_argument(
        "--no-manifest",
        action="store_true",
        help="Don't generate or upload manifest file",
    )

    args = parser.parse_args()

    # Parse directories
    directories = [d.strip() for d in args.directories.split(",")]

    # Print header
    mode_str = "DRY RUN" if args.dry_run else "UPLOAD"
    console.print(
        Panel.fit(
            f"[bold cyan]CODI Data Sync to R2[/bold cyan]\n\n"
            f"Mode: [bold yellow]{mode_str}[/bold yellow]\n"
            f"Directories: [bold]{', '.join(directories)}[/bold]",
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

    # Sync each directory
    stats = SyncStats()
    all_file_manifests = []

    for dir_name in directories:
        local_dir = DATA_ROOT / dir_name
        r2_prefix = f"datasets/{dir_name}"

        dir_manifests = sync_directory(
            client,
            config.bucket_name,
            local_dir,
            r2_prefix,
            stats,
            dry_run=args.dry_run,
            force=args.force,
        )

        all_file_manifests.extend(dir_manifests)

    # Generate and upload manifest
    if not args.no_manifest and all_file_manifests:
        generate_manifest(client, config.bucket_name, stats, all_file_manifests, args.dry_run)

    # Print summary
    print_summary(stats, args.dry_run)

    # Exit with error code if there were errors
    if stats.errors > 0:
        console.print(f"\n[yellow]⚠️  Completed with {stats.errors} error(s)[/yellow]")
        sys.exit(1)
    else:
        console.print("\n[bold green]✅ Sync completed successfully![/bold green]")
        sys.exit(0)


if __name__ == "__main__":
    main()
