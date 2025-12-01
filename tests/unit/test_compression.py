"""
Unit tests for compression module (app/backup/compression.py).

Tests archive creation for all supported formats (zip, tar.gz, tar.bz2, tar.xz, none).
"""

import os
import tarfile
import zipfile
from pathlib import Path

import pytest

from app.backup.compression import (
    create_archive,
    generate_archive_filename,
    strip_archive_extension,
    get_archive_size,
    CompressionError
)


class TestCreateArchive:
    """Test create_archive function with different formats."""

    @pytest.mark.parametrize("compression_format,expected_extension", [
        ("zip", ".zip"),
        ("tar.gz", ".tar.gz"),
        ("tar.bz2", ".tar.bz2"),
        ("tar.xz", ".tar.xz"),
        ("none", ".tar"),
    ])
    def test_create_archive_all_formats(self, temp_files, tmp_path, compression_format, expected_extension):
        """Test creating archives in all supported formats."""
        output_path = str(tmp_path / "test_archive")

        archive_path = create_archive(
            [str(temp_files / "test_file1.txt")],
            output_path,
            compression_format
        )

        assert archive_path.endswith(expected_extension)
        assert os.path.exists(archive_path)
        assert os.path.getsize(archive_path) > 0

    def test_create_archive_single_file(self, temp_files, tmp_path):
        """Test creating archive from single file."""
        source_file = temp_files / "test_file1.txt"
        output_path = str(tmp_path / "single_file_archive")

        archive_path = create_archive(
            [str(source_file)],
            output_path,
            "tar.gz"
        )

        assert os.path.exists(archive_path)

        # Verify contents
        with tarfile.open(archive_path, 'r:gz') as tar:
            members = tar.getmembers()
            assert len(members) == 1
            assert members[0].name == "test_file1.txt"

    def test_create_archive_multiple_files(self, temp_files, tmp_path):
        """Test creating archive from multiple files."""
        files = [
            str(temp_files / "test_file1.txt"),
            str(temp_files / "test_file2.log")
        ]
        output_path = str(tmp_path / "multi_file_archive")

        archive_path = create_archive(files, output_path, "zip")

        assert os.path.exists(archive_path)

        # Verify contents
        with zipfile.ZipFile(archive_path, 'r') as zipf:
            names = zipf.namelist()
            assert "test_file1.txt" in names
            assert "test_file2.log" in names

    def test_create_archive_directory(self, temp_files, tmp_path):
        """Test creating archive from directory."""
        output_path = str(tmp_path / "dir_archive")

        archive_path = create_archive(
            [str(temp_files)],
            output_path,
            "tar.gz"
        )

        assert os.path.exists(archive_path)

        # Verify directory structure preserved
        with tarfile.open(archive_path, 'r:gz') as tar:
            names = [m.name for m in tar.getmembers()]
            # Should include nested files
            assert any('test_file3.txt' in name for name in names)

    def test_create_archive_mixed_sources(self, temp_files, tmp_path):
        """Test creating archive from mix of files and directories."""
        sources = [
            str(temp_files / "test_file1.txt"),
            str(temp_files / "nested")
        ]
        output_path = str(tmp_path / "mixed_archive")

        archive_path = create_archive(sources, output_path, "tar.gz")

        assert os.path.exists(archive_path)

    def test_create_archive_with_zip_format(self, temp_files, tmp_path):
        """Test ZIP format specifically."""
        output_path = str(tmp_path / "zip_archive")

        archive_path = create_archive(
            [str(temp_files / "test_file1.txt")],
            output_path,
            "zip"
        )

        # Verify it's a valid ZIP file
        assert zipfile.is_zipfile(archive_path)

        with zipfile.ZipFile(archive_path, 'r') as zipf:
            assert zipf.testzip() is None  # No errors

    def test_create_archive_with_tar_gz_format(self, temp_files, tmp_path):
        """Test TAR.GZ format specifically."""
        output_path = str(tmp_path / "targz_archive")

        archive_path = create_archive(
            [str(temp_files / "test_file1.txt")],
            output_path,
            "tar.gz"
        )

        # Verify it's a valid TAR.GZ file
        assert tarfile.is_tarfile(archive_path)

        with tarfile.open(archive_path, 'r:gz') as tar:
            assert len(tar.getmembers()) > 0

    def test_create_archive_with_no_compression(self, temp_files, tmp_path):
        """Test TAR format without compression."""
        output_path = str(tmp_path / "tar_archive")

        archive_path = create_archive(
            [str(temp_files / "test_file1.txt")],
            output_path,
            "none"
        )

        assert archive_path.endswith(".tar")
        assert tarfile.is_tarfile(archive_path)


