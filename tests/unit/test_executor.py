"""
Unit tests for backup executor (app/backup/executor.py).

Tests BackupExecutor for orchestrating complete backup workflows.
"""

import os
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from datetime import datetime

import pytest

from app.backup.executor import (
    BackupExecutor,
    execute_backup_job,
    execute_backup_job_by_name
)
from app.backup.storage import StorageError
from app.backup.sources import SourceError
from app.backup.compression import CompressionError
from app.models import BackupJob, BackupHistory


class TestBackupExecutor:
    """Test BackupExecutor class."""

    def test_executor_initialization(self, db, local_backup_job):
        """Test BackupExecutor initializes correctly."""
        executor = BackupExecutor(local_backup_job)

        assert executor.job == local_backup_job
        assert executor.history_record is None
        assert executor.temp_dir is None
        assert executor.archive_path is None
        assert executor.logs == []

    @patch('app.backup.executor.create_source')
    @patch('app.backup.executor.create_archive')
    @patch('app.backup.executor.S3Storage')
    @patch('app.backup.executor.LocalStorage')
    @patch('app.backup.executor.get_archive_size')
    def test_executor_successful_backup(
        self, mock_get_size, mock_local_storage, mock_s3_storage,
        mock_create_archive, mock_create_source, db, local_backup_job,
        crypto_manager_initialized, aws_settings
    ):
        """Test successful backup execution."""
        cm, _ = crypto_manager_initialized

        # Mock source
        mock_source = MagicMock()
        mock_source.acquire.return_value = ['/tmp/test/file1.txt']
        mock_create_source.return_value = mock_source

        # Mock archive creation
        mock_create_archive.return_value = '/tmp/archive.tar.gz'
        mock_get_size.return_value = 1024000  # 1MB

        # Mock S3 storage
        mock_s3_instance = MagicMock()
        mock_s3_instance.upload.return_value = 'test_job/2024/01/backup.tar.gz'
        mock_s3_storage.return_value = mock_s3_instance

        # Mock local storage
        mock_local_instance = MagicMock()
        mock_local_instance.store.return_value = 'test_job/backup.tar.gz'
        mock_local_storage.return_value = mock_local_instance

        # Set retention to enable local storage
        local_backup_job.retention_local_days = 7

        with patch('app.backup.executor.crypto_manager', cm):
            executor = BackupExecutor(local_backup_job)
            result = executor.execute()

        # Verify history record was created
        assert result.status == 'success'
        assert result.job_id == local_backup_job.id
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.s3_key == 'test_job/2024/01/backup.tar.gz'
        assert result.local_path == 'test_job/backup.tar.gz'
        assert result.file_size_bytes == 1024000

        # Verify source was acquired
        mock_source.acquire.assert_called_once()
        mock_source.cleanup.assert_called_once()

        # Verify archive was created
        mock_create_archive.assert_called_once()

        # Verify S3 upload
        mock_s3_instance.upload.assert_called_once()

        # Verify local storage
        mock_local_instance.store.assert_called_once()

    @patch('app.backup.executor.create_source')
    @patch('app.backup.executor.create_archive')
    @patch('app.backup.executor.S3Storage')
    @patch('app.backup.executor.get_archive_size')
    def test_executor_backup_without_local_storage(
        self, mock_get_size, mock_s3_storage, mock_create_archive,
        mock_create_source, db, local_backup_job, crypto_manager_initialized,
        aws_settings
    ):
        """Test backup execution without local storage."""
        cm, _ = crypto_manager_initialized

        # Mock source
        mock_source = MagicMock()
        mock_source.acquire.return_value = ['/tmp/test/file1.txt']
        mock_create_source.return_value = mock_source

        # Mock archive creation
        mock_create_archive.return_value = '/tmp/archive.tar.gz'
        mock_get_size.return_value = 512000

        # Mock S3 storage
        mock_s3_instance = MagicMock()
        mock_s3_instance.upload.return_value = 'test_job/2024/01/backup.tar.gz'
        mock_s3_storage.return_value = mock_s3_instance

        # No local retention
        local_backup_job.retention_local_days = None

        with patch('app.backup.executor.crypto_manager', cm):
            executor = BackupExecutor(local_backup_job)
            result = executor.execute()

        # Verify backup succeeded without local storage
        assert result.status == 'success'
        assert result.s3_key == 'test_job/2024/01/backup.tar.gz'
        assert result.local_path is None

    @patch('app.backup.executor.create_source')
    def test_executor_source_acquisition_failure(
        self, mock_create_source, db, local_backup_job
    ):
        """Test backup fails when source acquisition fails."""
        # Mock source to raise error
        mock_source = MagicMock()
        mock_source.acquire.side_effect = SourceError("Failed to acquire source")
        mock_create_source.return_value = mock_source

        executor = BackupExecutor(local_backup_job)
        result = executor.execute()

        # Verify failure was recorded
        assert result.status == 'failed'
        assert 'Failed to acquire source' in result.error_message

        # Verify cleanup was called
        mock_source.cleanup.assert_called_once()

    @patch('app.backup.executor.create_source')
    @patch('app.backup.executor.create_archive')
    def test_executor_archive_creation_failure(
        self, mock_create_archive, mock_create_source, db, local_backup_job
    ):
        """Test backup fails when archive creation fails."""
        # Mock source
        mock_source = MagicMock()
        mock_source.acquire.return_value = ['/tmp/test/file1.txt']
        mock_create_source.return_value = mock_source

        # Mock archive creation to fail
        mock_create_archive.side_effect = CompressionError("Failed to create archive")

        executor = BackupExecutor(local_backup_job)
        result = executor.execute()

        # Verify failure was recorded
        assert result.status == 'failed'
        assert 'Failed to create archive' in result.error_message

    @patch('app.backup.executor.create_source')
    @patch('app.backup.executor.create_archive')
    @patch('app.backup.executor.S3Storage')
    @patch('app.backup.executor.get_archive_size')
    def test_executor_s3_upload_failure(
        self, mock_get_size, mock_s3_storage, mock_create_archive,
        mock_create_source, db, local_backup_job, crypto_manager_initialized,
        aws_settings
    ):
        """Test backup fails when S3 upload fails."""
        cm, _ = crypto_manager_initialized

        # Mock source
        mock_source = MagicMock()
        mock_source.acquire.return_value = ['/tmp/test/file1.txt']
        mock_create_source.return_value = mock_source

        # Mock archive creation
        mock_create_archive.return_value = '/tmp/archive.tar.gz'
        mock_get_size.return_value = 1024000

        # Mock S3 upload to fail
        mock_s3_instance = MagicMock()
        mock_s3_instance.upload.side_effect = StorageError("S3 upload failed")
        mock_s3_storage.return_value = mock_s3_instance

        with patch('app.backup.executor.crypto_manager', cm):
            executor = BackupExecutor(local_backup_job)
            result = executor.execute()

        # Verify failure was recorded
        assert result.status == 'failed'
        assert 'S3 upload failed' in result.error_message

    @patch('app.backup.executor.create_source')
    @patch('app.backup.executor.create_archive')
    @patch('app.backup.executor.S3Storage')
    @patch('app.backup.executor.get_archive_size')
    def test_executor_no_aws_settings(
        self, mock_get_size, mock_s3_storage, mock_create_archive,
        mock_create_source, db, local_backup_job
    ):
        """Test backup fails when AWS settings not configured."""
        # Mock source
        mock_source = MagicMock()
        mock_source.acquire.return_value = ['/tmp/test/file1.txt']
        mock_create_source.return_value = mock_source

        # Mock archive creation
        mock_create_archive.return_value = '/tmp/archive.tar.gz'
        mock_get_size.return_value = 1024000

        # No AWS settings in database
        executor = BackupExecutor(local_backup_job)
        result = executor.execute()

        # Verify failure was recorded
        assert result.status == 'failed'
        assert 'AWS settings not configured' in result.error_message

    def test_executor_logging(self, db, local_backup_job):
        """Test executor logs messages."""
        executor = BackupExecutor(local_backup_job)

        executor._log("Test message 1")
        executor._log("Test message 2")

        assert len(executor.logs) == 2
        assert "Test message 1" in executor.logs[0]
        assert "Test message 2" in executor.logs[1]
        # Verify timestamps are included
        assert "[20" in executor.logs[0]  # Year starts with 20

    @patch('app.backup.executor.shutil.rmtree')
    @patch('app.backup.executor.os.path.exists')
    def test_executor_cleanup(self, mock_exists, mock_rmtree, db, local_backup_job):
        """Test executor cleans up temporary files."""
        mock_exists.return_value = True

        executor = BackupExecutor(local_backup_job)
        executor.temp_dir = '/tmp/test_dir'

        executor._cleanup()

        mock_rmtree.assert_called_once_with('/tmp/test_dir')


