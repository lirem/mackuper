#!/bin/bash
set -e

echo "Starting Mackuper..."

# Ensure data directories exist (create with proper permissions)
mkdir -p /data/temp /data/local_backups 2>/dev/null || true

# Generate and persist SECRET_KEY if it doesn't exist
if [ ! -f /data/.secret_key ]; then
    echo "Generating persistent SECRET_KEY..."
    python3 -c "import secrets; print(secrets.token_hex(32))" > /data/.secret_key 2>/dev/null || {
        echo "Warning: Cannot write to /data/.secret_key - SECRET_KEY will not persist across restarts"
        export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    }
    if [ -f /data/.secret_key ]; then
        chmod 600 /data/.secret_key
        echo "SECRET_KEY generated and saved to /data/.secret_key"
        export SECRET_KEY=$(cat /data/.secret_key)
    fi
else
    # Export SECRET_KEY from persisted file
    export SECRET_KEY=$(cat /data/.secret_key)
    echo "Using existing SECRET_KEY from /data/.secret_key"
fi

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
