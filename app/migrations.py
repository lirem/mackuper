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
