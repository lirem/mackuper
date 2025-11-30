"""
Source handlers for backup operations.

Supports:
- LocalSource: Access files from the local filesystem
- SSHSource: Access files from remote systems via SSH/SFTP
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Any
from fnmatch import fnmatch
import paramiko
from paramiko import SSHClient, AutoAddPolicy


class SourceError(Exception):
    """Raised when source acquisition fails."""
    pass


class LocalSource:
    """
    Handler for local filesystem sources.

    Copies files/directories from the local filesystem to a temporary directory
    for archiving.
    """

    def __init__(self, paths: List[str], exclude_patterns: List[str] = None):
        """
        Initialize local source handler.

        Args:
            paths: List of file/directory paths to backup
            exclude_patterns: List of glob patterns to exclude (e.g., *.pyc, __pycache__, .venv)
        """
        self.paths = paths
        self.exclude_patterns = exclude_patterns or []
        self.temp_dir = None

    def _should_exclude(self, path: Path) -> bool:
        """
        Check if a path should be excluded based on exclude patterns.

        Args:
            path: Path to check

        Returns:
            True if path matches any exclude pattern, False otherwise
        """
        if not self.exclude_patterns:
            return False

        path_str = str(path)
        path_name = path.name

        for pattern in self.exclude_patterns:
            # Match against full path or just the name
            if fnmatch(path_str, pattern) or fnmatch(path_name, pattern):
                return True
            # Also match against relative path patterns
            if pattern.startswith('**/') and fnmatch(path_name, pattern[3:]):
                return True

        return False

    def acquire(self, temp_dir: str) -> List[str]:
        """
        Copy source files to temporary directory.

        Args:
            temp_dir: Temporary directory to copy files into

        Returns:
            List of paths in temp_dir that were copied

        Raises:
            SourceError: If any path cannot be accessed
        """
        self.temp_dir = temp_dir
        acquired_paths = []

        for path in self.paths:
            source_path = Path(path).expanduser().resolve()

            if not source_path.exists():
                raise SourceError(f"Path does not exist: {path}")

            # Create relative path structure in temp dir
            # Use just the basename to avoid deep nesting
            dest_name = source_path.name
            dest_path = Path(temp_dir) / dest_name

            try:
                if source_path.is_file():
                    if not self._should_exclude(source_path):
                        shutil.copy2(source_path, dest_path)
                        acquired_paths.append(str(dest_path))
                elif source_path.is_dir():
                    # Use ignore parameter to exclude patterns during copytree
                    def ignore_patterns(directory, files):
                        ignored = []
                        for name in files:
                            file_path = Path(directory) / name
                            if self._should_exclude(file_path):
                                ignored.append(name)
                        return ignored

                    shutil.copytree(source_path, dest_path, symlinks=False, ignore=ignore_patterns)
                    acquired_paths.append(str(dest_path))
                else:
                    raise SourceError(f"Unsupported path type: {path}")
            except PermissionError as e:
                raise SourceError(f"Permission denied accessing {path}: {e}")
            except Exception as e:
                raise SourceError(f"Failed to copy {path}: {e}")

        return acquired_paths

    def cleanup(self):
        """Cleanup any resources. Local source has no persistent connections."""
        pass


class SSHSource:
    """
    Handler for remote filesystem sources via SSH/SFTP.

    Downloads files/directories from a remote system via SSH to a temporary
    directory for archiving.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize SSH source handler.

        Args:
            config: SSH configuration dict with keys:
                - host: SSH hostname or IP
                - port: SSH port (default 22)
                - username: SSH username
                - password: SSH password (optional if using key)
                - private_key: Path to private key file (optional)
                - paths: List of remote paths to backup
        """
        self.host = config.get('host') or config.get('hostname')
        self.port = config.get('port', 22)
        self.username = config.get('username')
        self.password = config.get('password')
        self.private_key_path = config.get('private_key')
        self.paths = config.get('paths', [])

        self.ssh_client = None
        self.sftp_client = None
        self.temp_dir = None

    def _connect(self):
        """
        Establish SSH connection.

        Raises:
            SourceError: If connection fails
        """
        try:
            self.ssh_client = SSHClient()
            self.ssh_client.set_missing_host_key_policy(AutoAddPolicy())

            # Prepare connection kwargs
            connect_kwargs = {
                'hostname': self.host,
                'port': self.port,
                'username': self.username,
                'timeout': 30
            }

            # Use password or private key
            if self.password:
                connect_kwargs['password'] = self.password
            elif self.private_key_path:
                key_path = Path(self.private_key_path).expanduser()
                if not key_path.exists():
                    raise SourceError(f"Private key not found: {self.private_key_path}")
                connect_kwargs['key_filename'] = str(key_path)
            else:
                raise SourceError("Either password or private_key must be provided")

            self.ssh_client.connect(**connect_kwargs)
            self.sftp_client = self.ssh_client.open_sftp()

        except paramiko.AuthenticationException as e:
            raise SourceError(f"SSH authentication failed: {e}")
        except paramiko.SSHException as e:
            raise SourceError(f"SSH connection failed: {e}")
        except Exception as e:
            raise SourceError(f"Failed to connect to {self.host}: {e}")

    def _download_file(self, remote_path: str, local_path: str):
        """
        Download a single file via SFTP.

        Args:
            remote_path: Remote file path
            local_path: Local destination path
        """
        try:
            self.sftp_client.get(remote_path, local_path)
        except FileNotFoundError:
            raise SourceError(f"Remote file not found: {remote_path}")
        except PermissionError:
            raise SourceError(f"Permission denied accessing remote file: {remote_path}")
        except Exception as e:
            raise SourceError(f"Failed to download {remote_path}: {e}")

    def _download_directory(self, remote_path: str, local_path: str):
        """
        Recursively download a directory via SFTP.

        Args:
            remote_path: Remote directory path
            local_path: Local destination path
        """
        try:
            # Create local directory
            Path(local_path).mkdir(parents=True, exist_ok=True)

            # List remote directory
            for item in self.sftp_client.listdir_attr(remote_path):
                remote_item = f"{remote_path}/{item.filename}".replace('//', '/')
                local_item = Path(local_path) / item.filename

                # Check if item is a directory (S_ISDIR)
                if item.st_mode & 0o040000:  # Directory
                    self._download_directory(remote_item, str(local_item))
                else:  # File
                    self._download_file(remote_item, str(local_item))

        except FileNotFoundError:
            raise SourceError(f"Remote directory not found: {remote_path}")
        except PermissionError:
            raise SourceError(f"Permission denied accessing remote directory: {remote_path}")
        except Exception as e:
            raise SourceError(f"Failed to download directory {remote_path}: {e}")

    def acquire(self, temp_dir: str) -> List[str]:
        """
        Download source files to temporary directory.

        Args:
            temp_dir: Temporary directory to download files into

        Returns:
            List of paths in temp_dir that were downloaded

        Raises:
            SourceError: If connection or download fails
        """
        self.temp_dir = temp_dir
        self._connect()

        acquired_paths = []

        for remote_path in self.paths:
            # Get just the basename for local storage
            basename = os.path.basename(remote_path.rstrip('/'))
            local_path = Path(temp_dir) / basename

            try:
                # Check if remote path is a file or directory
                stat = self.sftp_client.stat(remote_path)

                if stat.st_mode & 0o040000:  # Directory
                    self._download_directory(remote_path, str(local_path))
                else:  # File
                    self._download_file(remote_path, str(local_path))

                acquired_paths.append(str(local_path))

            except FileNotFoundError:
                raise SourceError(f"Remote path not found: {remote_path}")
            except Exception as e:
                raise SourceError(f"Failed to acquire {remote_path}: {e}")

        return acquired_paths

    def cleanup(self):
        """Close SSH/SFTP connections."""
        if self.sftp_client:
            try:
                self.sftp_client.close()
            except:
                pass
            self.sftp_client = None

        if self.ssh_client:
            try:
                self.ssh_client.close()
            except:
                pass
            self.ssh_client = None


def create_source(source_type: str, config: Dict[str, Any]):
    """
    Factory function to create appropriate source handler.

    Args:
        source_type: 'local' or 'ssh'
        config: Configuration dict for the source

    Returns:
        LocalSource or SSHSource instance

    Raises:
        ValueError: If source_type is invalid
    """
    if source_type == 'local':
        paths = config.get('paths', [])
        exclude_patterns = config.get('exclude_patterns', [])
        return LocalSource(paths, exclude_patterns)
    elif source_type == 'ssh':
        return SSHSource(config)
    else:
        raise ValueError(f"Invalid source type: {source_type}")
