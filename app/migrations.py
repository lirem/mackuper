"""
Database migrations for Mackuper.

Simple migration system to handle schema changes without requiring Alembic.
"""

import logging
from sqlalchemy import text, inspect
from app import db

logger = logging.getLogger(__name__)


def init_database_schema(app):
    """
    Initialize database schema and run migrations.

    This function creates tables if they don't exist and runs any necessary migrations.
    It's designed to be called from multiple Gunicorn workers without conflicts.
    """
    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()

        # If no tables exist, create them all
        if not existing_tables:
            logger.info("No tables found - creating initial database schema")
            try:
                db.create_all()
                logger.info("Database schema created successfully")
            except Exception as e:
                logger.error(f"Failed to create database schema: {e}")
                # If another worker beat us to it, that's okay
                pass
        else:
            # Tables exist - run migrations
            run_migrations(app, inspector)


def run_migrations(app, inspector=None):
    """
    Run all necessary database migrations.

    This function checks the database schema and applies any missing changes.
    """
    if inspector is None:
        inspector = inspect(db.engine)

    # Migration 1: Add password_encrypted and updated_at columns to encryption_key table
    if 'encryption_key' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('encryption_key')]

        # Add password_encrypted column if it doesn't exist
        if 'password_encrypted' not in columns:
            logger.info("Running migration: Adding password_encrypted column to encryption_key table")
            try:
                db.session.execute(text(
                    "ALTER TABLE encryption_key ADD COLUMN password_encrypted TEXT"
                ))
                db.session.commit()
                logger.info("Successfully added password_encrypted column")
            except Exception as e:
                logger.error(f"Failed to add password_encrypted column: {e}")
                db.session.rollback()

        # Add updated_at column if it doesn't exist
        if 'updated_at' not in columns:
            logger.info("Running migration: Adding updated_at column to encryption_key table")
            try:
                db.session.execute(text(
                    "ALTER TABLE encryption_key ADD COLUMN updated_at TIMESTAMP"
                ))
                db.session.commit()
                logger.info("Successfully added updated_at column")
            except Exception as e:
                logger.error(f"Failed to add updated_at column: {e}")
                db.session.rollback()

    # Migration 2: Add ssh_password_encrypted column to backup_jobs table
    if 'backup_jobs' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('backup_jobs')]

        if 'ssh_password_encrypted' not in columns:
            logger.info("Running migration: Adding ssh_password_encrypted column to backup_jobs table")
            try:
                # Step 1: Add the new column
                db.session.execute(text(
                    "ALTER TABLE backup_jobs ADD COLUMN ssh_password_encrypted TEXT"
                ))
                db.session.commit()
                logger.info("Successfully added ssh_password_encrypted column")

                # Step 2: Migrate existing SSH passwords
                _migrate_ssh_passwords()

            except Exception as e:
                logger.error(f"Failed to add ssh_password_encrypted column: {e}")
                db.session.rollback()

    # Migration 3: Add cancellation_requested column to backup_history table
    if 'backup_history' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('backup_history')]

        if 'cancellation_requested' not in columns:
            logger.info("Running migration: Adding cancellation_requested column to backup_history table")
            try:
                db.session.execute(text(
                    "ALTER TABLE backup_history ADD COLUMN cancellation_requested BOOLEAN NOT NULL DEFAULT 0"
                ))
                db.session.commit()
                logger.info("Successfully added cancellation_requested column")
            except Exception as e:
                logger.error(f"Failed to add cancellation_requested column: {e}")
                db.session.rollback()


def _migrate_ssh_passwords():
    """
    Migrate existing plaintext SSH passwords to encrypted storage.

    This function:
    1. Finds all SSH backup jobs
    2. Extracts passwords from source_config JSON
    3. Encrypts passwords if crypto_manager is initialized
    4. Stores in ssh_password_encrypted column
    5. Removes password from source_config JSON
    """
    from app.models import BackupJob
    from app.utils.crypto import crypto_manager
    import json

    logger.info("Migrating existing SSH passwords to encrypted storage")

    # Get all SSH backup jobs
    ssh_jobs = BackupJob.query.filter_by(source_type='ssh').all()

    if not ssh_jobs:
        logger.info("No SSH backup jobs found - skipping password migration")
        return

    logger.info(f"Found {len(ssh_jobs)} SSH backup jobs to migrate")

    migrated_count = 0
    skipped_count = 0

    for job in ssh_jobs:
        try:
            # Parse source_config
            config = json.loads(job.source_config)

            # Check if password exists in config
            password = config.get('password')

            if not password:
                # No password (using private key only)
                logger.info(f"Job '{job.name}' has no password - skipping")
                skipped_count += 1
                continue

            # Check if crypto_manager is initialized
            if not crypto_manager.is_initialized:
                logger.warning(
                    f"Crypto manager not initialized - cannot migrate password for job '{job.name}'. "
                    "Password will be migrated on next user login."
                )
                skipped_count += 1
                continue

            # Encrypt the password
            encrypted_password = crypto_manager.encrypt(password)

            # Store encrypted password
            job.ssh_password_encrypted = encrypted_password

            # Remove password from source_config
            del config['password']
            job.source_config = json.dumps(config)

            logger.info(f"Migrated password for job '{job.name}'")
            migrated_count += 1

        except Exception as e:
            logger.error(f"Failed to migrate password for job '{job.name}': {e}")
            skipped_count += 1

    # Commit all changes
    try:
        db.session.commit()
        logger.info(
            f"Password migration complete: {migrated_count} migrated, {skipped_count} skipped"
        )
    except Exception as e:
        logger.error(f"Failed to commit password migration: {e}")
        db.session.rollback()
