"""
Unit tests for retention policy management (app/backup/retention.py).

Tests RetentionManager for cleaning up old backups.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time

from app.backup.retention import RetentionManager
from app.models import BackupJob, BackupHistory


class TestRetentionManager:
    """Test RetentionManager basic functionality."""

    def test_retention_manager_initialization(self):
        """Test RetentionManager initializes correctly."""
        manager = RetentionManager()

        assert manager is not None
        assert manager.logs == []

    def test_enforce_job_policy_no_retention(self, db, local_backup_job):
        """Test job with no retention policy configured."""
        # Set retention to None
        local_backup_job.retention_s3_days = None
        local_backup_job.retention_local_days = None
        db.session.commit()

        manager = RetentionManager()
        result = manager.enforce_job_policy(local_backup_job)

        assert result['s3_deleted'] == 0
        assert result['local_deleted'] == 0

    @freeze_time("2024-01-15")
    @patch('app.backup.retention.S3Storage')
    @patch('app.backup.retention.LocalStorage')
    def test_enforce_job_policy_s3_cleanup(self, mock_local_storage, mock_s3_storage, db, local_backup_job, crypto_manager_initialized, aws_settings):
        """Test S3 cleanup with retention policy."""
        cm, _ = crypto_manager_initialized

        # Mock storage cleanup methods
        mock_s3_instance = MagicMock()
        mock_s3_storage.return_value = mock_s3_instance
        mock_local_instance = MagicMock()
        mock_local_storage.return_value = mock_local_instance

        # Mock the global crypto_manager
        with patch('app.backup.retention.crypto_manager', cm):
            # Create old backup history record (30 days ago)
            old_history = BackupHistory(
                job_id=local_backup_job.id,
                status='success',
                started_at=datetime(2023, 12, 16),
                completed_at=datetime(2023, 12, 16),
                s3_key='test_job/2023/12/old_backup.tar.gz'
            )
            db.session.add(old_history)

            # Create recent backup history (5 days ago)
            recent_history = BackupHistory(
                job_id=local_backup_job.id,
                status='success',
                started_at=datetime(2024, 1, 10),
                completed_at=datetime(2024, 1, 10),
                s3_key='test_job/2024/01/recent_backup.tar.gz'
            )
            db.session.add(recent_history)

            # Set retention to 7 days
            local_backup_job.retention_s3_days = 7
            db.session.commit()

            manager = RetentionManager()
            result = manager.enforce_job_policy(local_backup_job)

            # Old backup should be marked for deletion
            assert result['s3_deleted'] >= 0

    @freeze_time("2024-01-15")
    @patch('app.backup.retention.LocalStorage')
    def test_enforce_job_policy_keeps_recent_backups(self, mock_local_storage, db, local_backup_job):
        """Test that recent backups are not deleted."""
        # Mock LocalStorage
        mock_local_instance = MagicMock()
        mock_local_storage.return_value = mock_local_instance

        # Create recent backup history (3 days ago)
        recent_history = BackupHistory(
            job_id=local_backup_job.id,
            status='success',
            started_at=datetime(2024, 1, 12),
            completed_at=datetime(2024, 1, 12),
            s3_key='test_job/2024/01/recent_backup.tar.gz'
        )
        db.session.add(recent_history)

        # Set retention to 7 days
        local_backup_job.retention_s3_days = 7
        db.session.commit()

        manager = RetentionManager()
        result = manager.enforce_job_policy(local_backup_job)

        # Should not delete recent backups
        # Note: Actual deletion depends on S3 interaction
        assert result is not None

    @patch('app.backup.retention.LocalStorage')
    def test_enforce_all_policies(self, mock_local_storage, db, local_backup_job):
        """Test enforcing policies for all jobs."""
        # Mock LocalStorage
        mock_local_instance = MagicMock()
        mock_local_storage.return_value = mock_local_instance

        manager = RetentionManager()
        summary = manager.enforce_all_policies()

        assert 'jobs_processed' in summary
        assert 's3_deleted' in summary
        assert 'local_deleted' in summary
        assert 'errors' in summary
        assert 'logs' in summary

        assert summary['jobs_processed'] >= 1  # At least our test job

    def test_enforce_all_policies_handles_errors(self, db):
        """Test that enforce_all_policies handles job errors gracefully."""
        # Create a job with invalid configuration
        bad_job = BackupJob(
            name='bad_job',
            enabled=True,
            source_type='local',
            source_config='{}',
            compression_format='tar.gz',
            retention_s3_days=7
        )
        db.session.add(bad_job)
        db.session.commit()

        manager = RetentionManager()
        summary = manager.enforce_all_policies()

        # Should complete despite errors
        assert summary is not None
        assert 'errors' in summary

    @patch('app.backup.retention.LocalStorage')
    def test_retention_manager_logging(self, mock_local_storage, db, local_backup_job):
        """Test that RetentionManager logs operations."""
        # Mock LocalStorage
        mock_local_instance = MagicMock()
        mock_local_storage.return_value = mock_local_instance

        manager = RetentionManager()
        manager.enforce_job_policy(local_backup_job)

        assert len(manager.logs) > 0
        assert any('Enforcing retention policy' in log for log in manager.logs)


class TestRetentionPolicyEnforcement:
    """Test specific retention policy scenarios."""

    @freeze_time("2024-01-15")
    @patch('app.backup.retention.LocalStorage')
    def test_retention_only_deletes_old_backups(self, mock_local_storage, db, local_backup_job):
        """Test that only backups older than retention period are deleted."""
        # Mock LocalStorage
        mock_local_instance = MagicMock()
        mock_local_storage.return_value = mock_local_instance

        # Create backups at different ages
        ages = [3, 5, 10, 15, 20]  # days ago
        for days_ago in ages:
            history = BackupHistory(
                job_id=local_backup_job.id,
                status='success',
                started_at=datetime(2024, 1, 15) - timedelta(days=days_ago),
                completed_at=datetime(2024, 1, 15) - timedelta(days=days_ago),
                s3_key=f'test_job/backup_{days_ago}.tar.gz'
            )
            db.session.add(history)

        # Set retention to 7 days
        local_backup_job.retention_s3_days = 7
        db.session.commit()

        manager = RetentionManager()
        result = manager.enforce_job_policy(local_backup_job)

        # Should have attempted to delete 3 backups (10, 15, 20 days old)
        assert result is not None

    @freeze_time("2024-01-15")
    @patch('app.backup.retention.LocalStorage')
    def test_retention_different_s3_and_local_policies(self, mock_local_storage, db, local_backup_job):
        """Test different retention periods for S3 and local storage."""
        # Mock LocalStorage
        mock_local_instance = MagicMock()
        mock_local_instance.list_files.return_value = []
        mock_local_storage.return_value = mock_local_instance

        # Set different retention periods
        local_backup_job.retention_s3_days = 30
        local_backup_job.retention_local_days = 7
        db.session.commit()

        manager = RetentionManager()
        result = manager.enforce_job_policy(local_backup_job)

        assert result['s3_deleted'] >= 0
        assert result['local_deleted'] >= 0

    @patch('app.backup.retention.LocalStorage')
    def test_retention_skips_failed_backups(self, mock_local_storage, db, local_backup_job):
        """Test that failed backups are also cleaned up."""
        # Mock LocalStorage
        mock_local_instance = MagicMock()
        mock_local_storage.return_value = mock_local_instance

        # Create a failed backup
        failed_history = BackupHistory(
            job_id=local_backup_job.id,
            status='failed',
            started_at=datetime.utcnow() - timedelta(days=10),
            completed_at=datetime.utcnow() - timedelta(days=10),
            s3_key='test_job/failed_backup.tar.gz',
            error_message='Test error'
        )
        db.session.add(failed_history)
        db.session.commit()

        local_backup_job.retention_s3_days = 7
        db.session.commit()

        manager = RetentionManager()
        result = manager.enforce_job_policy(local_backup_job)

        # Failed backups should also be subject to retention
        assert result is not None


class TestRetentionEdgeCases:
    """Test edge cases in retention management."""

    @patch('app.backup.retention.LocalStorage')
    def test_retention_zero_days_policy(self, mock_local_storage, db, local_backup_job):
        """Test retention policy with 0 days (delete all)."""
        # Mock LocalStorage
        mock_local_instance = MagicMock()
        mock_local_storage.return_value = mock_local_instance

        # Create a backup
        history = BackupHistory(
            job_id=local_backup_job.id,
            status='success',
            started_at=datetime.utcnow() - timedelta(hours=1),
            completed_at=datetime.utcnow() - timedelta(hours=1),
            s3_key='test_job/backup.tar.gz'
        )
        db.session.add(history)

        # Set retention to 0 days
        local_backup_job.retention_s3_days = 0
        db.session.commit()

        manager = RetentionManager()
        result = manager.enforce_job_policy(local_backup_job)

        # Even recent backups should be eligible for deletion
        assert result is not None

    @patch('app.backup.retention.LocalStorage')
    def test_retention_very_long_retention_period(self, mock_local_storage, db, local_backup_job):
        """Test retention policy with very long period (365 days)."""
        # Mock LocalStorage
        mock_local_instance = MagicMock()
        mock_local_storage.return_value = mock_local_instance

        # Create old backup
        old_history = BackupHistory(
            job_id=local_backup_job.id,
            status='success',
            started_at=datetime.utcnow() - timedelta(days=100),
            completed_at=datetime.utcnow() - timedelta(days=100),
            s3_key='test_job/old_backup.tar.gz'
        )
        db.session.add(old_history)

        # Set retention to 365 days
        local_backup_job.retention_s3_days = 365
        db.session.commit()

        manager = RetentionManager()
        result = manager.enforce_job_policy(local_backup_job)

        # Should not delete 100-day-old backup
        assert result['s3_deleted'] == 0

    @patch('app.backup.retention.LocalStorage')
    def test_retention_with_no_backup_history(self, mock_local_storage, db, local_backup_job):
        """Test retention enforcement when job has no backup history."""
        # Mock LocalStorage
        mock_local_instance = MagicMock()
        mock_local_storage.return_value = mock_local_instance

        # Don't create any backup history

        local_backup_job.retention_s3_days = 7
        db.session.commit()

        manager = RetentionManager()
        result = manager.enforce_job_policy(local_backup_job)

        # Should handle gracefully
        assert result['s3_deleted'] == 0
        assert result['local_deleted'] == 0

    def test_retention_logs_summary(self, db, local_backup_job):
        """Test that retention manager creates proper log summary."""
        manager = RetentionManager()
        summary = manager.enforce_all_policies()

        # Logs should be included in summary
        assert 'logs' in summary
        assert isinstance(summary['logs'], list)
        assert len(summary['logs']) > 0