class TestCreateArchiveErrors:
    """Test error handling in create_archive function."""

    def test_create_archive_empty_source_list(self, tmp_path):
        """Test that empty source list raises CompressionError."""
        output_path = str(tmp_path / "archive")

        with pytest.raises(CompressionError, match="No source paths"):
            create_archive([], output_path, "tar.gz")

    def test_create_archive_invalid_format(self, temp_files, tmp_path):
        """Test that invalid compression format raises ValueError."""
        output_path = str(tmp_path / "archive")

        with pytest.raises(ValueError, match="Invalid compression format"):
            create_archive(
                [str(temp_files / "test_file1.txt")],
                output_path,
                "invalid_format"
            )

    def test_create_archive_nonexistent_file(self, tmp_path):
        """Test that nonexistent source file raises CompressionError."""
        output_path = str(tmp_path / "archive")
        nonexistent = str(tmp_path / "does_not_exist.txt")

        with pytest.raises(CompressionError):
            create_archive([nonexistent], output_path, "tar.gz")


class TestGenerateArchiveFilename:
    """Test generate_archive_filename function."""

    def test_generate_filename_basic(self):
        """Test basic filename generation."""
        filename = generate_archive_filename("test_job", "tar.gz")

        assert filename.startswith("test_job-")
        assert filename.endswith(".tar.gz")

    def test_generate_filename_with_spaces(self):
        """Test filename generation with spaces in job name."""
        filename = generate_archive_filename("my backup job", "zip")

        # Spaces should be replaced with underscores
        assert "my_backup_job" in filename
        assert filename.endswith(".zip")

    def test_generate_filename_with_special_chars(self):
        """Test filename generation with special characters."""
        filename = generate_archive_filename("job@#$%name", "tar.gz")

        # Special chars should be replaced with underscores
        assert "job" in filename
        assert "name" in filename
        # No special characters should remain
        assert not any(c in filename for c in "@#$%")

    @pytest.mark.parametrize("compression_format,expected_extension", [
        ("zip", ".zip"),
        ("tar.gz", ".tar.gz"),
        ("tar.bz2", ".tar.bz2"),
        ("tar.xz", ".tar.xz"),
        ("none", ".tar"),
    ])
    def test_generate_filename_all_formats(self, compression_format, expected_extension):
        """Test filename generation for all formats."""
        filename = generate_archive_filename("test", compression_format)

        assert filename.endswith(expected_extension)

    def test_generate_filename_includes_timestamp(self):
        """Test that filename includes timestamp."""
        filename1 = generate_archive_filename("job", "tar.gz")
        filename2 = generate_archive_filename("job", "tar.gz")

        # Both should have timestamp format YYYYMMDD_HHMMSS
        assert "_" in filename1
        # Timestamps might be same if generated in same second, but format should be there
        # New format: job-YYYYMMDD_HHMMSS.ext (split on underscore gives 2+ parts)
        assert len(filename1.split("_")) >= 2

    def test_generate_filename_alphanumeric_preserved(self):
        """Test that alphanumeric characters and hyphens/underscores are preserved."""
        filename = generate_archive_filename("job-name_123", "zip")

        assert "job-name_123" in filename


