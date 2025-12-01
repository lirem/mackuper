# Contributing to Mackuper

Thank you for your interest in contributing to Mackuper! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Release Process](#release-process)

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help newcomers get started
- Report issues professionally

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- Docker and Docker Compose (for testing deployment)
- AWS S3 account (for integration testing)

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/mackuper.git
   cd mackuper
   ```

3. Add upstream remote:
   ```bash
   git remote add upstream https://github.com/ORIGINAL_OWNER/mackuper.git
   ```

## Development Setup

### 1. Create Virtual Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate it
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

### 2. Install Dependencies

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-cov black flake8 mypy
```

### 3. Set Up Development Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with development settings
# Set FLASK_ENV=development for debug mode
```

### 4. Initialize Database

```bash
# Run development server (will auto-create database)
python run.py
```

The application will be available at http://localhost:5000

### 5. Complete Setup Wizard

1. Open http://localhost:5000/setup
2. Create admin account
3. Configure AWS S3 (or skip for frontend-only development)

## Project Structure

```
mackuper/
├── app/                      # Main application package
│   ├── __init__.py          # Flask app factory, CSRF config, logging
│   ├── models.py            # SQLAlchemy database models
│   ├── auth.py              # Password hashing, validation, UserModel
│   ├── config.py            # Configuration classes (Dev/Prod)
│   ├── scheduler.py         # APScheduler setup and job management
│   ├── backup/              # Backup system modules
│   │   ├── sources.py       # LocalSource and SSHSource handlers
│   │   ├── compression.py   # Archive creation (zip, tar.*)
│   │   ├── storage.py       # S3Storage and LocalStorage
│   │   ├── executor.py      # BackupExecutor orchestration
│   │   └── retention.py     # RetentionManager cleanup
│   ├── routes/              # API route handlers
│   │   ├── auth_routes.py   # Login, logout, setup wizard
│   │   ├── dashboard_routes.py  # Dashboard stats
│   │   ├── jobs_routes.py   # Job CRUD + manual execution
│   │   ├── settings_routes.py   # AWS settings, password
│   │   └── history_routes.py    # Backup history and logs
│   ├── utils/               # Utility modules
│   │   └── crypto.py        # Fernet encryption/decryption
│   └── static/              # Frontend assets
│       ├── css/styles.css   # Custom CSS
│       └── js/              # Frontend JavaScript
│           ├── app.js       # Alpine.js main app
│           ├── dashboard.js # Dashboard component
│           ├── jobs.js      # Jobs management
│           ├── settings.js  # Settings page
│           └── history.js   # History viewer
├── templates/               # Jinja2 templates
│   ├── base.html           # Base template
│   ├── login.html          # Login page
│   ├── setup.html          # Setup wizard
│   └── app.html            # Main SPA shell
├── docker/                  # Docker deployment files
│   ├── Dockerfile          # Multi-stage Docker build
│   └── entrypoint.sh       # Container startup script
├── data/                    # Data directory (gitignored)
│   ├── mackuper.db         # SQLite database
│   ├── logs/               # Application logs
│   ├── temp/               # Temporary files
│   └── local_backups/      # Local backup storage
├── tests/                   # Test suite (to be implemented)
├── .claude/                 # Development documentation
│   ├── CLAUDE.md           # Working rules and guidelines
│   └── PROJECT_CONTEXT.md  # Codebase reference (keep updated!)
├── requirements.txt         # Python dependencies
├── docker-compose.yml      # Docker Compose configuration
├── run.py                  # Development server entry point
├── .env.example            # Environment variables template
├── .gitignore              # Git ignore patterns
├── .dockerignore           # Docker ignore patterns
├── README.md               # User documentation
├── CONTRIBUTING.md         # This file
└── LICENSE                 # Apache License 2.0
```

### Maintaining PROJECT_CONTEXT.md

The `.claude/PROJECT_CONTEXT.md` file is a quick reference document for the codebase structure. **When making significant changes, please update this file to keep it current.**

Update `PROJECT_CONTEXT.md` when you modify:
- **API routes** (`/app/routes/*.py`) → Update "API Endpoint Mapping" section
- **Database models** (`/app/models.py`) → Update "Database Schema" section
- **Backup modules** (`/app/backup/*.py`) → Update "Module Responsibility Matrix" and/or "Backup Workflow"
- **New modules** → Update "Module Responsibility Matrix"
- **Configuration** (`config.py`) → Update "Key Dependencies" section
- **Testing patterns** → Update "Testing Patterns" section
- **Dependencies** (`requirements.txt`) → Update "Key Dependencies" section

Also update the "Last Updated" timestamp at the top of the file.

## Coding Standards

### Python Style Guide

We follow PEP 8 with some customizations:

- **Line Length**: 100 characters (not 79)
- **Quotes**: Single quotes for strings (except docstrings)
- **Imports**: Organized in three groups (standard, third-party, local)
- **Docstrings**: Google style for functions and classes

### Code Formatting

```bash
# Format code with Black
black app/ tests/

# Check with flake8
flake8 app/ tests/ --max-line-length=100

# Type checking with mypy (optional)
mypy app/
```

### Naming Conventions

- **Functions/Variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private methods**: `_leading_underscore`
- **Database tables**: `snake_case` (plural)

### Example Code Style

```python
"""Module docstring explaining what this module does."""

import os
import logging
from typing import Optional, List

from flask import Blueprint, jsonify
from app import db
from app.models import BackupJob

logger = logging.getLogger(__name__)

# Constants
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30


class BackupExecutor:
    """
    Orchestrates backup job execution.

    Handles the complete backup workflow from source acquisition
    to S3 upload and cleanup.
    """

    def __init__(self, job_id: int):
        """
        Initialize backup executor.

        Args:
            job_id: ID of the backup job to execute
        """
        self.job_id = job_id
        self.job = self._load_job()

    def execute(self) -> bool:
        """
        Execute the backup job.

        Returns:
            True if successful, False otherwise

        Raises:
            StorageError: If S3 upload fails
        """
        try:
            logger.info(f"Starting backup for job {self.job_id}")
            # Implementation here
            return True
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}")
            return False
```

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_backup_executor.py

# Run specific test
pytest tests/test_backup_executor.py::test_local_source
```

### Writing Tests

Create test files in `tests/` directory:

```python
"""Tests for backup executor functionality."""

import pytest
from app.backup.executor import BackupExecutor
from app.models import BackupJob


def test_backup_executor_init():
    """Test BackupExecutor initialization."""
    job = BackupJob(name='test', source_type='local')
    executor = BackupExecutor(job.id)
    assert executor.job_id == job.id


def test_local_source_backup(tmp_path):
    """Test backing up local directory."""
    # Create test directory
    test_dir = tmp_path / "source"
    test_dir.mkdir()
    (test_dir / "file.txt").write_text("test content")

    # Execute backup
    job = BackupJob(
        name='test',
        source_type='local',
        source_config={'path': str(test_dir)}
    )
    executor = BackupExecutor(job.id)
    result = executor.execute()

    assert result is True
```

### Test Coverage Goals

- **Unit Tests**: 80%+ coverage for core modules
- **Integration Tests**: Critical workflows (backup execution, S3 upload)
- **API Tests**: All route handlers

## Submitting Changes

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation changes
- `refactor/description` - Code refactoring

### Commit Messages

Follow conventional commits:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(backup): add support for tar.xz compression

Implements LZMA compression for smaller backup sizes.
Uses Python's lzma module for creating tar.xz archives.

Closes #42

---

fix(scheduler): prevent duplicate job executions

Jobs were running multiple times due to scheduler misfire handling.
Changed coalesce setting to prevent duplicate runs.

Fixes #56

---

docs(readme): add troubleshooting section

Adds common issues and solutions for setup and backup failures.
```

### Pull Request Process

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes** following coding standards

3. **Write tests** for new functionality

4. **Update documentation** if needed

5. **Run tests** and ensure they pass:
   ```bash
   pytest tests/
   ```

6. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat(component): description"
   ```

7. **Push to your fork**:
   ```bash
   git push origin feature/my-feature
   ```

8. **Create Pull Request** on GitHub:
   - Use a descriptive title
   - Reference any related issues
   - Describe what changes were made and why
   - Include screenshots for UI changes

9. **Address review feedback** if requested

10. **Squash commits** if asked before merging

### PR Checklist

- [ ] Tests pass (`pytest tests/`)
- [ ] Code follows style guide (`black`, `flake8`)
- [ ] Documentation updated
- [ ] Commit messages follow convention
- [ ] No merge conflicts
- [ ] Changes are minimal and focused
- [ ] PR description is clear and complete

## Development Workflow

### Adding a New Feature

1. **Plan the feature**:
   - Consider impact on existing code
   - Check if configuration changes needed
   - Identify affected components

2. **Update database models** (if needed):
   - Add fields to `app/models.py`
   - Database migrations not required (SQLite recreates on schema change)

3. **Implement backend**:
   - Add route handlers in appropriate `routes/` file
   - Add business logic in `backup/` or `utils/`
   - Use logging for debugging

4. **Implement frontend** (if needed):
   - Update Alpine.js components in `static/js/`
   - Add styles in `static/css/styles.css`
   - Update templates if new pages needed

5. **Test thoroughly**:
   - Unit tests for logic
   - Manual testing through UI
   - Test with Docker build

6. **Document**:
   - Update README.md if user-facing
   - Add docstrings to functions
   - Update CONTRIBUTING.md if developer-facing

### Debugging Tips

**Enable debug mode:**
```bash
# In .env
FLASK_ENV=development

# In run.py, debug mode is automatically enabled
```

**Check logs:**
```bash
# Watch log file in real-time
tail -f data/logs/mackuper.log

# Search logs
grep "error" data/logs/mackuper.log
```

**Database inspection:**
```bash
# Open SQLite database
sqlite3 data/mackuper.db

# List tables
.tables

# Query jobs
SELECT * FROM backup_jobs;

# Exit
.exit
```

**Docker debugging:**
```bash
# View container logs
docker-compose logs -f mackuper

# Access container shell
docker-compose exec mackuper /bin/bash

# Restart container
docker-compose restart mackuper
```

## Release Process

### Version Numbering

We use Semantic Versioning (SemVer):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

### Creating a Release

1. **Update version** in `app/routes/settings_routes.py` `get_about()` function

2. **Update CHANGELOG.md** with release notes

3. **Create git tag**:
   ```bash
   git tag -a v1.0.0 -m "Release version 1.0.0"
   git push origin v1.0.0
   ```

4. **Build and test Docker image**:
   ```bash
   docker build -f docker/Dockerfile -t mackuper:1.0.0 .
   docker-compose up -d
   # Test thoroughly
   ```

5. **Create GitHub release** with tag and changelog

## Common Tasks

### Adding a New Compression Format

1. Add format to `app/backup/compression.py`
2. Update `COMPRESSION_FORMATS` constant
3. Implement `_create_<format>_archive()` method
4. Update frontend dropdown in `jobs.js`
5. Add tests

### Adding a New Source Type

1. Add source class to `app/backup/sources.py`
2. Inherit from base interface
3. Implement `acquire()` method
4. Update `BackupExecutor` to handle new type
5. Update frontend form in `jobs.js`
6. Add tests

### Adding API Endpoint

1. Add route to appropriate blueprint in `app/routes/`
2. Add `@login_required` decorator
3. Implement handler with error handling
4. Add logging
5. Update frontend to call new endpoint
6. Add tests

## Questions?

- **General Questions**: Open a discussion on GitHub
- **Bug Reports**: Create an issue with reproduction steps
- **Feature Requests**: Open an issue with use case description
- **Security Issues**: Email maintainers directly (see README)

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

Thank you for contributing to Mackuper! 🎉
