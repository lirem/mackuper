"""
Storage handlers for backup archives.

Supports:
- S3Storage: Upload to AWS S3
- LocalStorage: Store in local directory
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import boto3
from botocore.exceptions import ClientError, BotoCoreError


class StorageError(Exception):
    """Raised when storage operation fails."""
    pass


class S3Storage:
    """
    Handler for uploading backups to AWS S3.

    Uploads archives to S3 with a structured key format:
    {job_name}/{YYYY}/{MM}/{filename}
    """

    def __init__(self, access_key: str, secret_key: str, bucket_name: str, region: str = 'us-east-1'):
        """
        Initialize S3 storage handler.

        Args:
            access_key: AWS access key ID
            secret_key: AWS secret access key
            bucket_name: S3 bucket name
            region: AWS region (default: us-east-1)
        """
        self.bucket_name = bucket_name
        self.region = region

        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region
            )
        except Exception as e:
            raise StorageError(f"Failed to initialize S3 client: {e}")

    def upload(self, local_path: str, job_name: str, cancellation_check: Optional[callable] = None) -> str:
        """
        Upload archive to S3.

        Args:
            local_path: Path to local archive file
            job_name: Name of the backup job (used for S3 key structure)
            cancellation_check: Optional function to call periodically to check if operation should be cancelled

        Returns:
            S3 key of uploaded file

        Raises:
            StorageError: If upload fails
        """
        if not os.path.exists(local_path):
            raise StorageError(f"Local file not found: {local_path}")

        # Generate S3 key: {job_name}/{YYYY}/{MM}/{filename}
        filename = os.path.basename(local_path)
        now = datetime.now()
        s3_key = f"{job_name}/{now.year}/{now.month:02d}/{filename}"

        try:
            # Upload file with progress tracking
            file_size = os.path.getsize(local_path)

            # Use multipart upload for files larger than 100MB
            if file_size > 100 * 1024 * 1024:  # 100MB
                self._multipart_upload(local_path, s3_key, file_size, cancellation_check)
            else:
                # Check for cancellation before simple upload
                if cancellation_check:
                    cancellation_check()
                self._simple_upload(local_path, s3_key)

            return s3_key

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            raise StorageError(f"S3 upload failed ({error_code}): {e}")
        except BotoCoreError as e:
            raise StorageError(f"S3 upload failed: {e}")
        except Exception as e:
            raise StorageError(f"Failed to upload to S3: {e}")

    def _simple_upload(self, local_path: str, s3_key: str):
        """
        Upload file using simple put_object.

        Args:
            local_path: Path to local file
            s3_key: S3 object key
        """
        with open(local_path, 'rb') as f:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=f
            )

    def _multipart_upload(self, local_path: str, s3_key: str, file_size: int, cancellation_check: Optional[callable] = None):
        """
        Upload large file using multipart upload with cancellation support.

        Args:
            local_path: Path to local file
            s3_key: S3 object key
            file_size: Size of file in bytes
            cancellation_check: Optional function to call between chunks to check for cancellation
        """
        # 10MB chunks
        chunk_size = 10 * 1024 * 1024

        # Initiate multipart upload
        response = self.s3_client.create_multipart_upload(
            Bucket=self.bucket_name,
            Key=s3_key
        )
        upload_id = response['UploadId']

        parts = []

        try:
            with open(local_path, 'rb') as f:
                part_number = 1

                while True:
                    # Check for cancellation before each chunk
                    if cancellation_check:
                        cancellation_check()

                    data = f.read(chunk_size)
                    if not data:
                        break

                    # Upload part
                    response = self.s3_client.upload_part(
                        Bucket=self.bucket_name,
                        Key=s3_key,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=data
                    )

                    parts.append({
                        'PartNumber': part_number,
                        'ETag': response['ETag']
                    })

                    part_number += 1

            # Complete multipart upload
            self.s3_client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )

        except Exception as e:
            # Abort multipart upload on error or cancellation
            try:
                self.s3_client.abort_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    UploadId=upload_id
                )
            except:
                pass
            raise e

    def delete(self, s3_key: str):
        """
        Delete an object from S3.

        Args:
            s3_key: S3 object key to delete

        Raises:
            StorageError: If deletion fails
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            raise StorageError(f"S3 delete failed ({error_code}): {e}")
        except Exception as e:
            raise StorageError(f"Failed to delete from S3: {e}")

    def list_objects(self, prefix: str) -> list:
        """
        List objects in S3 with given prefix.

        Args:
            prefix: S3 key prefix to filter by

        Returns:
            List of dicts with 'Key', 'LastModified', and 'Size' keys

        Raises:
            StorageError: If listing fails
        """
        try:
            objects = []
            paginator = self.s3_client.get_paginator('list_objects_v2')

            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects.append({
                            'Key': obj['Key'],
                            'LastModified': obj['LastModified'],
                            'Size': obj['Size']
                        })

            return objects

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            raise StorageError(f"S3 list failed ({error_code}): {e}")
        except Exception as e:
            raise StorageError(f"Failed to list S3 objects: {e}")

    def test_connection(self) -> bool:
        """
        Test S3 connection and bucket access.

        Returns:
            True if connection is successful

        Raises:
            StorageError: If connection test fails
        """
        try:
            # Try to head the bucket
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == '404':
                raise StorageError(f"Bucket does not exist: {self.bucket_name}")
            elif error_code == '403':
                raise StorageError(f"Access denied to bucket: {self.bucket_name}")
            else:
                raise StorageError(f"S3 connection test failed ({error_code}): {e}")
        except Exception as e:
            raise StorageError(f"Failed to connect to S3: {e}")


