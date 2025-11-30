#!/bin/bash
set -e

echo "Starting Mackuper..."

# Ensure data directories exist
mkdir -p /data/temp /data/local_backups

# Run database migrations (if needed in the future)
# python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"

# Start the application with Gunicorn
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    "app:create_app()"
