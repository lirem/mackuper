"""
Unit tests for storage handlers (app/backup/storage.py).

Tests S3Storage and LocalStorage for storing backup archives.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import boto3
from moto import mock_aws

from app.backup.storage import (
    S3Storage,
    LocalStorage,
    StorageError
)


class TestS3Storage:
    """Test S3Storage for AWS S3 operations."""

    @mock_aws
    def test_s3_storage_upload_simple(self, tmp_path):
        """Test simple S3 upload for small files."""
        # Create mock S3 bucket
        s3 = boto3.resource('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='test-bucket')

        # Create test file
        test_file = tmp_path / "test.tar.gz"
        test_file.write_bytes(b"test data" * 100)

        storage = S3Storage(
            access_key='test_access_key',
            secret_key='test_secret_key',
            bucket_name='test-bucket',
            region='us-east-1'
        )

        s3_key = storage.upload(str(test_file), 'test_job')

        # Verify key format
        assert 'test_job' in s3_key
        assert s3_key.endswith('.tar.gz')

        # Verify file exists in S3
        obj = s3.Object('test-bucket', s3_key)
        assert obj.content_length > 0

    @mock_aws
    def test_s3_storage_upload_creates_key_with_timestamp(self, tmp_path):
        """Test that S3 key includes timestamp."""
        s3 = boto3.resource('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='test-bucket')

        test_file = tmp_path / "backup.tar.gz"
        test_file.write_bytes(b"data")

        storage = S3Storage(
            access_key='test_key',
            secret_key='test_secret',
            bucket_name='test-bucket'
        )

        s3_key = storage.upload(str(test_file), 'job_name')

        # Key should have format: job_name/YYYY/MM/filename
        parts = s3_key.split('/')
        assert len(parts) >= 3
        assert parts[0] == 'job_name'

    @mock_aws
    def test_s3_storage_delete(self, tmp_path):
        """Test deleting file from S3."""
        s3 = boto3.resource('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='test-bucket')

        # Upload a file first
        test_file = tmp_path / "test.tar.gz"
        test_file.write_bytes(b"test data")

        storage = S3Storage(
            access_key='test_key',
            secret_key='test_secret',
            bucket_name='test-bucket'
        )

        s3_key = storage.upload(str(test_file), 'test_job')

        # Verify it exists
        obj = s3.Object('test-bucket', s3_key)
        obj.load()  # Will raise error if doesn't exist

        # Delete it
        storage.delete(s3_key)

        # Verify it's gone
        with pytest.raises(Exception):
            obj.load()

    @mock_aws
    def test_s3_storage_list_objects(self):
        """Test listing objects in S3 for a job."""
        s3 = boto3.resource('s3', region_name='us-east-1')
        bucket = s3.create_bucket(Bucket='test-bucket')

        # Create some objects
        bucket.put_object(Key='test_job/2024/01/file1.tar.gz', Body=b'data1')
        bucket.put_object(Key='test_job/2024/01/file2.tar.gz', Body=b'data2')
        bucket.put_object(Key='other_job/2024/01/file3.tar.gz', Body=b'data3')

        storage = S3Storage(
            access_key='test_key',
            secret_key='test_secret',
            bucket_name='test-bucket'
        )

        objects = storage.list_objects('test_job')

        # Should only return test_job files
        assert len(objects) == 2
        # Objects are dicts with 'Key', 'LastModified', 'Size' keys
        assert all('test_job' in obj['Key'] for obj in objects)

    @mock_aws
    def test_s3_storage_nonexistent_file_upload_error(self):
        """Test uploading nonexistent file raises error."""
        s3 = boto3.resource('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='test-bucket')

        storage = S3Storage(
            access_key='test_key',
            secret_key='test_secret',
            bucket_name='test-bucket'
        )

        with pytest.raises(StorageError):
            storage.upload('/nonexistent/file.tar.gz', 'job')

    @mock_aws
    def test_s3_storage_with_custom_region(self, tmp_path):
        """Test S3 storage with custom region."""
        # Create bucket in specific region
        s3 = boto3.resource('s3', region_name='us-west-2')
        s3.create_bucket(
            Bucket='test-bucket-west',
            CreateBucketConfiguration={'LocationConstraint': 'us-west-2'}
        )

        test_file = tmp_path / "test.tar.gz"
        test_file.write_bytes(b"data")

        storage = S3Storage(
            access_key='test_key',
            secret_key='test_secret',
            bucket_name='test-bucket-west',
            region='us-west-2'
        )

        s3_key = storage.upload(str(test_file), 'test_job')
        assert s3_key is not None


class TestLocalStorage:
    """Test LocalStorage for local filesystem operations."""

    def test_local_storage_store(self, tmp_path):
        """Test storing file locally."""
        storage_dir = tmp_path / "backups"
        storage_dir.mkdir()

        # Create source file
        source_file = tmp_path / "backup.tar.gz"
        source_file.write_bytes(b"backup data" * 100)

        storage = LocalStorage(str(storage_dir))
        local_path = storage.store(str(source_file), 'test_job')

        # Verify file was copied
        full_path = storage_dir / local_path
        assert full_path.exists()
        assert full_path.read_bytes() == source_file.read_bytes()

    def test_local_storage_path_includes_job_name(self, tmp_path):
        """Test that stored path includes job name."""
        storage_dir = tmp_path / "backups"
        storage_dir.mkdir()

        source_file = tmp_path / "backup.tar.gz"
        source_file.write_bytes(b"data")

        storage = LocalStorage(str(storage_dir))
        local_path = storage.store(str(source_file), 'my_job')

        assert 'my_job' in local_path

    def test_local_storage_creates_nested_directories(self, tmp_path):
        """Test that storage creates necessary directories."""
        storage_dir = tmp_path / "backups"
        storage_dir.mkdir()

        source_file = tmp_path / "backup.tar.gz"
        source_file.write_bytes(b"data")

        storage = LocalStorage(str(storage_dir))
        local_path = storage.store(str(source_file), 'test_job')

        # Check nested structure was created
        full_path = storage_dir / local_path
        assert full_path.parent.exists()

    def test_local_storage_list_files(self, tmp_path):
        """Test listing local backup files for a job."""
        storage_dir = tmp_path / "backups"
        storage_dir.mkdir()

        # Create job directory structure
        job_dir = storage_dir / "test_job"
        job_dir.mkdir()

        # Create some backup files
        (job_dir / "backup1.tar.gz").write_bytes(b"data1")
        (job_dir / "backup2.tar.gz").write_bytes(b"data2")

        storage = LocalStorage(str(storage_dir))
        files = storage.list_files('test_job')

        assert len(files) == 2
        assert all('test_job' in str(f) for f in files)

    def test_local_storage_delete(self, tmp_path):
        """Test deleting local backup file."""
        storage_dir = tmp_path / "backups"
        storage_dir.mkdir()

        source_file = tmp_path / "backup.tar.gz"
        source_file.write_bytes(b"data")

        storage = LocalStorage(str(storage_dir))
        local_path = storage.store(str(source_file), 'test_job')

        # Verify it exists
        full_path = storage_dir / local_path
        assert full_path.exists()

        # Delete it
        storage.delete(local_path)

        # Verify it's gone
        assert not full_path.exists()

    def test_local_storage_nonexistent_file_error(self, tmp_path):
        """Test storing nonexistent file raises error."""
        storage_dir = tmp_path / "backups"
        storage_dir.mkdir()

        storage = LocalStorage(str(storage_dir))

        with pytest.raises(StorageError):
            storage.store('/nonexistent/file.tar.gz', 'job')

    def test_local_storage_get_full_path(self, tmp_path):
        """Test getting full path from relative path."""
        storage_dir = tmp_path / "backups"
        storage_dir.mkdir()

        source_file = tmp_path / "backup.tar.gz"
        source_file.write_bytes(b"data")

        storage = LocalStorage(str(storage_dir))
        local_path = storage.store(str(source_file), 'test_job')

        full_path = storage.get_full_path(local_path)

        assert full_path is not None
        assert str(storage_dir) in full_path
        assert os.path.exists(full_path)


class TestStorageEdgeCases:
    """Test edge cases and error handling."""

    @mock_aws
    def test_s3_storage_empty_file(self, tmp_path):
        """Test uploading empty file to S3."""
        s3 = boto3.resource('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='test-bucket')

        empty_file = tmp_path / "empty.tar.gz"
        empty_file.write_bytes(b"")

        storage = S3Storage(
            access_key='test_key',
            secret_key='test_secret',
            bucket_name='test-bucket'
        )

        s3_key = storage.upload(str(empty_file), 'test_job')
        assert s3_key is not None

    def test_local_storage_empty_file(self, tmp_path):
        """Test storing empty file locally."""
        storage_dir = tmp_path / "backups"
        storage_dir.mkdir()

        empty_file = tmp_path / "empty.tar.gz"
        empty_file.write_bytes(b"")

        storage = LocalStorage(str(storage_dir))
        local_path = storage.store(str(empty_file), 'test_job')

        full_path = storage_dir / local_path
        assert full_path.exists()
        assert full_path.stat().st_size == 0

    @mock_aws
    def test_s3_storage_large_file_multipart(self, tmp_path):
        """Test that large files trigger multipart upload."""
        s3 = boto3.resource('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='test-bucket')

        # Create a larger file (10MB)
        large_file = tmp_path / "large.tar.gz"
        large_file.write_bytes(b"x" * (10 * 1024 * 1024))

        storage = S3Storage(
            access_key='test_key',
            secret_key='test_secret',
            bucket_name='test-bucket'
        )

        s3_key = storage.upload(str(large_file), 'test_job')

        # Verify upload succeeded
        obj = s3.Object('test-bucket', s3_key)
        assert obj.content_length == 10 * 1024 * 1024

    def test_local_storage_special_characters_in_job_name(self, tmp_path):
        """Test job names with special characters."""
        storage_dir = tmp_path / "backups"
        storage_dir.mkdir()

        source_file = tmp_path / "backup.tar.gz"
        source_file.write_bytes(b"data")

        storage = LocalStorage(str(storage_dir))
        # Job name with special chars should be sanitized
        local_path = storage.store(str(source_file), 'job@#$name')

        assert local_path is not None