class TestExecuteBackupJobFunction:
    """Test execute_backup_job helper function."""

    @patch.object(BackupExecutor, 'execute')
    def test_execute_backup_job_by_id(self, mock_execute, db, local_backup_job):
        """Test executing backup job by ID."""
        mock_history = MagicMock()
        mock_execute.return_value = mock_history

        result = execute_backup_job(local_backup_job.id)

        assert result == mock_history
        mock_execute.assert_called_once()

    def test_execute_backup_job_not_found(self, db):
        """Test executing non-existent job raises error."""
        with pytest.raises(ValueError, match="not found"):
            execute_backup_job(99999)

    @patch.object(BackupExecutor, 'execute')
    def test_execute_backup_job_disabled(self, mock_execute, db, local_backup_job):
        """Test executing disabled job raises error."""
        local_backup_job.enabled = False
        db.session.commit()

        with pytest.raises(ValueError, match="disabled"):
            execute_backup_job(local_backup_job.id)

    @patch.object(BackupExecutor, 'execute')
    def test_execute_backup_job_disabled_allowed(self, mock_execute, db, local_backup_job):
        """Test executing disabled job when explicitly allowed."""
        local_backup_job.enabled = False
        db.session.commit()

        mock_history = MagicMock()
        mock_execute.return_value = mock_history

        result = execute_backup_job(local_backup_job.id, allow_disabled=True)

        assert result == mock_history
        mock_execute.assert_called_once()


class TestExecuteBackupJobByNameFunction:
    """Test execute_backup_job_by_name helper function."""

    @patch.object(BackupExecutor, 'execute')
    def test_execute_backup_job_by_name(self, mock_execute, db, local_backup_job):
        """Test executing backup job by name."""
        mock_history = MagicMock()
        mock_execute.return_value = mock_history

        result = execute_backup_job_by_name(local_backup_job.name)

        assert result == mock_history
        mock_execute.assert_called_once()

    def test_execute_backup_job_by_name_not_found(self, db):
        """Test executing non-existent job by name raises error."""
        with pytest.raises(ValueError, match="not found"):
            execute_backup_job_by_name("nonexistent_job")

    @patch.object(BackupExecutor, 'execute')
    def test_execute_backup_job_by_name_disabled(self, mock_execute, db, local_backup_job):
        """Test executing disabled job by name raises error."""
        local_backup_job.enabled = False
        db.session.commit()

        with pytest.raises(ValueError, match="disabled"):
            execute_backup_job_by_name(local_backup_job.name)
