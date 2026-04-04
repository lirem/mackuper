"""
Unit tests for retention policy management (app/backup/retention.py).

Tests RetentionManager for cleaning up old backups.
"""

from datetime import datetime, timedelta, timezone
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

        # S3 returns two objects: one old (30 days ago), one recent (5 days)
        old_key = 'test_local_backup/2023/12/old_backup.tar.gz'
        recent_key = 'test_local_backup/2024/01/recent_backup.tar.gz'
        mock_s3_instance.list_objects.return_value = [
            {'Key': old_key, 'LastModified': datetime(2023, 12, 16, tzinfo=timezone.utc), 'Size': 1000},
            {'Key': recent_key, 'LastModified': datetime(2024, 1, 10, tzinfo=timezone.utc), 'Size': 1000},
        ]

        # Mock the global crypto_manager
        with patch('app.backup.retention.crypto_manager', cm):
            # Set retention to 7 days
            local_backup_job.retention_s3_days = 7
            db.session.commit()

            manager = RetentionManager()
            result = manager.enforce_job_policy(local_backup_job)

            # Old backup (30 days ago) must be deleted; recent (5 days) kept
            assert result['s3_deleted'] == 1
            mock_s3_instance.delete.assert_called_once_with(old_key)

    @freeze_time("2024-01-15")
    @patch('app.backup.retention.S3Storage')
    @patch('app.backup.retention.LocalStorage')
    def test_enforce_job_policy_keeps_recent_backups(self, mock_local_storage, mock_s3_storage, db, local_backup_job, crypto_manager_initialized, aws_settings):
        """Test that recent backups are not deleted."""
        cm, _ = crypto_manager_initialized

        mock_s3_instance = MagicMock()
        mock_s3_storage.return_value = mock_s3_instance
        mock_local_storage.return_value = MagicMock()

        recent_key = 'test_local_backup/2024/01/recent_backup.tar.gz'
        mock_s3_instance.list_objects.return_value = [
            {'Key': recent_key, 'LastModified': datetime(2024, 1, 12, tzinfo=timezone.utc), 'Size': 1000},
        ]

        with patch('app.backup.retention.crypto_manager', cm):
            local_backup_job.retention_s3_days = 7
            db.session.commit()

            manager = RetentionManager()
            result = manager.enforce_job_policy(local_backup_job)

        # Recent backup (3 days ago, within 7-day window) must NOT be deleted
        assert result['s3_deleted'] == 0
        mock_s3_instance.delete.assert_not_called()

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
    @patch('app.backup.retention.S3Storage')
    @patch('app.backup.retention.LocalStorage')
    def test_retention_only_deletes_old_backups(self, mock_local_storage, mock_s3_storage, db, local_backup_job, crypto_manager_initialized, aws_settings):
        """Test that only backups older than retention period are deleted."""
        cm, _ = crypto_manager_initialized

        mock_s3_instance = MagicMock()
        mock_s3_storage.return_value = mock_s3_instance
        mock_local_storage.return_value = MagicMock()

        base = datetime(2024, 1, 15, tzinfo=timezone.utc)
        ages = [3, 5, 10, 15, 20]  # days ago from freeze_time date
        mock_s3_instance.list_objects.return_value = [
            {'Key': f'test_local_backup/backup_{d}.tar.gz', 'LastModified': base - timedelta(days=d), 'Size': 100}
            for d in ages
        ]

        with patch('app.backup.retention.crypto_manager', cm):
            local_backup_job.retention_s3_days = 7
            db.session.commit()

            manager = RetentionManager()
            result = manager.enforce_job_policy(local_backup_job)

        # Ages 10, 15, 20 are outside the 7-day window → deleted (3 objects)
        # Ages 3, 5 are within the window → kept
        assert result['s3_deleted'] == 3
        assert mock_s3_instance.delete.call_count == 3

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

    @patch('app.backup.retention.S3Storage')
    @patch('app.backup.retention.LocalStorage')
    def test_retention_skips_failed_backups(self, mock_local_storage, mock_s3_storage, db, local_backup_job, crypto_manager_initialized, aws_settings):
        """Test that S3 retention is based on object age, not backup status."""
        cm, _ = crypto_manager_initialized

        mock_s3_instance = MagicMock()
        mock_s3_storage.return_value = mock_s3_instance
        mock_local_storage.return_value = MagicMock()

        old_key = 'test_local_backup/failed_backup.tar.gz'
        mock_s3_instance.list_objects.return_value = [
            {'Key': old_key, 'LastModified': datetime.now(timezone.utc) - timedelta(days=10), 'Size': 0},
        ]

        with patch('app.backup.retention.crypto_manager', cm):
            local_backup_job.retention_s3_days = 7
            db.session.commit()

            manager = RetentionManager()
            result = manager.enforce_job_policy(local_backup_job)

        # S3 object is 10 days old with 7-day retention → must be deleted
        assert result['s3_deleted'] == 1
        mock_s3_instance.delete.assert_called_once_with(old_key)


