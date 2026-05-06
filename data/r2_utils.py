"""Cloudflare R2 storage utilities for CODI.

This module provides core functionality for interacting with Cloudflare R2 storage,
including upload, download, and checksum verification.
"""

import hashlib
import os
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

console = Console()


class R2Config:
    """Configuration for Cloudflare R2 storage."""

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        endpoint_url: str | None = None,
        region: str = "auto",
    ):
        self.account_id = account_id
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.bucket_name = bucket_name
        self.region = region

        # Construct endpoint URL if not provided
        if endpoint_url:
            self.endpoint_url = endpoint_url
        else:
            self.endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"

    @classmethod
    def from_env(cls) -> "R2Config":
        """Load R2 configuration from environment variables.

        Returns:
            R2Config: Configuration loaded from environment

        Raises:
            ValueError: If required environment variables are missing
        """
        load_dotenv()

        required_vars = [
            "R2_ACCOUNT_ID",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET_NAME",
        ]

        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}\n"
                "Create a .env file with: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME"
            )

        return cls(
            account_id=os.getenv("R2_ACCOUNT_ID"),
            access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            bucket_name=os.getenv("R2_BUCKET_NAME"),
            endpoint_url=os.getenv("R2_ENDPOINT_URL"),
            region=os.getenv("R2_REGION", "auto"),
        )


def get_r2_client(config: R2Config | None = None):
    """Initialize and return a boto3 S3 client configured for Cloudflare R2.

    Args:
        config: R2 configuration. If None, loads from environment variables.

    Returns:
        boto3.client: Configured S3 client for R2

    Raises:
        ValueError: If configuration is invalid
    """
    if config is None:
        config = R2Config.from_env()

    client = boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name=config.region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )

    return client


