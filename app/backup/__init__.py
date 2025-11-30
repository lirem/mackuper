"""
Backup module for Mackuper.

This module handles the core backup functionality including:
- Source acquisition (local and SSH)
- Compression
- Storage (S3 and local)
- Execution orchestration
- Retention policy enforcement
"""

from .executor import BackupExecutor
from .sources import LocalSource, SSHSource
from .compression import create_archive
from .storage import S3Storage, LocalStorage
from .retention import RetentionManager

__all__ = [
    'BackupExecutor',
    'LocalSource',
    'SSHSource',
    'create_archive',
    'S3Storage',
    'LocalStorage',
    'RetentionManager'
]