class TestRetentionEdgeCases:
    """Test edge cases in retention management."""

    @patch('app.backup.retention.S3Storage')
    @patch('app.backup.retention.LocalStorage')
    def test_retention_zero_days_policy(self, mock_local_storage, mock_s3_storage, db, local_backup_job, crypto_manager_initialized, aws_settings):
        """Test retention policy with 0 days deletes everything including recent backups."""
        cm, _ = crypto_manager_initialized

        mock_s3_instance = MagicMock()
        mock_s3_storage.return_value = mock_s3_instance
        mock_local_storage.return_value = MagicMock()

        recent_key = 'test_local_backup/backup.tar.gz'
        mock_s3_instance.list_objects.return_value = [
            {'Key': recent_key, 'LastModified': datetime.now(timezone.utc) - timedelta(hours=1), 'Size': 500},
        ]

        with patch('app.backup.retention.crypto_manager', cm):
            local_backup_job.retention_s3_days = 0
            db.session.commit()

            manager = RetentionManager()
            result = manager.enforce_job_policy(local_backup_job)

        # 0-day retention → cutoff is now → everything is old → deleted
        assert result['s3_deleted'] == 1
        mock_s3_instance.delete.assert_called_once_with(recent_key)

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


class TestRetentionTimezoneRegression:
    """
    Regression tests for H-02: S3 retention cutoff timezone-stripping bug.

    Prior to the fix, _cleanup_s3 used:
        cutoff_date = datetime.now()                       # naive local time
        obj['LastModified'].replace(tzinfo=None) < cutoff  # strips tzinfo from S3

    This caused incorrect comparisons in non-UTC deployments (S3 always
    returns UTC-aware datetimes). The fix uses datetime.now(timezone.utc)
    and compares aware datetimes directly.

    These tests avoid DB fixtures entirely — they mock AWSSettings.query.first()
    and crypto_manager so no database tables need to exist.
    """

    def _make_job(self, retention_s3_days):
        """Create a minimal BackupJob-like mock (no DB required)."""
        job = MagicMock(spec=['id', 'name', 'retention_s3_days', 'retention_local_days'])
        job.id = 999
        job.name = 'tz_regression_job'
        job.retention_s3_days = retention_s3_days
        job.retention_local_days = None
        return job

    def _make_aws_settings(self):
        """Create a minimal AWSSettings-like mock."""
        aws = MagicMock()
        aws.access_key_encrypted = 'enc_access'
        aws.secret_key_encrypted = 'enc_secret'
        aws.bucket_name = 'test-bucket'
        aws.region = 'us-east-1'
        return aws

    def _make_crypto(self):
        """Create a crypto_manager mock that decrypts to fixed strings."""
        cm = MagicMock()
        cm.is_initialized = True
        cm.decrypt.side_effect = lambda v: 'decrypted_' + v
        return cm

    @patch('app.backup.retention.BackupHistory')
    @patch('app.backup.retention.S3Storage')
    @patch('app.backup.retention.LocalStorage')
    @patch('app.backup.retention.AWSSettings')
    @patch('app.backup.retention.crypto_manager')
    def test_s3_objects_older_than_cutoff_are_deleted(
        self, mock_cm, mock_aws_cls, mock_local_storage, mock_s3_storage, mock_history
    ):
        """
        Regression: objects with LastModified before the UTC cutoff must be
        deleted. Provides timezone-aware UTC datetimes (as S3 does) and
        verifies the correct count is returned.
        """
        mock_cm.is_initialized = True
        mock_cm.decrypt.side_effect = lambda v: 'decrypted_' + v
        mock_aws_cls.query.first.return_value = self._make_aws_settings()
        mock_history.query.filter_by.return_value.first.return_value = None

        mock_s3_instance = MagicMock()
        mock_s3_storage.return_value = mock_s3_instance
        mock_local_storage.return_value = MagicMock()

        now = datetime.now(timezone.utc)
        old_key = 'tz_regression_job/old.tar.gz'
        new_key = 'tz_regression_job/new.tar.gz'

        mock_s3_instance.list_objects.return_value = [
            # 10 days old — outside 7-day window → must be deleted
            {'Key': old_key, 'LastModified': now - timedelta(days=10), 'Size': 100},
            # 3 days old — inside 7-day window → must be kept
            {'Key': new_key, 'LastModified': now - timedelta(days=3), 'Size': 100},
        ]

        job = self._make_job(retention_s3_days=7)
        manager = RetentionManager()
        result = manager.enforce_job_policy(job)

        assert result['s3_deleted'] == 1, (
            f"Expected 1 deletion (old object), got {result['s3_deleted']}"
        )
        mock_s3_instance.delete.assert_called_once_with(old_key)

    @patch('app.backup.retention.BackupHistory')
    @patch('app.backup.retention.S3Storage')
    @patch('app.backup.retention.LocalStorage')
    @patch('app.backup.retention.AWSSettings')
    @patch('app.backup.retention.crypto_manager')
    def test_s3_objects_newer_than_cutoff_are_kept(
        self, mock_cm, mock_aws_cls, mock_local_storage, mock_s3_storage, mock_history
    ):
        """
        Regression: objects with LastModified after the UTC cutoff must NOT
        be deleted, even when LastModified is timezone-aware.
        """
        mock_cm.is_initialized = True
        mock_cm.decrypt.side_effect = lambda v: 'decrypted_' + v
        mock_aws_cls.query.first.return_value = self._make_aws_settings()
        mock_history.query.filter_by.return_value.first.return_value = None

        mock_s3_instance = MagicMock()
        mock_s3_storage.return_value = mock_s3_instance
        mock_local_storage.return_value = MagicMock()

        now = datetime.now(timezone.utc)
        mock_s3_instance.list_objects.return_value = [
            {'Key': 'tz_regression_job/recent.tar.gz', 'LastModified': now - timedelta(days=1), 'Size': 100},
            {'Key': 'tz_regression_job/today.tar.gz', 'LastModified': now - timedelta(hours=2), 'Size': 100},
        ]

        job = self._make_job(retention_s3_days=7)
        manager = RetentionManager()
        result = manager.enforce_job_policy(job)

        assert result['s3_deleted'] == 0, (
            f"Expected 0 deletions (all objects within retention), got {result['s3_deleted']}"
        )
        mock_s3_instance.delete.assert_not_called()

    @freeze_time("2024-06-01 12:00:00")
    @patch('app.backup.retention.BackupHistory')
    @patch('app.backup.retention.S3Storage')
    @patch('app.backup.retention.LocalStorage')
    @patch('app.backup.retention.AWSSettings')
    @patch('app.backup.retention.crypto_manager')
    def test_exact_cutoff_boundary_is_exclusive(
        self, mock_cm, mock_aws_cls, mock_local_storage, mock_s3_storage, mock_history
    ):
        """
        Regression: an object whose LastModified equals the cutoff exactly
        (i.e. age == retention_days) is NOT deleted (comparison is strict <).
        An object 1 second past the cutoff IS deleted.

        freeze_time ensures our cutoff calculation matches RetentionManager's
        internal datetime.now(timezone.utc) call exactly.
        """
        mock_cm.is_initialized = True
        mock_cm.decrypt.side_effect = lambda v: 'decrypted_' + v
        mock_aws_cls.query.first.return_value = self._make_aws_settings()
        mock_history.query.filter_by.return_value.first.return_value = None

        mock_s3_instance = MagicMock()
        mock_s3_storage.return_value = mock_s3_instance
        mock_local_storage.return_value = MagicMock()

        retention_days = 7
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        cutoff = now - timedelta(days=retention_days)

        exactly_at_cutoff_key = 'tz_regression_job/exact.tar.gz'
        just_past_cutoff_key = 'tz_regression_job/past.tar.gz'

        mock_s3_instance.list_objects.return_value = [
            # Exactly at the cutoff — NOT older (not strictly <), so kept
            {'Key': exactly_at_cutoff_key, 'LastModified': cutoff, 'Size': 100},
            # 1 second before the cutoff — strictly older, so deleted
            {'Key': just_past_cutoff_key, 'LastModified': cutoff - timedelta(seconds=1), 'Size': 100},
        ]

        job = self._make_job(retention_s3_days=retention_days)
        manager = RetentionManager()
        result = manager.enforce_job_policy(job)

        assert result['s3_deleted'] == 1
        mock_s3_instance.delete.assert_called_once_with(just_past_cutoff_key)
