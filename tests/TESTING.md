# Mackuper Testing Guide

This document provides comprehensive information about testing the Mackuper backup application.

## Table of Contents
1. [Running Tests](#running-tests)
2. [Test Structure](#test-structure)
3. [Understanding Fixtures](#understanding-fixtures)
4. [Mocking Strategies](#mocking-strategies)
5. [Writing New Tests](#writing-new-tests)
6. [Debugging Test Failures](#debugging-test-failures)
7. [Coverage Reporting](#coverage-reporting)

## Running Tests

### Prerequisites
Install test dependencies:
```bash
pip install -r requirements.txt
```

### Basic Test Commands

**Run all tests:**
```bash
pytest
```

**Run with verbose output:**
```bash
pytest -v
```

**Run specific test file:**
```bash
pytest tests/unit/test_auth.py
pytest tests/integration/test_routes_auth.py -v
```

**Run specific test function:**
```bash
pytest tests/unit/test_crypto.py::test_crypto_manager_encrypt_decrypt
```

**Run only unit tests:**
```bash
pytest tests/unit/
```

**Run only integration tests:**
```bash
pytest tests/integration/
```

**Run tests by marker:**
```bash
pytest -m unit
pytest -m integration
pytest -m "not slow"
```

### Coverage Commands

**Run tests with coverage:**
```bash
pytest --cov=app
```

**Generate HTML coverage report:**
```bash
pytest --cov=app --cov-report=html
```
Then open `htmlcov/index.html` in your browser.

**Show missing lines:**
```bash
pytest --cov=app --cov-report=term-missing
```

**Coverage for specific module:**
```bash
pytest --cov=app.auth tests/unit/test_auth.py
```

## Test Structure

```
tests/
├── __init__.py                # Empty init file
├── conftest.py                # Shared fixtures (DB, app, mocks)
├── pytest.ini                 # Pytest configuration
├── TESTING.md                 # This file
├── unit/                      # Unit tests (isolated, mocked)
│   ├── test_auth.py           # Authentication functions
│   ├── test_crypto.py         # Encryption/decryption
│   ├── test_compression.py    # Archive creation
│   ├── test_sources.py        # File acquisition (local/SSH)
│   ├── test_storage.py        # S3 and local storage
│   ├── test_retention.py      # Retention policy cleanup
│   ├── test_scheduler.py      # Job scheduling
│   ├── test_executor.py       # Backup workflow
│   └── test_models.py         # Database models
├── integration/               # Integration tests (real DB, mocked services)
│   ├── test_routes_auth.py    # Auth routes
│   ├── test_routes_jobs.py    # Job management routes
│   ├── test_routes_settings.py # Settings routes
│   ├── test_routes_dashboard.py # Dashboard routes
│   └── test_routes_history.py # History routes
└── fixtures/                  # Test data and fixtures
    └── test_data/
        └── sample.txt
```

## Understanding Fixtures

Fixtures are reusable test components defined in `conftest.py`. They provide setup and teardown logic.

### Database Fixtures

**`app`** - Flask application with test configuration
- Uses in-memory SQLite database
- Disables CSRF protection
- Creates temporary directories

**`db`** - Database instance with tables created
- Fresh database for each test
- Automatic cleanup after test

**`client`** - Flask test client for HTTP requests
```python
def test_example(client):
    response = client.get('/health')
    assert response.status_code == 200
```

### User & Auth Fixtures

**`admin_user`** - Pre-created admin user
- Username: `admin`
- Password: `Admin123`

**`crypto_manager_initialized`** - Initialized CryptoManager
- Password: `test_password_123`
- Returns tuple: `(crypto_manager, salt)`

**`aws_settings`** - AWS settings with encrypted credentials

### Backup Job Fixtures

**`local_backup_job`** - Backup job with local source
**`ssh_backup_job`** - Backup job with SSH source
**`backup_history`** - Sample backup history record

### Mock Fixtures

**`mock_s3`** - Moto mock for AWS S3
```python
def test_s3_upload(mock_s3):
    # S3 operations work without real AWS
    pass
```

**`mock_ssh_client`** - Mock paramiko SSHClient
**`mock_scheduler`** - Mock APScheduler

### File Fixtures

**`temp_files`** - Temporary test files in tmp_path
**`sample_archive`** - Pre-created test archive

## Mocking Strategies

### Mocking AWS S3 with Moto

```python
from moto import mock_s3
import boto3

@mock_s3
def test_s3_operation():
    # Create mock S3
    s3 = boto3.resource('s3', region_name='us-east-1')
    s3.create_bucket(Bucket='test-bucket')

    # Your S3 code here
    # It will hit the mock instead of real AWS
```

Or use the fixture:
```python
def test_s3_with_fixture(mock_s3):
    # mock_s3 fixture already has 'test-bucket' created
    # Just use boto3 normally
    pass
```

### Mocking SSH/SFTP with Paramiko

```python
from unittest.mock import patch, MagicMock

@patch('paramiko.SSHClient')
def test_ssh_source(mock_ssh):
    # Setup mock
    mock_sftp = MagicMock()
    mock_ssh.return_value.open_sftp.return_value = mock_sftp

    # Mock file operations
    mock_sftp.stat.return_value.st_mode = 0o100644  # Regular file

    # Your SSH code here
```

### Mocking Time with Freezegun

```python
from freezegun import freeze_time
from datetime import datetime

@freeze_time("2024-01-15 12:00:00")
def test_retention():
    # datetime.now() always returns 2024-01-15 12:00:00
    now = datetime.utcnow()
    assert now.day == 15
```

### Mocking APScheduler

```python
def test_scheduler(mock_scheduler):
    # mock_scheduler is already set up
    # Access mock methods
    mock_scheduler.get_jobs.return_value = []
```

## Writing New Tests

### Test Naming Convention
- File: `test_<module>.py`
- Class: `Test<Feature>` (optional)
- Function: `test_<function>_<scenario>_<expected_result>`

Examples:
```python
def test_hash_password_returns_different_from_plain()
def test_encrypt_decrypt_cycle_preserves_data()
def test_create_archive_with_invalid_format_raises_error()
```

### Test Structure (AAA Pattern)

```python
def test_example():
    # Arrange - Set up test data
    password = "TestPass123"

    # Act - Execute the code being tested
    hashed = hash_password(password)

    # Assert - Verify the result
    assert hashed != password
    assert len(hashed) > 20
```

### Parameterized Tests

Test multiple scenarios with one test function:

```python
import pytest

@pytest.mark.parametrize("password,is_valid,expected_error", [
    ("short", False, "8 characters"),
    ("nouppercase1", False, "uppercase"),
    ("NOLOWERCASE1", False, "lowercase"),
    ("NoDigits", False, "digit"),
    ("ValidPass123", True, ""),
])
def test_password_validation(password, is_valid, expected_error):
    result, msg = validate_password_strength(password)
    assert result == is_valid
    if expected_error:
        assert expected_error in msg
```

### Testing Exceptions

```python
import pytest

def test_crypto_not_initialized_raises_error():
    cm = CryptoManager()
    with pytest.raises(RuntimeError, match="not initialized"):
        cm.encrypt("test")
```

### Integration Test Example

```python
def test_login_flow(client, admin_user):
    # Arrange
    login_data = {
        'username': 'admin',
        'password': 'Admin123'
    }

    # Act
    response = client.post('/login', data=login_data, follow_redirects=True)

    # Assert
    assert response.status_code == 200
    assert b'Login successful' in response.data
```

## Debugging Test Failures

### Run with Print Statements
```bash
pytest -s  # Don't capture stdout
```

### Run with Debugger
```bash
pytest --pdb  # Drop into debugger on failure
```

### Show Local Variables on Failure
```bash
pytest -l  # Show locals in tracebacks
```

### Run Last Failed Tests
```bash
pytest --lf  # Only re-run failures
```

### Exit on First Failure
```bash
pytest -x  # Stop after first failure
```

### Verbose Output
```bash
pytest -vv  # Extra verbose
```

### See Print Output for Passing Tests
```bash
pytest -v -s
```

## Coverage Reporting

### Understanding Coverage Reports

**Line Coverage**: Percentage of code lines executed during tests
**Branch Coverage**: Percentage of conditional branches tested

### Coverage Goals
- Overall Project: 80-95%
- Critical Security (auth, crypto): 95%+
- Core Backup Logic: 90%+
- Routes: 80%+

### Interpreting HTML Report

After running `pytest --cov=app --cov-report=html`, open `htmlcov/index.html`.

**Green lines**: Executed during tests
**Red lines**: Never executed
**Yellow lines**: Partially executed (branches)

### Excluding Code from Coverage

Use comments to exclude code:
```python
def debug_only_function():  # pragma: no cover
    # This won't count against coverage
    pass
```

### Finding Untested Code

```bash
pytest --cov=app --cov-report=term-missing
```

Look for modules with low coverage and missing line numbers.

### Coverage Best Practices

1. **Don't obsess over 100%**: 80-95% is excellent
2. **Focus on critical paths**: Auth, crypto, data handling
3. **Test error paths**: Not just happy paths
4. **Ignore boilerplate**: App initialization, simple getters
5. **Use markers**: Separate fast/slow tests

## Common Issues

### Import Errors
**Problem**: `ModuleNotFoundError: No module named 'app'`
**Solution**: Run pytest from project root, not from tests/

### Database Errors
**Problem**: `Table already exists`
**Solution**: Ensure using function-scoped fixtures, not session-scoped

### Scheduler Tests Hanging
**Problem**: Tests with APScheduler don't finish
**Solution**: Use `mock_scheduler` fixture, don't start real scheduler

### S3 Tests Failing
**Problem**: `boto3.exceptions.NoCredentialsError`
**Solution**: Use `@mock_s3` decorator or `mock_s3` fixture

### Temp Files Not Cleaned Up
**Problem**: /tmp/ filling up with test files
**Solution**: Use pytest's `tmp_path` fixture, not manual temp files

## Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Moto Documentation](https://docs.getmoto.org/)
- [Flask Testing](https://flask.palletsprojects.com/en/3.0.x/testing/)
- [Freezegun Documentation](https://github.com/spulec/freezegun)

## Quick Reference

```bash
# Most common commands
pytest                                    # Run all tests
pytest -v                                # Verbose
pytest --cov=app --cov-report=html       # Coverage report
pytest tests/unit/                       # Only unit tests
pytest -k "test_password"                # Run tests matching name
pytest --lf                              # Re-run last failures
pytest -x                                # Stop on first failure
pytest -s                                # Show print statements
```