class LocalStorage:
    """
    Handler for storing backups in local filesystem.

    Stores archives in a local directory with the same structure as S3:
    {base_path}/{job_name}/{YYYY}/{MM}/{filename}
    """

    def __init__(self, base_path: str):
        """
        Initialize local storage handler.

        Args:
            base_path: Base directory for local backups
        """
        self.base_path = Path(base_path)

        # Create base directory if it doesn't exist
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise StorageError(f"Failed to create local storage directory: {e}")

    def store(self, source_path: str, job_name: str) -> str:
        """
        Copy archive to local storage.

        Args:
            source_path: Path to source archive file
            job_name: Name of the backup job

        Returns:
            Relative path of stored file (from base_path)

        Raises:
            StorageError: If storage fails
        """
        if not os.path.exists(source_path):
            raise StorageError(f"Source file not found: {source_path}")

        # Generate local path: {job_name}/{YYYY}/{MM}/{filename}
        filename = os.path.basename(source_path)
        now = datetime.now()
        relative_path = f"{job_name}/{now.year}/{now.month:02d}/{filename}"
        dest_path = self.base_path / relative_path

        try:
            # Create directory structure
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(source_path, dest_path)

            return relative_path

        except PermissionError as e:
            raise StorageError(f"Permission denied writing to {dest_path}: {e}")
        except Exception as e:
            raise StorageError(f"Failed to store locally: {e}")

    def delete(self, relative_path: str):
        """
        Delete a file from local storage.

        Args:
            relative_path: Relative path of file to delete

        Raises:
            StorageError: If deletion fails
        """
        full_path = self.base_path / relative_path

        try:
            if full_path.exists():
                full_path.unlink()
        except PermissionError as e:
            raise StorageError(f"Permission denied deleting {full_path}: {e}")
        except Exception as e:
            raise StorageError(f"Failed to delete local file: {e}")

    def list_files(self, job_name: str) -> list:
        """
        List all backup files for a job.

        Args:
            job_name: Name of the backup job

        Returns:
            List of dicts with 'path', 'modified', and 'size' keys

        Raises:
            StorageError: If listing fails
        """
        job_path = self.base_path / job_name

        if not job_path.exists():
            return []

        try:
            files = []

            for file_path in job_path.rglob('*'):
                if file_path.is_file():
                    stat = file_path.stat()
                    relative_path = file_path.relative_to(self.base_path)

                    files.append({
                        'path': str(relative_path),
                        'modified': datetime.fromtimestamp(stat.st_mtime),
                        'size': stat.st_size
                    })

            return files

        except Exception as e:
            raise StorageError(f"Failed to list local files: {e}")

    def get_full_path(self, relative_path: str) -> str:
        """
        Get full filesystem path from relative path.

        Args:
            relative_path: Relative path from base_path

        Returns:
            Full filesystem path
        """
        return str(self.base_path / relative_path)
