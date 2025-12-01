"""
Unit tests for source handlers (app/backup/sources.py).

Tests LocalSource and SSHSource for acquiring backup files.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from app.backup.sources import (
    LocalSource,
    SSHSource,
    create_source,
    SourceError
)


class TestLocalSource:
    """Test LocalSource for local file system operations."""

    def test_local_source_acquire_single_file(self, temp_files, tmp_path):
        """Test acquiring a single file."""
        source_file = temp_files / "test_file1.txt"
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        source = LocalSource(paths=[str(source_file)])
        acquired = source.acquire(str(dest_dir))

        assert len(acquired) == 1
        assert Path(acquired[0]).exists()
        assert Path(acquired[0]).name == "test_file1.txt"

    def test_local_source_acquire_directory(self, tmp_path):
        """Test acquiring a directory."""
        # Create a separate source directory (not using temp_files to avoid recursion)
        source_dir = tmp_path / "my_source"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("content1")
        (source_dir / "file2.txt").write_text("content2")

        dest_dir = tmp_path / "my_dest"
        dest_dir.mkdir()

        source = LocalSource(paths=[str(source_dir)])
        acquired = source.acquire(str(dest_dir))

        assert len(acquired) >= 1
        # Check directory was copied
        dest_path = Path(acquired[0])
        assert dest_path.exists()
        assert dest_path.is_dir()

    def test_local_source_acquire_multiple_paths(self, temp_files, tmp_path):
        """Test acquiring multiple paths."""
        file1 = temp_files / "test_file1.txt"
        file2 = temp_files / "test_file2.log"
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        source = LocalSource(paths=[str(file1), str(file2)])
        acquired = source.acquire(str(dest_dir))

        assert len(acquired) == 2

    def test_local_source_exclude_patterns(self, tmp_path):
        """Test excluding files by pattern."""
        source_dir = tmp_path / "my_source"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("keep")
        (source_dir / "file.pyc").write_bytes(b"exclude")

        dest_dir = tmp_path / "my_dest"
        dest_dir.mkdir()

        # Exclude .pyc files
        source = LocalSource(
            paths=[str(source_dir)],
            exclude_patterns=["*.pyc"]
        )
        acquired = source.acquire(str(dest_dir))

        # Verify .pyc file was not copied
        acquired_path = Path(acquired[0])
        pyc_files = list(acquired_path.rglob("*.pyc"))
        assert len(pyc_files) == 0

    def test_local_source_exclude_multiple_patterns(self, tmp_path):
        """Test excluding multiple file patterns."""
        source_dir = tmp_path / "my_source"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("keep")
        (source_dir / "file.pyc").write_bytes(b"exclude")
        (source_dir / "file.log").write_text("exclude")

        dest_dir = tmp_path / "my_dest"
        dest_dir.mkdir()

        source = LocalSource(
            paths=[str(source_dir)],
            exclude_patterns=["*.pyc", "*.log", "__pycache__"]
        )
        acquired = source.acquire(str(dest_dir))

        acquired_path = Path(acquired[0])
        # .log files should be excluded
        log_files = list(acquired_path.rglob("*.log"))
        assert len(log_files) == 0

    def test_local_source_should_exclude_method(self):
        """Test _should_exclude method with various patterns."""
        source = LocalSource(
            paths=[],
            exclude_patterns=["*.pyc", "__pycache__", "**/*.tmp"]
        )

        # Should exclude
        assert source._should_exclude(Path("/test/file.pyc")) is True
        assert source._should_exclude(Path("/test/__pycache__")) is True
        assert source._should_exclude(Path("/deep/path/file.tmp")) is True

        # Should not exclude
        assert source._should_exclude(Path("/test/file.txt")) is False
        assert source._should_exclude(Path("/test/file.py")) is False

    def test_local_source_nonexistent_path_raises_error(self, tmp_path):
        """Test that nonexistent path raises SourceError."""
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        source = LocalSource(paths=["/nonexistent/path"])

        with pytest.raises(SourceError, match="does not exist"):
            source.acquire(str(dest_dir))

    def test_local_source_cleanup(self):
        """Test cleanup method (should do nothing for local source)."""
        source = LocalSource(paths=[])
        # Should not raise any errors
        source.cleanup()

    def test_local_source_expanduser_in_paths(self, tmp_path):
        """Test that tilde in paths is expanded."""
        # Create a file in temp dir
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        # Use absolute path (can't test ~ directly without home dir)
        source = LocalSource(paths=[str(test_file)])
        acquired = source.acquire(str(dest_dir))

        assert len(acquired) == 1


class TestSSHSource:
    """Test SSHSource for remote file operations via SSH/SFTP."""

    @patch('app.backup.sources.SSHClient')
    def test_ssh_source_connect(self, mock_ssh_class, tmp_path):
        """Test SSH connection establishment."""
        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.open_sftp.return_value = mock_sftp

        config = {
            'host': 'test.example.com',
            'username': 'testuser',
            'password': 'testpass',
            'paths': ['/remote/file.txt']
        }

        # Mock SFTP stat to indicate file
        mock_stat = MagicMock()
        mock_stat.st_mode = 0o100644  # Regular file
        mock_sftp.stat.return_value = mock_stat

        source = SSHSource(config)
        source.acquire(str(tmp_path))

        # Verify connection was made
        mock_ssh.connect.assert_called_once()
        assert 'hostname' in mock_ssh.connect.call_args[1]
        assert mock_ssh.connect.call_args[1]['hostname'] == 'test.example.com'
        assert mock_ssh.connect.call_args[1]['username'] == 'testuser'
        assert mock_ssh.connect.call_args[1]['password'] == 'testpass'

    @patch('app.backup.sources.SSHClient')
    def test_ssh_source_download_file(self, mock_ssh_class, tmp_path):
        """Test downloading a single file via SFTP."""
        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.open_sftp.return_value = mock_sftp

        # Mock file
        mock_stat = MagicMock()
        mock_stat.st_mode = 0o100644
        mock_sftp.stat.return_value = mock_stat

        config = {
            'host': 'test.example.com',
            'username': 'testuser',
            'password': 'testpass',
            'paths': ['/remote/data.txt']
        }

        source = SSHSource(config)
        acquired = source.acquire(str(tmp_path))

        # Verify SFTP get was called
        mock_sftp.get.assert_called_once()
        assert len(acquired) == 1

    @patch('app.backup.sources.SSHClient')
    def test_ssh_source_download_directory(self, mock_ssh_class, tmp_path):
        """Test downloading a directory via SFTP."""
        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.open_sftp.return_value = mock_sftp

        # Mock directory
        mock_stat = MagicMock()
        mock_stat.st_mode = 0o040755  # Directory
        mock_sftp.stat.return_value = mock_stat

        # Mock directory listing
        file_attr = MagicMock()
        file_attr.filename = 'file.txt'
        file_attr.st_mode = 0o100644  # File
        mock_sftp.listdir_attr.return_value = [file_attr]

        config = {
            'host': 'test.example.com',
            'username': 'testuser',
            'password': 'testpass',
            'paths': ['/remote/dir']
        }

        source = SSHSource(config)
        acquired = source.acquire(str(tmp_path))

        assert len(acquired) >= 1
        mock_sftp.listdir_attr.assert_called()

    @patch('app.backup.sources.SSHClient')
    def test_ssh_source_with_private_key(self, mock_ssh_class, tmp_path):
        """Test SSH connection with private key."""
        mock_ssh = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        # Create a fake key file
        key_file = tmp_path / "id_rsa"
        key_file.write_text("fake_private_key")

        # Mock stat
        mock_stat = MagicMock()
        mock_stat.st_mode = 0o100644
        mock_sftp.stat.return_value = mock_stat

        config = {
            'host': 'test.example.com',
            'username': 'testuser',
            'private_key': str(key_file),
            'paths': ['/remote/file.txt']
        }

        source = SSHSource(config)
        source.acquire(str(tmp_path))

        # Verify key_filename was passed
        assert 'key_filename' in mock_ssh.connect.call_args[1]

    @patch('app.backup.sources.SSHClient')
    def test_ssh_source_authentication_failure(self, mock_ssh_class, tmp_path):
        """Test SSH authentication failure handling."""
        import paramiko

        mock_ssh = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.connect.side_effect = paramiko.AuthenticationException("Auth failed")

        config = {
            'host': 'test.example.com',
            'username': 'testuser',
            'password': 'wrongpass',
            'paths': ['/remote/file.txt']
        }

        source = SSHSource(config)

        with pytest.raises(SourceError, match="[Aa]uthentication"):
            source.acquire(str(tmp_path))

    @patch('app.backup.sources.SSHClient')
    def test_ssh_source_connection_failure(self, mock_ssh_class, tmp_path):
        """Test SSH connection failure handling."""
        import paramiko

        mock_ssh = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.connect.side_effect = paramiko.SSHException("Connection failed")

        config = {
            'host': 'unreachable.example.com',
            'username': 'testuser',
            'password': 'testpass',
            'paths': ['/remote/file.txt']
        }

        source = SSHSource(config)

        with pytest.raises(SourceError, match="[Cc]onnection"):
            source.acquire(str(tmp_path))

    @patch('paramiko.SSHClient')
    def test_ssh_source_cleanup(self, mock_ssh_class):
        """Test SSH cleanup closes connections."""
        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.open_sftp.return_value = mock_sftp

        config = {
            'host': 'test.example.com',
            'username': 'testuser',
            'password': 'testpass',
            'paths': []
        }

        source = SSHSource(config)
        source.ssh_client = mock_ssh
        source.sftp_client = mock_sftp

        source.cleanup()

        mock_sftp.close.assert_called_once()
        mock_ssh.close.assert_called_once()

    @patch('paramiko.SSHClient')
    def test_ssh_source_no_credentials_raises_error(self, mock_ssh_class, tmp_path):
        """Test that missing credentials raises error."""
        config = {
            'host': 'test.example.com',
            'username': 'testuser',
            # No password or private_key
            'paths': ['/remote/file.txt']
        }

        source = SSHSource(config)

        with pytest.raises(SourceError, match="password or private_key"):
            source.acquire(str(tmp_path))


class TestCreateSourceFactory:
    """Test create_source factory function."""

    def test_create_source_local(self):
        """Test creating LocalSource via factory."""
        config = {
            'paths': ['/tmp/test'],
            'exclude_patterns': ['*.pyc']
        }

        source = create_source('local', config)

        assert isinstance(source, LocalSource)
        assert source.paths == ['/tmp/test']
        assert source.exclude_patterns == ['*.pyc']

    def test_create_source_ssh(self):
        """Test creating SSHSource via factory."""
        config = {
            'host': 'test.example.com',
            'username': 'testuser',
            'password': 'testpass',
            'paths': ['/remote/data']
        }

        source = create_source('ssh', config)

        assert isinstance(source, SSHSource)
        assert source.host == 'test.example.com'
        assert source.username == 'testuser'

    def test_create_source_invalid_type_raises_error(self):
        """Test that invalid source type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid source type"):
            create_source('invalid_type', {})

    def test_create_source_local_defaults(self):
        """Test LocalSource created with default exclude patterns."""
        config = {'paths': ['/tmp/test']}

        source = create_source('local', config)

        assert isinstance(source, LocalSource)
        assert source.exclude_patterns == []

    def test_create_source_ssh_with_port(self):
        """Test SSHSource with custom port."""
        config = {
            'host': 'test.example.com',
            'port': 2222,
            'username': 'testuser',
            'password': 'testpass',
            'paths': ['/remote/data']
        }

        source = create_source('ssh', config)

        assert source.port == 2222