class TestStripArchiveExtension:
    """Test strip_archive_extension function."""

    def test_strip_tar_gz_extension(self):
        """Test stripping .tar.gz extension."""
        filename = "backup-20251130_143022.tar.gz"
        result = strip_archive_extension(filename)
        assert result == "backup-20251130_143022"

    def test_strip_tar_bz2_extension(self):
        """Test stripping .tar.bz2 extension."""
        filename = "backup-20251130_143022.tar.bz2"
        result = strip_archive_extension(filename)
        assert result == "backup-20251130_143022"

    def test_strip_tar_xz_extension(self):
        """Test stripping .tar.xz extension."""
        filename = "backup-20251130_143022.tar.xz"
        result = strip_archive_extension(filename)
        assert result == "backup-20251130_143022"

    def test_strip_zip_extension(self):
        """Test stripping .zip extension."""
        filename = "backup-20251130_143022.zip"
        result = strip_archive_extension(filename)
        assert result == "backup-20251130_143022"

    def test_strip_tar_extension(self):
        """Test stripping .tar extension."""
        filename = "backup-20251130_143022.tar"
        result = strip_archive_extension(filename)
        assert result == "backup-20251130_143022"

    def test_strip_unknown_extension(self):
        """Test fallback for unknown extensions."""
        filename = "backup.unknown"
        result = strip_archive_extension(filename)
        assert result == "backup"


class TestGetArchiveSize:
    """Test get_archive_size function."""

    def test_get_archive_size_valid_file(self, temp_files, tmp_path):
        """Test getting size of valid archive."""
        output_path = str(tmp_path / "test_archive")

        archive_path = create_archive(
            [str(temp_files / "test_file1.txt")],
            output_path,
            "tar.gz"
        )

        size = get_archive_size(archive_path)

        assert size > 0
        assert isinstance(size, int)

    def test_get_archive_size_large_file(self, tmp_path):
        """Test getting size of larger archive."""
        # Create a larger file
        large_file = tmp_path / "large_file.txt"
        large_file.write_text("x" * 10000)  # 10KB

        output_path = str(tmp_path / "large_archive")

        archive_path = create_archive(
            [str(large_file)],
            output_path,
            "zip"
        )

        size = get_archive_size(archive_path)

        # Compressed size should be significant
        assert size > 100  # At least 100 bytes

    def test_get_archive_size_nonexistent_file(self, tmp_path):
        """Test that nonexistent file raises CompressionError."""
        nonexistent = str(tmp_path / "does_not_exist.tar.gz")

        with pytest.raises(CompressionError, match="Archive not found"):
            get_archive_size(nonexistent)

    def test_get_archive_size_matches_os_getsize(self, temp_files, tmp_path):
        """Test that get_archive_size matches os.path.getsize."""
        output_path = str(tmp_path / "test_archive")

        archive_path = create_archive(
            [str(temp_files / "test_file1.txt")],
            output_path,
            "tar.gz"
        )

        size_from_function = get_archive_size(archive_path)
        size_from_os = os.path.getsize(archive_path)

        assert size_from_function == size_from_os


class TestArchiveIntegrity:
    """Test that created archives are valid and can be extracted."""

    def test_zip_archive_extractable(self, temp_files, tmp_path):
        """Test that created ZIP archive can be extracted."""
        output_path = str(tmp_path / "test_zip")

        archive_path = create_archive(
            [str(temp_files / "test_file1.txt")],
            output_path,
            "zip"
        )

        # Extract and verify
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with zipfile.ZipFile(archive_path, 'r') as zipf:
            zipf.extractall(extract_dir)

        extracted_file = extract_dir / "test_file1.txt"
        assert extracted_file.exists()
        assert extracted_file.read_text() == "Test content 1"

    def test_targz_archive_extractable(self, temp_files, tmp_path):
        """Test that created TAR.GZ archive can be extracted."""
        output_path = str(tmp_path / "test_targz")

        archive_path = create_archive(
            [str(temp_files / "test_file1.txt")],
            output_path,
            "tar.gz"
        )

        # Extract and verify
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with tarfile.open(archive_path, 'r:gz') as tar:
            tar.extractall(extract_dir)

        extracted_file = extract_dir / "test_file1.txt"
        assert extracted_file.exists()
        assert extracted_file.read_text() == "Test content 1"
