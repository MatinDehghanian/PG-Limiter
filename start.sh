#!/bin/bash

VERSION="0.5.3"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}❌${NC} $1"; }
log_debug() { echo -e "${CYAN}→${NC} $1"; }
log_step() { echo -e "${BLUE}[$1/${TOTAL_STEPS}]${NC} $2"; }

TOTAL_STEPS=8

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║              PG-Limiter v$VERSION Starting...                   ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Create data directories
# ═══════════════════════════════════════════════════════════════════════════════
log_step 1 "Creating data directories..."
mkdir -p /var/lib/pg-limiter/data || { log_error "Failed to create data directory"; exit 1; }
mkdir -p /var/lib/pg-limiter/logs || { log_error "Failed to create logs directory"; exit 1; }

# Create symlinks for data directory
if [ ! -L "/app/data" ] && [ ! -d "/app/data" ]; then
    ln -sf /var/lib/pg-limiter/data /app/data
fi
log_info "Data directories ready"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Validate environment variables
# ═══════════════════════════════════════════════════════════════════════════════
log_step 2 "Validating environment variables..."
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
log_debug "Panel: $PANEL_DOMAIN"
log_debug "Bot Token: ${BOT_TOKEN:0:15}..."
log_debug "Admin IDs: $ADMIN_IDS"
log_debug "Redis URL: ${REDIS_URL:-not configured (using in-memory cache)}"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Initialize database
# ═══════════════════════════════════════════════════════════════════════════════
log_step 3 "Initializing database..."
DB_OUTPUT=$(timeout 30 python -c "
import asyncio
import sys
try:
    from db import init_db
    asyncio.run(init_db())
    print('SUCCESS')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1)
DB_EXIT=$?

if [ $DB_EXIT -eq 124 ]; then
    log_error "Database initialization timed out (30s)"
    exit 1
elif [ $DB_EXIT -ne 0 ]; then
    log_error "Database initialization failed: $DB_OUTPUT"
    exit 1
fi
log_info "Database initialized"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Run database migrations
# ═══════════════════════════════════════════════════════════════════════════════
log_step 4 "Running database migrations..."
MIGRATION_OUTPUT=$(timeout 30 python -m alembic upgrade head 2>&1)
MIGRATION_EXIT=$?

if [ $MIGRATION_EXIT -eq 0 ]; then
    log_info "Migrations applied successfully"
elif [ $MIGRATION_EXIT -eq 124 ]; then
    log_warn "Migration timed out, continuing..."
else
    log_warn "Migrations skipped (may already be applied)"
    log_debug "Details: ${MIGRATION_OUTPUT:0:100}..."
fi

# Migrate from JSON to database if old JSON files exist
if [ -f "/app/.disable_users.json" ] || [ -f "/app/.violation_history.json" ]; then
    log_debug "Migrating data from JSON files to database..."
    timeout 30 python -m db.migrate_from_json 2>&1 && log_info "JSON migration complete" || log_warn "JSON migration skipped"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: Check Redis connectivity (optional)
