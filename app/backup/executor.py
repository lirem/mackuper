"""
Backup executor - orchestrates the complete backup workflow.

Workflow:
1. Create BackupHistory record (status: running)
2. Acquire source files (local or SSH)
3. Create compressed archive
4. Upload to S3
5. Store locally (if configured)
6. Cleanup temporary files
7. Update BackupHistory (status: success/failed)
"""

import os
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from app import db
from app.models import BackupJob, BackupHistory, AWSSettings
from app.utils.crypto import crypto_manager
from .sources import create_source, SourceError
from .compression import create_archive, generate_archive_filename, strip_archive_extension, get_archive_size, CompressionError
from .storage import S3Storage, LocalStorage, StorageError


class BackupExecutor:
    """
    Orchestrates the complete backup workflow for a job.
    """

    def __init__(self, job: BackupJob):
        """
        Initialize backup executor.

        Args:
            job: BackupJob instance to execute
        """
        self.job = job
        self.history_record = None
        self.temp_dir = None
        self.archive_path = None
        self.logs = []
        self._log_flush_counter = 0

    def execute(self) -> BackupHistory:
        """
        Execute the backup job.

        Returns:
            BackupHistory record with execution results

        Raises:
            Exception: Various exceptions may be raised and logged to history
        """
        # Create history record
        self.history_record = BackupHistory(
            job_id=self.job.id,
            status='running',
            started_at=datetime.utcnow()
        )
        db.session.add(self.history_record)
        db.session.commit()

        self._log(f"Starting backup job: {self.job.name}")

        try:
            # Execute backup workflow
            self._execute_workflow()

            # Mark as success
            self.history_record.status = 'success'
            self.history_record.completed_at = datetime.utcnow()
            self._log(f"Backup completed successfully")

        except Exception as e:
            # Mark as failed
            self.history_record.status = 'failed'
            self.history_record.completed_at = datetime.utcnow()
            self.history_record.error_message = str(e)
            self._log(f"Backup failed: {e}")

        finally:
            # Save logs
            self.history_record.logs = '\n'.join(self.logs)
            db.session.commit()

            # Cleanup temporary files
            self._cleanup()

        return self.history_record

    def _execute_workflow(self):
        """Execute the main backup workflow steps."""
        # Step 1: Create temporary directory
        self._log("Creating temporary directory")
        self.temp_dir = tempfile.mkdtemp(prefix='mackuper_backup_')
        self._log(f"Temporary directory: {self.temp_dir}")
        self._flush_logs_to_db()

        # Step 2: Acquire source files
        self._log(f"Acquiring source files (type: {self.job.source_type})")
        acquired_paths = self._acquire_sources()
        self._log(f"Acquired {len(acquired_paths)} items")
        self._flush_logs_to_db()

        # Step 3: Create archive
        self._log(f"Creating archive (format: {self.job.compression_format})")
        self.archive_path = self._create_archive(acquired_paths)
        file_size = get_archive_size(self.archive_path)
        self.history_record.file_size_bytes = file_size
        self._log(f"Archive created: {os.path.basename(self.archive_path)} ({file_size / 1024 / 1024:.2f} MB)")
        self._flush_logs_to_db()

        # Step 4: Upload to S3
        self._log("Uploading to S3")
        s3_key = self._upload_to_s3()
        self.history_record.s3_key = s3_key
        self._log(f"Uploaded to S3: {s3_key}")
        self._flush_logs_to_db()

        # Step 5: Store locally (if configured)
        if self.job.retention_local_days is not None:
            self._log("Storing local copy")
            local_path = self._store_locally()
            self.history_record.local_path = local_path
            self._log(f"Stored locally: {local_path}")
        else:
            self._log("Local storage not configured, skipping")

    def _acquire_sources(self) -> List[str]:
        """
        Acquire source files from local or SSH source.

        Returns:
            List of paths in temp directory

        Raises:
            SourceError: If source acquisition fails
        """
        # Parse source config
        source_config = json.loads(self.job.source_config)

        # For SSH jobs, decrypt password and inject into config
        if self.job.source_type == 'ssh':
            # Check if password is encrypted in new column
            if self.job.ssh_password_encrypted:
                # Decrypt password
                if not crypto_manager.is_initialized:
                    raise SourceError(
                        "Crypto manager not initialized. Cannot decrypt SSH password. "
                        "This usually means the application needs to be restarted or user needs to log in."
                    )

                try:
                    decrypted_password = crypto_manager.decrypt(self.job.ssh_password_encrypted)
                    source_config['password'] = decrypted_password
                    self._log("SSH password decrypted successfully")
                except Exception as e:
                    raise SourceError(f"Failed to decrypt SSH password: {e}")

            # Legacy support: password might still be in source_config (not yet migrated)
            elif 'password' in source_config:
                self._log("Using legacy plaintext SSH password (migration pending)")

            # No password in either location - using private key only
            else:
                self._log("No SSH password found - using private key authentication")

        # Create appropriate source handler
        source = create_source(self.job.source_type, source_config)

        try:
            # Acquire files to temp directory
            acquired_paths = source.acquire(self.temp_dir)
            return acquired_paths
        finally:
            # Always cleanup source connections
            source.cleanup()

    def _create_archive(self, source_paths: List[str]) -> str:
        """
        Create compressed archive from source paths.

        Args:
            source_paths: List of paths to include in archive

        Returns:
            Path to created archive file

        Raises:
            CompressionError: If archive creation fails
        """
        # Generate archive filename with timestamp
        filename = generate_archive_filename(self.job.name, self.job.compression_format)

        # Strip extension (create_archive adds it back)
        filename_without_ext = strip_archive_extension(filename)

        # Create archive in temp directory
        archive_base = os.path.join(self.temp_dir, filename_without_ext)

        # Create archive
        archive_path = create_archive(
            source_paths,
            archive_base,
            self.job.compression_format
        )

        return archive_path

    def _upload_to_s3(self) -> str:
        """
        Upload archive to S3.

        Returns:
            S3 key of uploaded file

        Raises:
            StorageError: If upload fails
        """
        # Get AWS settings
        aws_settings = AWSSettings.query.first()
        if not aws_settings:
            raise StorageError("AWS settings not configured")

        # Decrypt AWS credentials
        if not crypto_manager.is_initialized:
            raise StorageError("Crypto manager not initialized")

        access_key = crypto_manager.decrypt(aws_settings.access_key_encrypted)
        secret_key = crypto_manager.decrypt(aws_settings.secret_key_encrypted)

        # Create S3 storage handler
        s3_storage = S3Storage(
            access_key=access_key,
            secret_key=secret_key,
            bucket_name=aws_settings.bucket_name,
            region=aws_settings.region
        )

        # Upload archive
        s3_key = s3_storage.upload(self.archive_path, self.job.name)
        return s3_key

    def _store_locally(self) -> str:
        """
        Store archive in local storage.

        Returns:
            Relative path in local storage

        Raises:
            StorageError: If storage fails
        """
        # Get local storage path from config
        from app.config import Config
        local_storage_path = Config.LOCAL_BACKUP_DIR

        # Create local storage handler
        local_storage = LocalStorage(local_storage_path)

        # Store archive
        local_path = local_storage.store(self.archive_path, self.job.name)
        return local_path

    def _cleanup(self):
        """Remove temporary directory and files."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                self._log(f"Cleaned up temporary directory")
            except Exception as e:
                self._log(f"Warning: Failed to cleanup temp directory: {e}")

    def _log(self, message: str):
        """
        Add a log message with timestamp.

        Args:
            message: Log message
        """
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        print(log_entry)  # Also print to console for debugging

        # Flush logs every 5 entries
        self._log_flush_counter += 1
        if self._log_flush_counter >= 5:
            self._flush_logs_to_db()

    def _flush_logs_to_db(self):
        """Flush accumulated logs to database for real-time visibility."""
        if self.history_record:
            self.history_record.logs = '\n'.join(self.logs)
            db.session.commit()
            self._log_flush_counter = 0


def execute_backup_job(job_id: int, allow_disabled: bool = False) -> BackupHistory:
    """
    Execute a backup job by ID.

    Args:
        job_id: ID of BackupJob to execute
        allow_disabled: If True, allow execution of disabled jobs (for manual triggers)

    Returns:
        BackupHistory record with execution results

    Raises:
        ValueError: If job not found, or if disabled and not allowed
    """
    job = BackupJob.query.get(job_id)

    if not job:
        raise ValueError(f"Backup job not found: {job_id}")

    if not job.enabled and not allow_disabled:
        raise ValueError(f"Backup job is disabled: {job.name}")

    executor = BackupExecutor(job)
    return executor.execute()


def execute_backup_job_by_name(job_name: str) -> BackupHistory:
    """
    Execute a backup job by name.

    Args:
        job_name: Name of BackupJob to execute

    Returns:
        BackupHistory record with execution results

    Raises:
        ValueError: If job not found or disabled
    """
    job = BackupJob.query.filter_by(name=job_name).first()

    if not job:
        raise ValueError(f"Backup job not found: {job_name}")

    if not job.enabled:
        raise ValueError(f"Backup job is disabled: {job_name}")

    executor = BackupExecutor(job)
    return executor.execute()
