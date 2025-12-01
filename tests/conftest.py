"""
Shared pytest fixtures for Mackuper tests.

This module provides fixtures for:
- Flask app and test client
- Database setup with in-memory SQLite
- User and authentication fixtures
- Backup job fixtures
- Mock fixtures for external services (S3, SSH)
- Temporary file fixtures
"""

import os
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import boto3
from moto import mock_aws

from app import create_app, db as _db
from app.models import User, AWSSettings, BackupJob, BackupHistory
from app.auth import hash_password
from app.utils.crypto import CryptoManager


@pytest.fixture(scope='function')
def app():
    """
    Create Flask app with test configuration.

    Uses in-memory SQLite database for fast, isolated tests.
    """
    # Create temp directory for test app
    temp_dir = tempfile.mkdtemp()

    app = create_app('development')

    # Override configuration for testing
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'TEMP_DIR': os.path.join(temp_dir, 'temp'),
        'LOCAL_BACKUP_DIR': os.path.join(temp_dir, 'backups'),
    })

    # Create temp directories
    os.makedirs(app.config['TEMP_DIR'], exist_ok=True)
    os.makedirs(app.config['LOCAL_BACKUP_DIR'], exist_ok=True)

    yield app

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope='function')
def db(app):
    """
    Create database with all tables.

    Each test gets a fresh database.
    """
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Flask test client for making HTTP requests."""
    return app.test_client()


@pytest.fixture(scope='function')
def runner(app):
    """Flask CLI test runner."""
    return app.test_cli_runner()


@pytest.fixture(scope='function')
def admin_user(db):
    """
    Create an admin user for testing authentication.

    Username: admin
    Password: Admin123
    """
    user = User(
        username='admin',
        password_hash=hash_password('Admin123')
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture(scope='function')
def crypto_manager_initialized():
    """
    Create and initialize a CryptoManager instance.

    Password: test_password_123
    """
    cm = CryptoManager()
    salt = cm.initialize('test_password_123')
    return cm, salt


@pytest.fixture(scope='function')
def aws_settings(db, crypto_manager_initialized):
    """
    Create AWS settings with encrypted credentials.

    Uses the initialized CryptoManager to encrypt test AWS keys.
    """
    cm, _ = crypto_manager_initialized

    settings = AWSSettings(
        access_key_encrypted=cm.encrypt('test_access_key_123'),
        secret_key_encrypted=cm.encrypt('test_secret_key_456'),
        bucket_name='test-bucket',
        region='us-east-1'
    )
    db.session.add(settings)
    db.session.commit()
    return settings


@pytest.fixture(scope='function')
def local_backup_job(db):
    """
    Create a backup job with local source configuration.
    """
    job = BackupJob(
        name='test_local_backup',
        description='Test local backup job',
        enabled=True,
        source_type='local',
        source_config=json.dumps({
            'paths': ['/tmp/test_data'],
            'exclude_patterns': ['*.pyc', '__pycache__', '.git']
        }),
        compression_format='tar.gz',
        schedule_cron='0 2 * * *',  # Daily at 2 AM
        retention_s3_days=30,
        retention_local_days=7
    )
    db.session.add(job)
    db.session.commit()
    return job


@pytest.fixture(scope='function')
def ssh_backup_job(db):
    """
    Create a backup job with SSH source configuration.
    """
    job = BackupJob(
        name='test_ssh_backup',
        description='Test SSH backup job',
        enabled=True,
        source_type='ssh',
        source_config=json.dumps({
            'host': 'test.example.com',
            'port': 22,
            'username': 'testuser',
            'password': 'testpass',
            'paths': ['/remote/data']
        }),
        compression_format='zip',
        schedule_cron='0 3 * * *',  # Daily at 3 AM
        retention_s3_days=14,
        retention_local_days=None  # No local storage
    )
    db.session.add(job)
    db.session.commit()
    return job


@pytest.fixture(scope='function')
def backup_history(db, local_backup_job):
    """
    Create a backup history record for testing.
    """
    from datetime import datetime

    history = BackupHistory(
        job_id=local_backup_job.id,
        status='success',
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        file_size_bytes=1024000,  # 1MB
        s3_key='test_local_backup/2024/01/backup_20240115_120000.tar.gz',
        local_path='test_local_backup/backup_20240115_120000.tar.gz',
        logs='[2024-01-15 12:00:00] Backup started\n[2024-01-15 12:00:05] Backup completed'
    )
    db.session.add(history)
    db.session.commit()
    return history


@pytest.fixture
def mock_s3():
    """
    Mock AWS S3 service using moto.

    Creates a test bucket 'test-bucket' in us-east-1 region.
    """
    with mock_aws():
        # Create mock S3 resource
        s3 = boto3.resource('s3', region_name='us-east-1')

        # Create test bucket
        s3.create_bucket(Bucket='test-bucket')

        yield s3


@pytest.fixture
def mock_ssh_client():
    """
    Mock paramiko SSHClient for SSH/SFTP testing.

    Returns a MagicMock that simulates SSH connections.
    """
    with patch('paramiko.SSHClient') as mock_ssh:
        # Mock SFTP client
        mock_sftp = MagicMock()
        mock_ssh.return_value.open_sftp.return_value = mock_sftp

        # Mock connection success
        mock_ssh.return_value.connect.return_value = None

        yield mock_ssh


@pytest.fixture
def temp_files(tmp_path):
    """
    Create temporary test files and directories.

    Creates:
    - test_file1.txt
    - test_file2.log
    - nested/test_file3.txt
    - test_file.pyc (should be excluded in tests)
    """
    # Create files
    (tmp_path / 'test_file1.txt').write_text('Test content 1')
    (tmp_path / 'test_file2.log').write_text('Test log content')

    # Create nested directory
    nested_dir = tmp_path / 'nested'
    nested_dir.mkdir()
    (nested_dir / 'test_file3.txt').write_text('Nested test content')

    # Create file that should be excluded
    (tmp_path / 'test_file.pyc').write_bytes(b'compiled python')

    return tmp_path


@pytest.fixture
def sample_archive(tmp_path):
    """
    Create a sample archive file for testing.
    """
    import tarfile

    # Create some test files
    test_dir = tmp_path / 'test_data'
    test_dir.mkdir()
    (test_dir / 'file1.txt').write_text('Content 1')
    (test_dir / 'file2.txt').write_text('Content 2')

    # Create archive
    archive_path = tmp_path / 'test_archive.tar.gz'
    with tarfile.open(archive_path, 'w:gz') as tar:
        tar.add(test_dir, arcname='test_data')

    return archive_path


@pytest.fixture(scope='function')
def mock_scheduler():
    """
    Mock APScheduler for testing scheduler functionality.
    """
    with patch('app.scheduler.BackgroundScheduler') as mock_sched:
        scheduler_instance = MagicMock()
        mock_sched.return_value = scheduler_instance

        # Mock scheduler methods
        scheduler_instance.running = False
        scheduler_instance.state = 0
        scheduler_instance.get_jobs.return_value = []

        yield scheduler_instance