def calculate_checksum(file_path: Path, algorithm: str = "sha256") -> str:
    """Calculate checksum for a file.

    Args:
        file_path: Path to file
        algorithm: Hash algorithm (default: sha256)

    Returns:
        str: Hexadecimal checksum string

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    hash_obj = hashlib.new(algorithm)

    with open(file_path, "rb") as f:
        # Read in chunks to handle large files
        for chunk in iter(lambda: f.read(8192), b""):
            hash_obj.update(chunk)

    return hash_obj.hexdigest()


def file_exists_in_r2(
    client,
    bucket: str,
    key: str,
    local_checksum: str | None = None,
) -> bool:
    """Check if a file exists in R2 and optionally verify its checksum.

    Args:
        client: boto3 S3 client
        bucket: R2 bucket name
        key: Object key in R2
        local_checksum: Optional local file checksum to compare

    Returns:
        bool: True if file exists (and checksums match if provided)
    """
    try:
        response = client.head_object(Bucket=bucket, Key=key)

        # If no checksum provided, just check existence
        if local_checksum is None:
            return True

        # Compare checksums (stored in metadata)
        remote_checksum = response.get("Metadata", {}).get("sha256")
        if remote_checksum:
            return remote_checksum == local_checksum

        # If no checksum metadata, compare ETags (less reliable but better than nothing)
        etag = response.get("ETag", "").strip('"')
        return etag == local_checksum

    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def upload_file_with_progress(
    client,
    local_path: Path,
    bucket: str,
    key: str,
    metadata: dict[str, str] | None = None,
    show_progress: bool = True,
) -> bool:
    """Upload a file to R2 with progress bar.

    Args:
        client: boto3 S3 client
        local_path: Local file path
        bucket: R2 bucket name
        key: Object key in R2
        metadata: Optional metadata to attach to object
        show_progress: Whether to show progress bar

    Returns:
        bool: True if upload successful

    Raises:
        FileNotFoundError: If local file doesn't exist
        ClientError: If upload fails
    """
    if not local_path.exists():
        raise FileNotFoundError(f"File not found: {local_path}")

    file_size = local_path.stat().st_size

    # Calculate checksum and add to metadata
    checksum = calculate_checksum(local_path)
    if metadata is None:
        metadata = {}
    metadata["sha256"] = checksum

    if show_progress and file_size > 1024 * 1024:  # Show progress for files >1MB
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Uploading {local_path.name}", total=file_size)

            def callback(bytes_transferred):
                progress.update(task, advance=bytes_transferred)

            client.upload_file(
                str(local_path),
                bucket,
                key,
                Callback=callback,
                ExtraArgs={"Metadata": metadata},
            )
    else:
        # Upload without progress bar for small files
        client.upload_file(
            str(local_path),
            bucket,
            key,
            ExtraArgs={"Metadata": metadata},
        )

    return True


def download_file_with_progress(
    client,
    bucket: str,
    key: str,
    local_path: Path,
    verify_checksum: bool = True,
    show_progress: bool = True,
) -> bool:
    """Download a file from R2 with progress bar and optional checksum verification.

    Args:
        client: boto3 S3 client
        bucket: R2 bucket name
        key: Object key in R2
        local_path: Local destination path
        verify_checksum: Whether to verify checksum after download
        show_progress: Whether to show progress bar

    Returns:
        bool: True if download successful and checksum matches (if verified)

    Raises:
        ClientError: If download fails
        ValueError: If checksum verification fails
    """
    # Get object metadata first
    try:
        response = client.head_object(Bucket=bucket, Key=key)
        file_size = response["ContentLength"]
        remote_checksum = response.get("Metadata", {}).get("sha256")
    except ClientError as e:
        console.print(f"[red]Error accessing {key}: {e}[/red]")
        raise

    # Create parent directories if needed
    local_path.parent.mkdir(parents=True, exist_ok=True)

    if show_progress and file_size > 1024 * 1024:  # Show progress for files >1MB
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Downloading {local_path.name}", total=file_size)

            def callback(bytes_transferred):
                progress.update(task, advance=bytes_transferred)

            client.download_file(bucket, key, str(local_path), Callback=callback)
    else:
        # Download without progress bar for small files
        client.download_file(bucket, key, str(local_path))

    # Verify checksum if requested and available
    if verify_checksum and remote_checksum:
        local_checksum = calculate_checksum(local_path)
        if local_checksum != remote_checksum:
            local_path.unlink()  # Delete corrupted file
            raise ValueError(
                f"Checksum mismatch for {key}:\n"
                f"  Expected: {remote_checksum}\n"
                f"  Got:      {local_checksum}"
            )

    return True


def list_r2_objects(
    client,
    bucket: str,
    prefix: str = "",
    max_keys: int = 1000,
) -> list[dict]:
    """List objects in an R2 bucket with a given prefix.

    Args:
        client: boto3 S3 client
        bucket: R2 bucket name
        prefix: Key prefix to filter by
        max_keys: Maximum number of keys to return per page

    Returns:
        list: List of object metadata dictionaries

    Raises:
        ClientError: If listing fails
    """
    objects = []
    continuation_token = None

    while True:
        params = {
            "Bucket": bucket,
            "Prefix": prefix,
            "MaxKeys": max_keys,
        }

        if continuation_token:
            params["ContinuationToken"] = continuation_token

        try:
            response = client.list_objects_v2(**params)
        except ClientError as e:
            console.print(f"[red]Error listing objects: {e}[/red]")
            raise

        # Add objects from this page
        if "Contents" in response:
            objects.extend(response["Contents"])

        # Check if there are more pages
        if not response.get("IsTruncated"):
            break

        continuation_token = response.get("NextContinuationToken")

    return objects


def get_object_metadata(client, bucket: str, key: str) -> dict | None:
    """Get metadata for an object in R2.

    Args:
        client: boto3 S3 client
        bucket: R2 bucket name
        key: Object key in R2

    Returns:
        dict: Object metadata, or None if object doesn't exist

    Raises:
        ClientError: If request fails (except 404)
    """
    try:
        response = client.head_object(Bucket=bucket, Key=key)
        return {
            "key": key,
            "size": response["ContentLength"],
            "last_modified": response["LastModified"],
            "etag": response["ETag"].strip('"'),
            "metadata": response.get("Metadata", {}),
        }
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return None
        raise


def format_size(bytes_size: int) -> str:
    """Format byte size to human-readable string.

    Args:
        bytes_size: Size in bytes

    Returns:
        str: Formatted size string (e.g., "1.5 MB")
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"
