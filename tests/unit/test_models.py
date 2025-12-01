"""
Unit tests for database models (app/models.py).

Tests all SQLAlchemy models, relationships, and validators.
"""

import json
from datetime import datetime, timedelta

import pytest

from app.models import User, AWSSettings, BackupJob, BackupHistory, EncryptionKey


class TestUserModel:
    """Test User model."""

    def test_create_user(self, db):
        """Test creating a user."""
        user = User(
            username='testuser',
            password_hash='hashed_password_123'
        )
        db.session.add(user)
        db.session.commit()

        assert user.id is not None
        assert user.username == 'testuser'
        assert user.password_hash == 'hashed_password_123'
        assert user.created_at is not None

    def test_user_username_unique(self, db):
        """Test that username must be unique."""
        user1 = User(username='testuser', password_hash='hash1')
        db.session.add(user1)
        db.session.commit()

        user2 = User(username='testuser', password_hash='hash2')
        db.session.add(user2)

        with pytest.raises(Exception):  # IntegrityError
            db.session.commit()

    def test_user_repr(self, db):
        """Test User __repr__ method."""
        user = User(username='testuser', password_hash='hash')
        db.session.add(user)
        db.session.commit()

        assert repr(user) == '<User testuser>'

    def test_user_created_at_auto_set(self, db):
        """Test that created_at is automatically set."""
        before = datetime.utcnow()
        user = User(username='testuser', password_hash='hash')
        db.session.add(user)
        db.session.commit()
        after = datetime.utcnow()

        assert before <= user.created_at <= after


class TestAWSSettingsModel:
    """Test AWSSettings model."""

    def test_create_aws_settings(self, db):
        """Test creating AWS settings."""
        settings = AWSSettings(
            access_key_encrypted='encrypted_access_key',
            secret_key_encrypted='encrypted_secret_key',
            bucket_name='my-backup-bucket',
            region='us-west-2'
        )
        db.session.add(settings)
        db.session.commit()

        assert settings.id is not None
        assert settings.access_key_encrypted == 'encrypted_access_key'
        assert settings.secret_key_encrypted == 'encrypted_secret_key'
        assert settings.bucket_name == 'my-backup-bucket'
        assert settings.region == 'us-west-2'
        assert settings.updated_at is not None

    def test_aws_settings_repr(self, db):
        """Test AWSSettings __repr__ method."""
        settings = AWSSettings(
            access_key_encrypted='enc1',
            secret_key_encrypted='enc2',
            bucket_name='test-bucket',
            region='us-east-1'
        )
        db.session.add(settings)
        db.session.commit()

        assert repr(settings) == '<AWSSettings bucket=test-bucket region=us-east-1>'

    def test_aws_settings_updated_at_auto_update(self, db):
        """Test that updated_at is automatically updated on modification."""
        settings = AWSSettings(
            access_key_encrypted='enc1',
            secret_key_encrypted='enc2',
            bucket_name='test-bucket',
            region='us-east-1'
        )
        db.session.add(settings)
        db.session.commit()

        original_updated_at = settings.updated_at

        # Modify settings
        settings.bucket_name = 'new-bucket'
        db.session.commit()

        # updated_at should change
        assert settings.updated_at >= original_updated_at


class TestBackupJobModel:
    """Test BackupJob model."""

    def test_create_backup_job_local(self, db):
        """Test creating a local backup job."""
        job = BackupJob(
            name='local_backup',
            description='Backup local files',
            enabled=True,
            source_type='local',
            source_config=json.dumps({'paths': ['/data']}),
            compression_format='tar.gz',
            schedule_cron='0 2 * * *',
            retention_s3_days=30,
            retention_local_days=7
        )
        db.session.add(job)
        db.session.commit()

        assert job.id is not None
        assert job.name == 'local_backup'
        assert job.enabled is True
        assert job.source_type == 'local'
        assert job.compression_format == 'tar.gz'

    def test_create_backup_job_ssh(self, db):
        """Test creating an SSH backup job."""
        job = BackupJob(
            name='ssh_backup',
            enabled=True,
            source_type='ssh',
            source_config=json.dumps({
                'host': 'example.com',
                'username': 'user',
                'paths': ['/remote/data']
            }),
            compression_format='zip',
            retention_s3_days=14
        )
        db.session.add(job)
        db.session.commit()

        assert job.source_type == 'ssh'
        assert job.retention_local_days is None

    def test_backup_job_name_unique(self, db):
        """Test that backup job name must be unique."""
        job1 = BackupJob(
            name='backup1',
            enabled=True,
            source_type='local',
            source_config='{}',
            compression_format='tar.gz'
        )
        db.session.add(job1)
        db.session.commit()

        job2 = BackupJob(
            name='backup1',
            enabled=True,
            source_type='local',
            source_config='{}',
            compression_format='zip'
        )
        db.session.add(job2)

        with pytest.raises(Exception):  # IntegrityError
            db.session.commit()

    def test_backup_job_repr(self, db):
        """Test BackupJob __repr__ method."""
        job = BackupJob(
            name='test_job',
            enabled=True,
            source_type='local',
            source_config='{}',
            compression_format='tar.gz'
        )
        db.session.add(job)
        db.session.commit()

        assert repr(job) == '<BackupJob test_job type=local enabled=True>'

    def test_backup_job_timestamps(self, db):
        """Test that created_at and updated_at are set correctly."""
        job = BackupJob(
            name='test_job',
            enabled=True,
            source_type='local',
            source_config='{}',
            compression_format='tar.gz'
        )
        db.session.add(job)
        db.session.commit()

        assert job.created_at is not None
        assert job.updated_at is not None
        assert job.created_at <= job.updated_at


