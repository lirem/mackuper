"""
Retention policy enforcement for backups.

Manages cleanup of old backups from both S3 and local storage based on
configured retention policies.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any

from app import db
from app.models import BackupJob, BackupHistory, AWSSettings
from app.utils.crypto import crypto_manager
from .storage import S3Storage, LocalStorage, StorageError


class RetentionManager:
    """
    Manages retention policy enforcement for backup jobs.

    Cleans up old backups from S3 and local storage based on retention_s3_days
    and retention_local_days settings.
    """

    def __init__(self):
        """Initialize retention manager."""
        self.logs = []

    def enforce_all_policies(self) -> Dict[str, Any]:
        """
        Enforce retention policies for all backup jobs.

        Returns:
            Dict with summary of cleanup operations:
            {
                'jobs_processed': int,
                's3_deleted': int,
                'local_deleted': int,
                'errors': List[str],
                'logs': List[str]
            }
        """
        self._log("Starting retention policy enforcement for all jobs")

        jobs = BackupJob.query.all()
        summary = {
            'jobs_processed': 0,
            's3_deleted': 0,
            'local_deleted': 0,
            'errors': []
        }

        for job in jobs:
            try:
                result = self.enforce_job_policy(job)
                summary['jobs_processed'] += 1
                summary['s3_deleted'] += result['s3_deleted']
                summary['local_deleted'] += result['local_deleted']
            except Exception as e:
                error_msg = f"Failed to enforce policy for job {job.name}: {e}"
                self._log(error_msg)
                summary['errors'].append(error_msg)

        self._log(
            f"Retention enforcement complete. "
            f"Jobs: {summary['jobs_processed']}, "
            f"S3 deleted: {summary['s3_deleted']}, "
            f"Local deleted: {summary['local_deleted']}, "
            f"Errors: {len(summary['errors'])}"
        )

        summary['logs'] = self.logs
        return summary

    def enforce_job_policy(self, job: BackupJob) -> Dict[str, int]:
        """
        Enforce retention policy for a specific job.

        Args:
            job: BackupJob instance

        Returns:
            Dict with counts: {'s3_deleted': int, 'local_deleted': int}

        Raises:
            StorageError: If cleanup operations fail
        """
        self._log(f"Enforcing retention policy for job: {job.name}")

        result = {
            's3_deleted': 0,
            'local_deleted': 0
        }

        # Cleanup S3 if retention policy is set
        if job.retention_s3_days is not None:
            self._log(f"S3 retention: {job.retention_s3_days} days")
            result['s3_deleted'] = self._cleanup_s3(job)
        else:
            self._log("S3 retention: not configured, skipping")

        # Cleanup local if retention policy is set
        if job.retention_local_days is not None:
            self._log(f"Local retention: {job.retention_local_days} days")
            result['local_deleted'] = self._cleanup_local(job)
        else:
            self._log("Local retention: not configured, skipping")

        return result

    def _cleanup_s3(self, job: BackupJob) -> int:
        """
        Cleanup old S3 backups for a job.

        Args:
            job: BackupJob instance

        Returns:
            Number of backups deleted

        Raises:
            StorageError: If S3 operations fail
        """
        # Get AWS settings
        aws_settings = AWSSettings.query.first()
        if not aws_settings:
            self._log("AWS settings not configured, skipping S3 cleanup")
            return 0

        # Decrypt credentials
        if not crypto_manager.is_initialized:
            self._log("Crypto manager not initialized, skipping S3 cleanup")
            return 0

        access_key = crypto_manager.decrypt(aws_settings.access_key_encrypted)
        secret_key = crypto_manager.decrypt(aws_settings.secret_key_encrypted)

        # Create S3 storage handler
        s3_storage = S3Storage(
            access_key=access_key,
            secret_key=secret_key,
            bucket_name=aws_settings.bucket_name,
            region=aws_settings.region
        )

        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=job.retention_s3_days)

        # List all objects with job name prefix
        try:
            objects = s3_storage.list_objects(prefix=job.name)
        except StorageError as e:
            self._log(f"Failed to list S3 objects: {e}")
            return 0

        # Filter objects older than cutoff
        to_delete = [
            obj for obj in objects
            if obj['LastModified'].replace(tzinfo=None) < cutoff_date
        ]

        # Delete old objects
        deleted_count = 0
        for obj in to_delete:
            try:
                s3_storage.delete(obj['Key'])
                deleted_count += 1
                self._log(f"Deleted S3 object: {obj['Key']}")

                # Update history records to mark as deleted
                history = BackupHistory.query.filter_by(
                    job_id=job.id,
                    s3_key=obj['Key']
                ).first()
                if history:
                    history.s3_key = None
                    db.session.commit()

            except StorageError as e:
                self._log(f"Failed to delete S3 object {obj['Key']}: {e}")

        return deleted_count

    def _cleanup_local(self, job: BackupJob) -> int:
        """
        Cleanup old local backups for a job.

        Args:
            job: BackupJob instance

        Returns:
            Number of backups deleted

        Raises:
            StorageError: If local operations fail
        """
        from app.config import Config
        local_storage_path = Config.LOCAL_BACKUP_DIR

        # Create local storage handler
        local_storage = LocalStorage(local_storage_path)

        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=job.retention_local_days)

        # List all files for job
        try:
            files = local_storage.list_files(job.name)
        except StorageError as e:
            self._log(f"Failed to list local files: {e}")
            return 0

        # Filter files older than cutoff
        to_delete = [
            f for f in files
            if f['modified'] < cutoff_date
        ]

        # Delete old files
        deleted_count = 0
        for file_info in to_delete:
            try:
                local_storage.delete(file_info['path'])
                deleted_count += 1
                self._log(f"Deleted local file: {file_info['path']}")

                # Update history records to mark as deleted
                history = BackupHistory.query.filter_by(
                    job_id=job.id,
                    local_path=file_info['path']
                ).first()
                if history:
                    history.local_path = None
                    db.session.commit()

            except StorageError as e:
                self._log(f"Failed to delete local file {file_info['path']}: {e}")

        return deleted_count

    def _log(self, message: str):
        """
        Add a log message with timestamp.

        Args:
            message: Log message
        """
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        print(log_entry)  # Also print to console


def enforce_retention_policies() -> Dict[str, Any]:
    """
    Enforce retention policies for all jobs.

    This function should be called by the scheduler on a daily basis.

    Returns:
        Summary dict from RetentionManager.enforce_all_policies()
    """
    manager = RetentionManager()
    return manager.enforce_all_policies()
