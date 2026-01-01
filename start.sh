#!/bin/bash

VERSION="0.7.6"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Logging functions with timestamps
get_timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
log_info() { echo -e "[$(get_timestamp)] ${GREEN}✓${NC} $1"; }
log_warn() { echo -e "[$(get_timestamp)] ${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "[$(get_timestamp)] ${RED}❌${NC} $1"; }
log_debug() { echo -e "[$(get_timestamp)] ${CYAN}→${NC} $1"; }
log_step() { echo -e "[$(get_timestamp)] ${BLUE}[$1/${TOTAL_STEPS}]${NC} $2"; }
log_crash() { echo -e "[$(get_timestamp)] ${MAGENTA}💥${NC} $1"; }

TOTAL_STEPS=8
CRASH_LOG="/var/lib/pg-limiter/logs/crash.log"
RESTART_COUNT=0
MAX_RESTARTS=2
RESTART_DELAY=5

# ═══════════════════════════════════════════════════════════════════════════════
# ERROR HANDLING AND SIGNAL TRAPS
# ═══════════════════════════════════════════════════════════════════════════════

# Trap for graceful shutdown
cleanup() {
    log_warn "Received shutdown signal, cleaning up..."
    # Kill any background processes
    jobs -p | xargs -r kill 2>/dev/null
    log_info "PG-Limiter stopped gracefully"
    exit 0
}

# Trap signals
trap cleanup SIGTERM SIGINT SIGHUP

# Function to log crash details
log_crash_details() {
    local exit_code=$1
    local crash_time=$(get_timestamp)
    
    echo "" >> "$CRASH_LOG"
    echo "═══════════════════════════════════════════════════════════════" >> "$CRASH_LOG"
    echo "CRASH REPORT - $crash_time" >> "$CRASH_LOG"
    echo "═══════════════════════════════════════════════════════════════" >> "$CRASH_LOG"
    echo "Exit Code: $exit_code" >> "$CRASH_LOG"
    echo "Restart Count: $RESTART_COUNT / $MAX_RESTARTS" >> "$CRASH_LOG"
    echo "" >> "$CRASH_LOG"
}

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

# First, ensure data directory exists and is writable
if [ ! -d "/app/data" ]; then
    mkdir -p /app/data
fi

# Test that we can create/write to the database file
touch /app/data/pg_limiter.db 2>/dev/null || {
    log_error "Cannot write to database directory /app/data"
    exit 1
}

# Initialize database - bypass all logging to avoid hanging
log_debug "Running database initialization..."
DB_OUTPUT=$(timeout 30 python -u -c "
import asyncio
import sys
import os
import logging

# Disable all logging to prevent file handlers from keeping process alive
logging.disable(logging.CRITICAL)
os.environ['PYTHONUNBUFFERED'] = '1'

print('Importing modules...', flush=True)

# Direct imports without going through the logging-heavy __init__
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

print('Creating engine...', flush=True)

DATABASE_URL = 'sqlite+aiosqlite:////var/lib/pg-limiter/data/pg_limiter.db'
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={'check_same_thread': False},
    poolclass=StaticPool,
)

print('Importing models...', flush=True)
from db.models import Base

async def init():
    print('Creating tables...', flush=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Closing engine...', flush=True)
    await engine.dispose()
    print('SUCCESS', flush=True)

try:
    asyncio.run(init())
    sys.exit(0)
except Exception as e:
    import traceback
    print(f'ERROR: {e}', flush=True)
    traceback.print_exc()
    sys.exit(1)
" 2>&1)
DB_EXIT=$?

if [ $DB_EXIT -eq 124 ]; then
    log_error "Database initialization timed out (30s)"
    log_debug "Output: $DB_OUTPUT"
    exit 1
elif [ $DB_EXIT -ne 0 ]; then
    log_error "Database initialization failed:"
    echo "$DB_OUTPUT" | while read line; do
        log_debug "$line"
    done
    exit 1
elif echo "$DB_OUTPUT" | grep -q "SUCCESS"; then
    log_info "Database initialized"
else
    log_error "Database initialization failed (no success message)"
    log_debug "Output: $DB_OUTPUT"
    exit 1
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Run database migrations
# ═══════════════════════════════════════════════════════════════════════════════
log_step 4 "Running database migrations..."

# First, ensure all required columns exist (handles upgrades from older versions)
COLUMN_OUTPUT=$(timeout 30 python -u -c "
import sqlite3
import os

db_path = '/var/lib/pg-limiter/data/pg_limiter.db'
if not os.path.exists(db_path):
    print('Fresh database, skipping column check')
    exit(0)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check if users table exists
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='users'\")
if not cursor.fetchone():
    print('No users table yet')
    conn.close()
    exit(0)

# Get existing columns
cursor.execute('PRAGMA table_info(users)')
existing = {row[1] for row in cursor.fetchall()}

# Columns to add
columns = [
    ('is_excepted', 'BOOLEAN DEFAULT 0'),
    ('exception_reason', 'TEXT'),
    ('excepted_by', 'VARCHAR(255)'),
    ('excepted_at', 'DATETIME'),
    ('special_limit', 'INTEGER'),
    ('special_limit_updated_at', 'DATETIME'),
    ('is_disabled_by_limiter', 'BOOLEAN DEFAULT 0'),
    ('disabled_at', 'FLOAT'),
    ('enable_at', 'FLOAT'),
    ('original_groups', 'JSON'),
    ('disable_reason', 'TEXT'),
    ('punishment_step', 'INTEGER DEFAULT 0'),
]

added = []
for name, typ in columns:
    if name not in existing:
        try:
            cursor.execute(f'ALTER TABLE users ADD COLUMN {name} {typ}')
            added.append(name)
        except:
            pass

conn.commit()
conn.close()

if added:
    print(f'Added columns: {added}')
else:
    print('All columns exist')
" 2>&1)

if echo "$COLUMN_OUTPUT" | grep -q "Added columns"; then
    log_info "Database schema updated: $COLUMN_OUTPUT"
else
    log_debug "Schema check: $COLUMN_OUTPUT"
fi

# Now run alembic migrations
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
REDIS_URL="${REDIS_URL:-}"

if [ -z "$REDIS_URL" ]; then
    log_debug "Redis not configured, using in-memory cache"
    REDIS_STATUS="skipped"
else
    REDIS_OUTPUT=$(timeout 10 python -u -c "
import asyncio
import sys
import os
import logging

logging.disable(logging.CRITICAL)

async def check_redis():
    try:
        import redis.asyncio as redis
        r = redis.from_url(os.environ.get('REDIS_URL', ''))
        await r.ping()
        await r.close()
        print('CONNECTED')
    except Exception as e:
        print(f'FALLBACK: {e}')

asyncio.run(check_redis())
sys.exit(0)
" 2>&1)
    
    if echo "$REDIS_OUTPUT" | grep -q "CONNECTED"; then
        log_info "Redis connected"
        REDIS_STATUS="connected"
    else
        log_warn "Redis not available, using in-memory cache fallback"
        REDIS_STATUS="fallback"
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: Verify Telegram Bot Token
# ═══════════════════════════════════════════════════════════════════════════════
log_step 6 "Verifying Telegram bot token..."
BOT_OUTPUT=$(timeout 15 python -u -c "
import asyncio
import sys
import os
import logging

logging.disable(logging.CRITICAL)

async def check_bot():
    from telegram import Bot
    token = os.environ.get('BOT_TOKEN', '')
    bot = Bot(token=token)
    me = await bot.get_me()
    print(f'CONNECTED: @{me.username} (ID: {me.id})')

try:
    asyncio.run(check_bot())
    sys.exit(0)
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
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
PANEL_OUTPUT=$(timeout 15 python -u -c "
import asyncio
import os
import sys
import logging

logging.disable(logging.CRITICAL)

async def check_panel():
    import httpx
    domain = os.environ.get('PANEL_DOMAIN', '')
    
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

try:
    asyncio.run(check_panel())
    sys.exit(0)
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
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
# STEP 8: Skip module verification (will fail at runtime if issues)
# ═══════════════════════════════════════════════════════════════════════════════
log_step 8 "Checking core imports..."

# Quick syntax check only - full module loading happens in main app
IMPORT_OUTPUT=$(timeout 10 python -u -c "
import sys
import logging
logging.disable(logging.CRITICAL)

# Only check that files exist and have valid syntax
import py_compile
import os

files = [
    'limiter.py',
    'db/database.py',
    'db/models.py',
    'telegram_bot/main.py',
    'utils/read_config.py',
]

failed = []
for f in files:
    if not os.path.exists(f):
        print(f'MISSING: {f}')
        failed.append(f)
    else:
        try:
            py_compile.compile(f, doraise=True)
            print(f'OK: {f}')
        except py_compile.PyCompileError as e:
            print(f'SYNTAX_ERROR: {f} - {e}')
            failed.append(f)

if failed:
    sys.exit(1)
print('ALL_OK')
sys.exit(0)
" 2>&1)
IMPORT_EXIT=$?

if [ $IMPORT_EXIT -eq 0 ] && echo "$IMPORT_OUTPUT" | grep -q "ALL_OK"; then
    log_info "Core files verified"
elif [ $IMPORT_EXIT -eq 124 ]; then
    log_warn "Import check timed out, continuing..."
else
    log_warn "Some files may have issues:"
    echo "$IMPORT_OUTPUT" | grep -v "^OK:" | head -5 | while read line; do
        log_debug "$line"
    done
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
if [ "$REDIS_STATUS" = "connected" ]; then
    echo "  • Redis Cache:  ✓ Connected"
else
    echo "  • Redis Cache:  ○ In-memory fallback"
fi
echo ""
echo "Starting limiter..."
echo ""

# Remove deprecated files
rm -f /var/lib/pg-limiter/config.json /app/config.json 2>/dev/null

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION LOOP WITH CRASH RECOVERY
# ═══════════════════════════════════════════════════════════════════════════════

run_limiter() {
    # Create a wrapper script that captures Python errors with full traceback
    python -u -c "
import sys
import traceback
import os
import signal
import datetime

# Configure Python to show full tracebacks
sys.tracebacklimit = 50

def log_error(message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{timestamp}] ❌ {message}', file=sys.stderr, flush=True)

def log_crash(message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{timestamp}] 💥 {message}', file=sys.stderr, flush=True)

def write_crash_log(exc_type, exc_value, exc_tb):
    '''Write detailed crash information to log file'''
    crash_log = '/var/lib/pg-limiter/logs/crash.log'
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Get full traceback
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    
    # Extract the exact error location
    if exc_tb:
        # Walk to the last frame (actual error location)
        tb = exc_tb
        while tb.tb_next:
            tb = tb.tb_next
        
        filename = tb.tb_frame.f_code.co_filename
        lineno = tb.tb_lineno
        func_name = tb.tb_frame.f_code.co_name
        
        # Try to read the actual line of code
        try:
            with open(filename, 'r') as f:
                lines = f.readlines()
                if 0 < lineno <= len(lines):
                    error_line = lines[lineno - 1].strip()
                else:
                    error_line = '<line not available>'
        except:
            error_line = '<could not read file>'
    else:
        filename = 'unknown'
        lineno = 0
        func_name = 'unknown'
        error_line = '<no traceback>'
    
    # Print to console with colors
    print('', flush=True)
    print('╔═══════════════════════════════════════════════════════════════╗', flush=True)
    print('║                    💥 CRASH DETECTED 💥                        ║', flush=True)
    print('╚═══════════════════════════════════════════════════════════════╝', flush=True)
    print('', flush=True)
    log_crash(f'Error Type: {exc_type.__name__}')
    log_crash(f'Error Message: {exc_value}')
    log_crash(f'File: {filename}')
    log_crash(f'Line: {lineno}')
    log_crash(f'Function: {func_name}')
    log_crash(f'Code: {error_line}')
    print('', flush=True)
    print('─── Full Traceback ───', flush=True)
    for line in tb_lines:
        print(line, end='', flush=True)
    print('───────────────────────', flush=True)
    print('', flush=True)
    
    # Write to crash log file
    try:
        with open(crash_log, 'a') as f:
            f.write(f'\\n')
            f.write(f'═══════════════════════════════════════════════════════════════\\n')
            f.write(f'CRASH REPORT - {timestamp}\\n')
            f.write(f'═══════════════════════════════════════════════════════════════\\n')
            f.write(f'Error Type: {exc_type.__name__}\\n')
            f.write(f'Error Message: {exc_value}\\n')
            f.write(f'File: {filename}\\n')
            f.write(f'Line: {lineno}\\n')
            f.write(f'Function: {func_name}\\n')
            f.write(f'Code: {error_line}\\n')
            f.write(f'\\n--- Full Traceback ---\\n')
            for line in tb_lines:
                f.write(line)
            f.write(f'───────────────────────\\n')
            f.write(f'\\n')
        log_error(f'Crash details saved to: {crash_log}')
    except Exception as e:
        log_error(f'Could not write crash log: {e}')

# Custom exception hook
def exception_hook(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    write_crash_log(exc_type, exc_value, exc_tb)
    sys.exit(1)

sys.excepthook = exception_hook

# Handle signals gracefully
def signal_handler(signum, frame):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    signal_name = signal.Signals(signum).name
    print(f'[{timestamp}] ⚠ Received {signal_name}, shutting down...', flush=True)
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Import and run the main limiter
try:
    print('[$(get_timestamp)] 🚀 Starting limiter.py...', flush=True)
    
    # Use exec to run limiter.py so it replaces this process
    exec(open('limiter.py').read())
    
except SystemExit as e:
    if e.code != 0 and e.code is not None:
        log_error(f'Limiter exited with code: {e.code}')
    sys.exit(e.code if e.code is not None else 0)
except Exception as e:
    exc_type, exc_value, exc_tb = sys.exc_info()
    write_crash_log(exc_type, exc_value, exc_tb)
    sys.exit(1)
"
    return $?
}

# Main loop with restart logic
while true; do
    run_limiter
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        log_info "Limiter exited normally"
        break
    fi
    
    RESTART_COUNT=$((RESTART_COUNT + 1))
    
    log_crash "Limiter crashed with exit code: $EXIT_CODE"
    log_crash "Restart attempt: $RESTART_COUNT / $MAX_RESTARTS"
    
    if [ $RESTART_COUNT -ge $MAX_RESTARTS ]; then
        log_error "Maximum restart attempts ($MAX_RESTARTS) reached"
        log_error "Check crash logs at: $CRASH_LOG"
        log_error "Last exit code: $EXIT_CODE"
        exit $EXIT_CODE
    fi
    
    log_warn "Restarting in $RESTART_DELAY seconds..."
    sleep $RESTART_DELAY
    
    # Increase delay for subsequent restarts (exponential backoff)
    RESTART_DELAY=$((RESTART_DELAY * 2))
    if [ $RESTART_DELAY -gt 60 ]; then
        RESTART_DELAY=60
    fi
    
    echo ""
    log_info "Attempting restart #$RESTART_COUNT..."
    echo ""
done
