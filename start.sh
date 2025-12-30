#!/bin/bash
set -e

VERSION="0.4.2"

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║              PG-Limiter v$VERSION Starting...                   ║"
echo "╚═══════════════════════════════════════════════════════════════╝"

# Ensure data directories exist
mkdir -p /var/lib/pg-limiter/data
mkdir -p /var/lib/pg-limiter/logs

# Create symlinks for data directory
if [ ! -L "/app/data" ] && [ ! -d "/app/data" ]; then
    ln -sf /var/lib/pg-limiter/data /app/data
fi

# Validate required environment variables
echo "Validating environment..."
if [ -z "$PANEL_DOMAIN" ]; then
    echo "❌ Error: PANEL_DOMAIN is not set"
    exit 1
fi
if [ -z "$PANEL_PASSWORD" ]; then
    echo "❌ Error: PANEL_PASSWORD is not set"
    exit 1
fi
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ Error: BOT_TOKEN is not set"
    exit 1
fi
if [ -z "$ADMIN_IDS" ]; then
    echo "❌ Error: ADMIN_IDS is not set"
    exit 1
fi
echo "✓ Environment validated"

# Initialize database
echo "Initializing database..."
python -c "
import asyncio
from db import init_db
asyncio.run(init_db())
print('✓ Database initialized')
"

# Run database migrations
echo "Running database migrations..."
python -m alembic upgrade head 2>&1 || echo "⚠ Migrations not applied (may already be up to date)"

# Migrate from JSON to database if old JSON files exist
if [ -f "/app/.disable_users.json" ] || [ -f "/app/.violation_history.json" ]; then
    echo "Migrating data from JSON files to database..."
    python -m db.migrate_from_json || true
fi

# Remove old config.json if exists (no longer needed)
if [ -f "/var/lib/pg-limiter/config.json" ]; then
    echo "Removing deprecated config.json..."
    rm -f /var/lib/pg-limiter/config.json
fi
if [ -L "/app/config.json" ]; then
    rm -f /app/config.json
fi

echo "✓ PG-Limiter initialized"
echo "Starting limiter..."
echo "Bot Token: ${BOT_TOKEN:0:10}..."
echo "Admin IDs: $ADMIN_IDS"
exec python -u limiter.py