# ═══════════════════════════════════════════════════════════════════════════════
log_step 5 "Checking Redis connectivity..."
REDIS_OUTPUT=$(timeout 10 python -c "
import asyncio
import sys
import os

async def check_redis():
    redis_url = os.environ.get('REDIS_URL', '')
    if not redis_url:
        print('SKIPPED: No REDIS_URL configured')
        return
    
    try:
        from utils.redis_cache import get_cache
        cache = await get_cache()
        if cache.is_connected():
            print('CONNECTED')
        else:
            print('FALLBACK: Using in-memory cache')
    except Exception as e:
        print(f'FALLBACK: {e}')

asyncio.run(check_redis())
" 2>&1)
REDIS_EXIT=$?

if echo "$REDIS_OUTPUT" | grep -q "CONNECTED"; then
    log_info "Redis connected"
elif echo "$REDIS_OUTPUT" | grep -q "SKIPPED"; then
    log_debug "Redis not configured, using in-memory cache"
else
    log_warn "Redis not available, using in-memory cache fallback"
    log_debug "$REDIS_OUTPUT"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: Verify Telegram Bot Token
# ═══════════════════════════════════════════════════════════════════════════════
log_step 6 "Verifying Telegram bot token..."
BOT_OUTPUT=$(timeout 15 python -c "
import asyncio
import os
import sys

async def check_bot():
    try:
        from telegram import Bot
        token = os.environ.get('BOT_TOKEN', '')
        if not token:
            print('ERROR: BOT_TOKEN not set')
            sys.exit(1)
        
        bot = Bot(token=token)
        me = await bot.get_me()
        print(f'CONNECTED: @{me.username} (ID: {me.id})')
    except Exception as e:
        print(f'ERROR: {e}')
        sys.exit(1)

asyncio.run(check_bot())
" 2>&1)
BOT_EXIT=$?

if [ $BOT_EXIT -eq 0 ] && echo "$BOT_OUTPUT" | grep -q "CONNECTED"; then
    BOT_USERNAME=$(echo "$BOT_OUTPUT" | grep "CONNECTED" | sed 's/CONNECTED: //')
    log_info "Telegram bot verified: $BOT_USERNAME"
elif [ $BOT_EXIT -eq 124 ]; then
    log_error "Telegram bot verification timed out"
    exit 1
else
    log_error "Telegram bot verification failed: $BOT_OUTPUT"
    log_error "Please check your BOT_TOKEN is correct"
    exit 1
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7: Verify Panel API connectivity
# ═══════════════════════════════════════════════════════════════════════════════
log_step 7 "Checking Panel API connectivity..."
PANEL_OUTPUT=$(timeout 15 python -c "
import asyncio
import os
import sys

async def check_panel():
    try:
        import httpx
        domain = os.environ.get('PANEL_DOMAIN', '')
        if not domain:
            print('ERROR: PANEL_DOMAIN not set')
            sys.exit(1)
        
        # Try HTTPS first, then HTTP
        for scheme in ['https', 'http']:
            url = f'{scheme}://{domain}/api/'
            try:
                async with httpx.AsyncClient(verify=False, timeout=10) as client:
                    response = await client.get(url)
                    if response.status_code in [200, 401, 403, 404]:
                        print(f'REACHABLE: {scheme}://{domain} (status: {response.status_code})')
                        return
            except Exception:
                continue
        
        print(f'UNREACHABLE: Could not connect to {domain}')
        sys.exit(1)
    except Exception as e:
        print(f'ERROR: {e}')
        sys.exit(1)

asyncio.run(check_panel())
" 2>&1)
PANEL_EXIT=$?

if [ $PANEL_EXIT -eq 0 ] && echo "$PANEL_OUTPUT" | grep -q "REACHABLE"; then
    log_info "Panel API reachable: $PANEL_DOMAIN"
elif [ $PANEL_EXIT -eq 124 ]; then
    log_warn "Panel API check timed out, continuing..."
else
    log_warn "Panel API not reachable (will retry during runtime)"
    log_debug "$PANEL_OUTPUT"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 8: Verify Python modules
# ═══════════════════════════════════════════════════════════════════════════════
log_step 8 "Verifying Python modules..."
MODULE_OUTPUT=$(timeout 30 python -c "
import sys

modules_to_check = [
    ('telegram_bot.main', 'application', 'Telegram Bot'),
    ('utils.read_config', 'read_config', 'Config Manager'),
    ('utils.panel_api', 'get_token', 'Panel API Client'),
    ('utils.isp_detector', 'ISPDetector', 'ISP Detector'),
    ('utils.redis_cache', 'get_cache', 'Redis Cache'),
    ('utils.warning_system', 'EnhancedWarningSystem', 'Warning System'),
    ('db', 'get_db', 'Database'),
]

failed = []
for module_name, attr_name, display_name in modules_to_check:
    try:
        module = __import__(module_name, fromlist=[attr_name])
        if hasattr(module, attr_name):
            print(f'OK: {display_name}')
        else:
            print(f'WARN: {display_name} (missing {attr_name})')
    except Exception as e:
        print(f'FAIL: {display_name} - {e}')
        failed.append(display_name)

if failed:
    print(f'CRITICAL: {len(failed)} module(s) failed to load')
    sys.exit(1)
else:
    print('ALL_MODULES_OK')
" 2>&1)
MODULE_EXIT=$?

if [ $MODULE_EXIT -eq 0 ] && echo "$MODULE_OUTPUT" | grep -q "ALL_MODULES_OK"; then
    log_info "All modules verified"
    # Show individual module status
    echo "$MODULE_OUTPUT" | grep "^OK:" | while read line; do
        log_debug "${line#OK: }"
    done
elif [ $MODULE_EXIT -eq 124 ]; then
    log_error "Module verification timed out"
    exit 1
else
    log_error "Module verification failed"
    echo "$MODULE_OUTPUT" | grep -E "^(FAIL|WARN|CRITICAL):" | while read line; do
        log_error "$line"
    done
    exit 1
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP COMPLETE
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════"
log_info "PG-Limiter v$VERSION initialized successfully"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Components Status:"
echo "  • Database:     ✓ Ready"
echo "  • Telegram Bot: ✓ $BOT_USERNAME"
echo "  • Panel API:    ✓ $PANEL_DOMAIN"
echo "  • Redis Cache:  $(echo "$REDIS_OUTPUT" | grep -q "CONNECTED" && echo "✓ Connected" || echo "○ In-memory fallback")"
echo ""
echo "Starting limiter..."
echo ""

# Remove deprecated files
rm -f /var/lib/pg-limiter/config.json /app/config.json 2>/dev/null

# Start the main application with unbuffered output
exec python -u limiter.py
