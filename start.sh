#!/bin/bash

VERSION="0.5.3"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}❌${NC} $1"; }

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║              PG-Limiter v$VERSION Starting...                   ║"
echo "╚═══════════════════════════════════════════════════════════════╝"

# Ensure data directories exist
echo "Creating data directories..."
mkdir -p /var/lib/pg-limiter/data || { log_error "Failed to create data directory"; exit 1; }
mkdir -p /var/lib/pg-limiter/logs || { log_error "Failed to create logs directory"; exit 1; }
log_info "Data directories ready"

# Create symlinks for data directory
if [ ! -L "/app/data" ] && [ ! -d "/app/data" ]; then
    ln -sf /var/lib/pg-limiter/data /app/data
fi

# Validate required environment variables
echo "Validating environment..."
MISSING_VARS=""
[ -z "$PANEL_DOMAIN" ] && MISSING_VARS="$MISSING_VARS PANEL_DOMAIN"
[ -z "$PANEL_PASSWORD" ] && MISSING_VARS="$MISSING_VARS PANEL_PASSWORD"
[ -z "$BOT_TOKEN" ] && MISSING_VARS="$MISSING_VARS BOT_TOKEN"
[ -z "$ADMIN_IDS" ] && MISSING_VARS="$MISSING_VARS ADMIN_IDS"

if [ -n "$MISSING_VARS" ]; then
    log_error "Missing required environment variables:$MISSING_VARS"
    exit 1
fi
log_info "Environment validated"
echo "    Panel: $PANEL_DOMAIN"
echo "    Bot Token: ${BOT_TOKEN:0:10}..."
echo "    Admin IDs: $ADMIN_IDS"

# Initialize database
echo "Initializing database..."
python -c "
import asyncio
from db import init_db
asyncio.run(init_db())
print('DB_INIT_DONE')
" 2>&1
DB_EXIT=$?
if [ $DB_EXIT -eq 0 ]; then
    log_info "Database initialized"
else
    log_error "Database initialization failed (exit code: $DB_EXIT)"
    exit 1
fi

# Run database migrations
echo "Running database migrations..."
MIGRATION_OUTPUT=$(python -m alembic upgrade head 2>&1)
MIGRATION_EXIT=$?
if [ $MIGRATION_EXIT -eq 0 ]; then
    log_info "Migrations applied"
else
    log_warn "Migrations skipped: $MIGRATION_OUTPUT"
fi

# Migrate from JSON to database if old JSON files exist
if [ -f "/app/.disable_users.json" ] || [ -f "/app/.violation_history.json" ]; then
    echo "Migrating data from JSON files to database..."
    if python -m db.migrate_from_json 2>&1; then
        log_info "JSON migration complete"
    else
        log_warn "JSON migration skipped"
    fi
fi

# Remove old config.json if exists (no longer needed)
if [ -f "/var/lib/pg-limiter/config.json" ]; then
    echo "Removing deprecated config.json..."
    rm -f /var/lib/pg-limiter/config.json
fi
if [ -L "/app/config.json" ]; then
    rm -f /app/config.json
fi

# Verify Python can import all required modules
echo "Verifying modules..."
python -c "
print('  Importing telegram_bot.main...')
from telegram_bot.main import application
print('  Importing utils.read_config...')
from utils.read_config import read_config
print('  Importing db...')
from db import get_db
print('  All modules loaded successfully')
" 2>&1
MODULE_EXIT=$?
if [ $MODULE_EXIT -eq 0 ]; then
    log_info "All modules verified"
else
    log_error "Module verification failed (exit code: $MODULE_EXIT)"
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
log_info "PG-Limiter v$VERSION initialized successfully"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Starting limiter..."
exec python -u limiter.py
