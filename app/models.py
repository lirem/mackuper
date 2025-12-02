from datetime import datetime
from flask_login import UserMixin
from app import db


class User(UserMixin, db.Model):
    """User model for authentication"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'


class AWSSettings(db.Model):
    """AWS S3 configuration"""
    __tablename__ = 'aws_settings'

    id = db.Column(db.Integer, primary_key=True)
    access_key_encrypted = db.Column(db.Text, nullable=False)
    secret_key_encrypted = db.Column(db.Text, nullable=False)
    bucket_name = db.Column(db.String(255), nullable=False)
    region = db.Column(db.String(50), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<AWSSettings bucket={self.bucket_name} region={self.region}>'


class BackupJob(db.Model):
    """Backup job configuration"""
    __tablename__ = 'backup_jobs'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    source_type = db.Column(db.String(20), nullable=False)  # 'local' or 'ssh'
    source_config = db.Column(db.Text, nullable=False)  # JSON string
    ssh_password_encrypted = db.Column(db.Text, nullable=True)  # Encrypted SSH password (only for SSH jobs with passwords)
    compression_format = db.Column(db.String(20), nullable=False)  # zip, tar.gz, tar.bz2, tar.xz, none
    schedule_cron = db.Column(db.String(100))  # Cron expression
    retention_s3_days = db.Column(db.Integer)  # Days to keep in S3
    retention_local_days = db.Column(db.Integer)  # Days to keep locally (null = don't store)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    history = db.relationship('BackupHistory', back_populates='job', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f'<BackupJob {self.name} type={self.source_type} enabled={self.enabled}>'


class BackupHistory(db.Model):
    """Backup execution history and logs"""
    __tablename__ = 'backup_history'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('backup_jobs.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # running, success, failed, cancelling, cancelled
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)
    file_size_bytes = db.Column(db.BigInteger)
    s3_key = db.Column(db.String(500))
    local_path = db.Column(db.String(500))
    error_message = db.Column(db.Text)
    logs = db.Column(db.Text)  # Detailed execution logs
    cancellation_requested = db.Column(db.Boolean, default=False, nullable=False)  # User requested cancellation

    # Relationship
    job = db.relationship('BackupJob', back_populates='history')

    def __repr__(self):
        return f'<BackupHistory job_id={self.job_id} status={self.status}>'


class EncryptionKey(db.Model):
    """Master encryption key storage"""
    __tablename__ = 'encryption_key'

    id = db.Column(db.Integer, primary_key=True)
    key_encrypted = db.Column(db.Text, nullable=False)  # Actually stores salt (misleading name)
    password_encrypted = db.Column(db.Text, nullable=True)  # Encrypted user password for auto-unlock
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    def __repr__(self):
        return f'<EncryptionKey id={self.id} has_password={self.password_encrypted is not None}>'