class TestBackupHistoryModel:
    """Test BackupHistory model."""

    def test_create_backup_history(self, db, local_backup_job):
        """Test creating a backup history record."""
        history = BackupHistory(
            job_id=local_backup_job.id,
            status='success',
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            file_size_bytes=1024000,
            s3_key='backup/2024/01/file.tar.gz',
            local_path='backups/file.tar.gz',
            logs='Backup completed successfully'
        )
        db.session.add(history)
        db.session.commit()

        assert history.id is not None
        assert history.job_id == local_backup_job.id
        assert history.status == 'success'
        assert history.file_size_bytes == 1024000

    def test_backup_history_statuses(self, db, local_backup_job):
        """Test different backup history statuses."""
        statuses = ['running', 'success', 'failed']

        for status in statuses:
            history = BackupHistory(
                job_id=local_backup_job.id,
                status=status,
                started_at=datetime.utcnow()
            )
            db.session.add(history)
            db.session.commit()

            assert history.status == status

    def test_backup_history_relationship_to_job(self, db, local_backup_job):
        """Test relationship between BackupHistory and BackupJob."""
        history1 = BackupHistory(
            job_id=local_backup_job.id,
            status='success',
            started_at=datetime.utcnow()
        )
        history2 = BackupHistory(
            job_id=local_backup_job.id,
            status='failed',
            started_at=datetime.utcnow()
        )
        db.session.add_all([history1, history2])
        db.session.commit()

        # Access history through job relationship
        histories = local_backup_job.history.all()

        assert len(histories) == 2
        assert history1 in histories
        assert history2 in histories

    def test_backup_history_repr(self, db, local_backup_job):
        """Test BackupHistory __repr__ method."""
        history = BackupHistory(
            job_id=local_backup_job.id,
            status='success',
            started_at=datetime.utcnow()
        )
        db.session.add(history)
        db.session.commit()

        assert repr(history) == f'<BackupHistory job_id={local_backup_job.id} status=success>'

    def test_backup_history_cascade_delete(self, db):
        """Test that deleting a job deletes its history (cascade)."""
        job = BackupJob(
            name='temp_job',
            enabled=True,
            source_type='local',
            source_config='{}',
            compression_format='tar.gz'
        )
        db.session.add(job)
        db.session.commit()

        job_id = job.id

        history = BackupHistory(
            job_id=job_id,
            status='success',
            started_at=datetime.utcnow()
        )
        db.session.add(history)
        db.session.commit()

        history_id = history.id

        # Delete the job
        db.session.delete(job)
        db.session.commit()

        # History should be deleted too
        assert BackupHistory.query.get(history_id) is None


class TestEncryptionKeyModel:
    """Test EncryptionKey model."""

    def test_create_encryption_key(self, db):
        """Test creating an encryption key."""
        key = EncryptionKey(
            key_encrypted='encrypted_master_key_data'
        )
        db.session.add(key)
        db.session.commit()

        assert key.id is not None
        assert key.key_encrypted == 'encrypted_master_key_data'
        assert key.created_at is not None

    def test_encryption_key_repr(self, db):
        """Test EncryptionKey __repr__ method."""
        key = EncryptionKey(key_encrypted='enc_key')
        db.session.add(key)
        db.session.commit()

        assert repr(key) == f'<EncryptionKey id={key.id}>'

    def test_encryption_key_created_at(self, db):
        """Test that created_at is automatically set."""
        before = datetime.utcnow()
        key = EncryptionKey(key_encrypted='enc_key')
        db.session.add(key)
        db.session.commit()
        after = datetime.utcnow()

        assert before <= key.created_at <= after


class TestModelRelationships:
    """Test relationships between models."""

    def test_backup_job_to_history_relationship(self, db):
        """Test one-to-many relationship from BackupJob to BackupHistory."""
        job = BackupJob(
            name='test_job',
            enabled=True,
            source_type='local',
            source_config='{}',
            compression_format='tar.gz'
        )
        db.session.add(job)
        db.session.commit()

        # Add multiple history records
        for i in range(3):
            history = BackupHistory(
                job_id=job.id,
                status='success',
                started_at=datetime.utcnow()
            )
            db.session.add(history)
        db.session.commit()

        # Query through relationship
        assert job.history.count() == 3

    def test_backup_history_to_job_relationship(self, db, local_backup_job):
        """Test many-to-one relationship from BackupHistory to BackupJob."""
        history = BackupHistory(
            job_id=local_backup_job.id,
            status='success',
            started_at=datetime.utcnow()
        )
        db.session.add(history)
        db.session.commit()

        # Access job through history relationship
        assert history.job == local_backup_job
        assert history.job.name == 'test_local_backup'
