"""
Compression handlers for backup archives.

Supports multiple formats:
- zip: Standard zip compression
- tar.gz: Gzip compressed tar
- tar.bz2: Bzip2 compressed tar
- tar.xz: LZMA compressed tar
- none: No compression (tar only)
"""

import os
import tarfile
import zipfile
from pathlib import Path
from typing import List
from datetime import datetime


class CompressionError(Exception):
    """Raised when archive creation fails."""
    pass


def create_archive(
    source_paths: List[str],
    output_path: str,
    compression_format: str = 'tar.gz'
) -> str:
    """
    Create a compressed archive from source paths.

    Args:
        source_paths: List of file/directory paths to include in archive
        output_path: Path where archive should be created (without extension)
        compression_format: Format to use ('zip', 'tar.gz', 'tar.bz2', 'tar.xz', 'none')

    Returns:
        Full path to the created archive file

    Raises:
        CompressionError: If archive creation fails
        ValueError: If compression_format is invalid
    """
    # Validate inputs
    if not source_paths:
        raise CompressionError("No source paths provided")

    # Map format to extension and handler
    format_map = {
        'zip': ('zip', _create_zip),
        'tar.gz': ('tar.gz', _create_tar),
        'tar.bz2': ('tar.bz2', _create_tar),
        'tar.xz': ('tar.xz', _create_tar),
        'none': ('tar', _create_tar)
    }

    if compression_format not in format_map:
        raise ValueError(
            f"Invalid compression format: {compression_format}. "
            f"Valid options: {list(format_map.keys())}"
        )

    extension, handler = format_map[compression_format]
    archive_path = f"{output_path}.{extension}"

    try:
        handler(source_paths, archive_path, compression_format)
        return archive_path
    except Exception as e:
        # Clean up partial archive on failure
        if os.path.exists(archive_path):
            try:
                os.remove(archive_path)
            except:
                pass
        raise CompressionError(f"Failed to create archive: {e}")


def _create_zip(source_paths: List[str], archive_path: str, compression_format: str):
    """
    Create a ZIP archive.

    Args:
        source_paths: List of paths to include
        archive_path: Output archive path
        compression_format: Not used for zip, kept for interface consistency
    """
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for source_path in source_paths:
            source = Path(source_path)

            if source.is_file():
                # Add single file
                zipf.write(source, source.name)
            elif source.is_dir():
                # Add directory recursively
                _add_directory_to_zip(zipf, source, source.name)
            else:
                raise CompressionError(f"Invalid path type: {source_path}")


def _add_directory_to_zip(zipf: zipfile.ZipFile, directory: Path, arcname: str):
    """
    Recursively add directory to zip archive.

    Args:
        zipf: ZipFile object
        directory: Directory to add
        arcname: Archive name for the directory
    """
    for item in directory.rglob('*'):
        if item.is_file():
            # Calculate relative path within archive
            relative_path = item.relative_to(directory.parent)
            zipf.write(item, relative_path)


def _create_tar(source_paths: List[str], archive_path: str, compression_format: str):
    """
    Create a TAR archive with optional compression.

    Args:
        source_paths: List of paths to include
        archive_path: Output archive path
        compression_format: Compression format ('tar.gz', 'tar.bz2', 'tar.xz', 'none')
    """
    # Map format to tarfile mode
    mode_map = {
        'tar.gz': 'w:gz',
        'tar.bz2': 'w:bz2',
        'tar.xz': 'w:xz',
        'none': 'w'
    }

    mode = mode_map.get(compression_format, 'w:gz')

    with tarfile.open(archive_path, mode) as tar:
        for source_path in source_paths:
            source = Path(source_path)

            if not source.exists():
                raise CompressionError(f"Path does not exist: {source_path}")

            # Add to archive with just the basename as arcname
            # This prevents deep directory structures in the archive
            arcname = source.name
            tar.add(source, arcname=arcname, recursive=True)


def generate_archive_filename(job_name: str, compression_format: str) -> str:
    """
    Generate a standardized archive filename.

    Format: {job_name}_{YYYYMMDD_HHMMSS}.{ext}

    Args:
        job_name: Name of the backup job
        compression_format: Compression format

    Returns:
        Filename (without path)
    """
    # Generate timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Map format to extension
    extension_map = {
        'zip': 'zip',
        'tar.gz': 'tar.gz',
        'tar.bz2': 'tar.bz2',
        'tar.xz': 'tar.xz',
        'none': 'tar'
    }

    extension = extension_map.get(compression_format, 'tar.gz')

    # Sanitize job name (replace spaces and special chars with underscores)
    safe_job_name = "".join(
        c if c.isalnum() or c in ('-', '_') else '_'
        for c in job_name
    )

    return f"{safe_job_name}-{timestamp}.{extension}"


def strip_archive_extension(filename: str) -> str:
    """
    Strip archive extension from filename.

    Handles multi-part extensions like .tar.gz, .tar.bz2, .tar.xz

    Args:
        filename: Archive filename with extension

    Returns:
        Filename without extension
    """
    if filename.endswith('.tar.gz'):
        return filename[:-7]
    elif filename.endswith('.tar.bz2'):
        return filename[:-8]
    elif filename.endswith('.tar.xz'):
        return filename[:-7]
    elif filename.endswith('.zip'):
        return filename[:-4]
    elif filename.endswith('.tar'):
        return filename[:-4]
    else:
        # Fallback to standard splitext
        return os.path.splitext(filename)[0]


def get_archive_size(archive_path: str) -> int:
    """
    Get the size of an archive file in bytes.

    Args:
        archive_path: Path to the archive file

    Returns:
        File size in bytes

    Raises:
        CompressionError: If file doesn't exist or cannot be accessed
    """
    try:
        return os.path.getsize(archive_path)
    except FileNotFoundError:
        raise CompressionError(f"Archive not found: {archive_path}")
    except Exception as e:
        raise CompressionError(f"Failed to get archive size: {e}")
