"""
Backup and restore handlers for the Telegram bot.
Includes functions for creating and restoring backups.
"""

import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from telegram_bot.constants import RESTORE_CONFIG
from telegram_bot.handlers.admin import check_admin_privilege
from utils.logs import get_logger

backup_logger = get_logger("backup")

# Conversation state for migration
MIGRATE_WAITING_FILE = 100


def create_migrate_keyboard():
    """Create keyboard for migration options."""
    keyboard = [
        [InlineKeyboardButton("📥 Send JSON File", callback_data="migrate_send_file")],
        [InlineKeyboardButton("« Back", callback_data="settings_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_backup(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Send a comprehensive backup zip file to the user."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    
    try:
        await update.message.reply_text("📦 Creating backup... Please wait.")
        
        # Create temp directory for backup
        temp_dir = tempfile.mkdtemp()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"pg-limiter-backup-{timestamp}.zip"
        zip_path = os.path.join(temp_dir, zip_name)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Check Docker mounted config directory (read-only mount)
            docker_config_dir = "/etc/opt/pg-limiter"
            config_found = False
            if os.path.exists(docker_config_dir):
                for filename in os.listdir(docker_config_dir):
                    filepath = os.path.join(docker_config_dir, filename)
                    if os.path.isfile(filepath):
                        zipf.write(filepath, f"config/{filename}")
                        config_found = True
                        backup_logger.info(f"Added config file: {filename}")
            
            # Also check local .env if not found in config dir
            if os.path.exists(".env"):
                zipf.write(".env", "config/.env")
                config_found = True
                backup_logger.info("Added local .env file")
            
            if not config_found:
                backup_logger.warning("No config files found to backup")
            
            # Add data files from /var/lib/pg-limiter/ (or local data/)
            data_dirs = [
                "/var/lib/pg-limiter/data",
                "data",
            ]
            for data_dir in data_dirs:
                if os.path.exists(data_dir) and os.path.isdir(data_dir):
                    for root, dirs, files in os.walk(data_dir):
                        for file in files:
                            filepath = os.path.join(root, file)
                            arcname = os.path.join("data", os.path.relpath(filepath, data_dir))
                            zipf.write(filepath, arcname)
                    break
            
            # Add legacy JSON files if they exist
            legacy_files = [
                ".disable_users.json",
                ".violation_history.json",
                ".user_groups_backup.json",
            ]
            for legacy_file in legacy_files:
                if os.path.exists(legacy_file):
                    zipf.write(legacy_file, f"legacy/{legacy_file}")
            
            # Add backup info
            hostname = "unknown"
            try:
                hostname = os.uname().nodename
            except AttributeError:
                pass
            
            backup_info = f"""PG-Limiter Backup
Created: {datetime.now().isoformat()}
Hostname: {hostname}

Contents:
- config/: Configuration files (.env)
- data/: Database and persistent data
- legacy/: Legacy JSON files (if any)

To restore:
1. Send this zip file to the bot with /restore command
2. Or use: pg-limiter restore <this-file.zip>
"""
            zipf.writestr("backup_info.txt", backup_info)
        
        # Send the zip file
        with open(zip_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=zip_name,
                caption=(
                    "✅ <b>Backup created successfully!</b>\n\n"
                    "📁 This backup includes:\n"
                    "• Configuration files\n"
                    "• Database (SQLite)\n"
                    "• Legacy JSON files (if any)\n\n"
                    "💡 To restore, use /restore command and send this file."
                ),
                parse_mode="HTML",
            )
        
        # Cleanup
        shutil.rmtree(temp_dir)
        
    except Exception as e:
        await update.message.reply_html(
            f"❌ <b>Error creating backup:</b>\n<code>{str(e)}</code>"
        )


async def restore_config(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Start the restore process by asking for the backup file."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    
    await update.message.reply_html(
        "📥 <b>Restore from Backup</b>\n\n"
        "Please send your backup file (zip or json format).\n\n"
        "<b>⚠️ Warning:</b> This will replace your current data!"
    )
    return RESTORE_CONFIG


async def restore_config_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the uploaded backup file and restore it."""
    try:
        # Check if a document was sent
        if not update.message.document:
            await update.message.reply_html(
                "❌ Please send a valid backup file (zip or json).\n"
                "Use /restore to try again."
            )
            return ConversationHandler.END
        
        file_name = update.message.document.file_name
        
        # Download the file
        file = await update.message.document.get_file()
        file_content = await file.download_as_bytearray()
        
        if file_name.endswith('.zip'):
            # Handle zip backup (new format)
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, "backup.zip")
            
            with open(zip_path, 'wb') as f:
                f.write(file_content)
            
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zipf.extractall(temp_dir)
            
            # Restore .env file if present
            env_restored = False
            env_restore_note = ""
            for env_name in ["config/.env", ".env"]:
                src_path = os.path.join(temp_dir, env_name)
                if os.path.exists(src_path):
                    # Determine destination - check if config dir exists AND is writable
                    config_dir = "/etc/opt/pg-limiter"
                    if os.path.exists(config_dir) and os.access(config_dir, os.W_OK):
                        env_dst = os.path.join(config_dir, ".env")
                    else:
                        env_dst = ".env"
                        if os.path.exists(config_dir):
                            # Config dir exists but is read-only (Docker mount)
                            env_restore_note = " (saved locally - config dir is read-only)"
                    
                    shutil.copy(src_path, env_dst)
                    env_restored = True
                    backup_logger.info(f"Restored .env to: {env_dst}")
                    break
            
            # Restore data files
            data_src = os.path.join(temp_dir, "data")
            if os.path.exists(data_src):
                data_dst = "/var/lib/pg-limiter/data" if os.path.exists("/var/lib/pg-limiter") else "data"
                
                # Copy database files
                for item in os.listdir(data_src):
                    src = os.path.join(data_src, item)
                    dst = os.path.join(data_dst, item)
                    if os.path.isfile(src):
                        os.makedirs(data_dst, exist_ok=True)
                        shutil.copy2(src, dst)
            
            # Restore legacy files (for migration)
            legacy_src = os.path.join(temp_dir, "legacy")
            if os.path.exists(legacy_src):
                for item in os.listdir(legacy_src):
                    src = os.path.join(legacy_src, item)
                    if os.path.isfile(src):
                        shutil.copy2(src, item)
            
            # Cleanup
            shutil.rmtree(temp_dir)
            
            env_status = '✓' + env_restore_note if env_restored else '✗'
            await update.message.reply_html(
                "✅ <b>Backup restored successfully!</b>\n\n"
                f"• Environment file: {env_status}\n"
                "• Database: ✓\n\n"
                "⚠️ Please restart the service for changes to take effect."
            )
            
        elif file_name.endswith('.json'):
            # Handle legacy JSON config - migrate to database
            try:
                config_data = json.loads(file_content.decode('utf-8'))
                
                from db import get_db, ConfigCRUD, UserLimitCRUD, ExceptUserCRUD
                
                async with get_db() as db:
                    # Import settings to database
                    if "disable_method" in config_data:
                        await ConfigCRUD.set(db, "disable_method", str(config_data["disable_method"]))
                    if config_data.get("disabled_group_id"):
                        await ConfigCRUD.set(db, "disabled_group_id", str(config_data["disabled_group_id"]))
                    if config_data.get("enhanced_details") is not None:
                        await ConfigCRUD.set(db, "enhanced_details", str(config_data["enhanced_details"]).lower())
                    
                    # Import special limits
                    special_limits = config_data.get("limits", {}).get("special", {})
                    for username, limit in special_limits.items():
                        await UserLimitCRUD.set(db, username, limit)
                    
                    # Import except users
                    except_users = config_data.get("except_users", [])
                    for username in except_users:
                        await ExceptUserCRUD.add(db, username, "Restored from backup")
                
                await update.message.reply_html(
                    "✅ <b>Legacy config imported to database!</b>\n\n"
                    "📝 Panel credentials should be set in .env file.\n"
                    "⚠️ Restart the service for changes to take effect."
                )
                
            except json.JSONDecodeError as e:
                await update.message.reply_html(
                    f"❌ Invalid JSON format: {str(e)}\nUse /restore to try again."
                )
                return ConversationHandler.END
        else:
            await update.message.reply_html(
                "❌ Unsupported file format. Please send a .zip or .json file.\n"
                "Use /restore to try again."
            )
            return ConversationHandler.END
        
    except Exception as e:
        await update.message.reply_html(
            f"❌ <b>Error during restore:</b>\n<code>{str(e)}</code>\n\nUse /restore to try again."
        )
    
    context.user_data["waiting_for"] = None
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
# MIGRATE BACKUP - Full JSON backup migration to SQLite
# ═══════════════════════════════════════════════════════════════════════════════


async def migrate_backup_start(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Start the backup migration process."""
    backup_logger.info(f"migrate_backup_start called by user {update.effective_user.id}")
    
    check = await check_admin_privilege(update)
    if check is not None:
        backup_logger.warning(f"User {update.effective_user.id} not admin for migrate_backup")
        return check
    
    message = update.message or update.callback_query.message
    
    await message.reply_html(
        "📥 <b>Migrate JSON Backup to Database</b>\n\n"
        "This will import data from your old JSON backup files into the SQLite database.\n\n"
        "<b>Supported files:</b>\n"
        "• <code>config.json</code> - Configuration, limits, except users\n"
        "• <code>.disable_users.json</code> - Disabled users list\n"
        "• <code>.violation_history.json</code> - Violation records\n"
        "• Any JSON file with the above format\n\n"
        "📤 <b>Please send your JSON file now</b>\n\n"
        "<i>Send /cancel to abort</i>"
    )
    backup_logger.info("Waiting for user to send JSON file...")
    return MIGRATE_WAITING_FILE


async def migrate_backup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the uploaded JSON file and migrate it to database."""
    backup_logger.info(f"migrate_backup_handler called")
    backup_logger.info(f"  - Message: {update.message}")
    backup_logger.info(f"  - Document: {update.message.document if update.message else None}")
    backup_logger.info(f"  - Text: {update.message.text if update.message else None}")
    
    try:
        if not update.message:
            backup_logger.error("No message in update")
            return ConversationHandler.END
        
        if not update.message.document:
            backup_logger.warning("No document in message - prompting user again")
            await update.message.reply_html(
                "❌ Please send a <b>JSON file</b> (not text).\n\n"
                "Make sure to send the file as a document attachment.\n"
                "Use /cancel to abort."
            )
            return MIGRATE_WAITING_FILE  # Stay in the conversation
        
        file_name = update.message.document.file_name
        backup_logger.info(f"Received file: {file_name}")
        
        if not file_name.endswith('.json'):
            await update.message.reply_html(
                "❌ Please send a .json file.\n"
                "Use /migrate_backup to try again."
            )
            return ConversationHandler.END
        
        await update.message.reply_text("⏳ Processing backup file...")
        
        # Download the file
        file = await update.message.document.get_file()
        file_content = await file.download_as_bytearray()
        backup_logger.info(f"Downloaded file, size: {len(file_content)} bytes")
        
        try:
            data = json.loads(file_content.decode('utf-8'))
            backup_logger.info(f"Parsed JSON, keys: {list(data.keys())[:10]}")
        except json.JSONDecodeError as e:
            backup_logger.error(f"JSON decode error: {e}")
            await update.message.reply_html(
                f"❌ Invalid JSON format:\n<code>{str(e)}</code>"
            )
            return ConversationHandler.END
        
        # Migration statistics
        stats = {
            "config_items": 0,
            "special_limits": 0,
            "except_users": 0,
            "disabled_users": 0,
            "violations": 0,
            "errors": [],
        }
        
        try:
            from db import get_db
            from db.crud import (
                ConfigCRUD,
                UserLimitCRUD,
                ExceptUserCRUD,
                DisabledUserCRUD,
                ViolationHistoryCRUD,
            )
            backup_logger.info("Database imports successful")
        except Exception as import_err:
            backup_logger.error(f"Failed to import database modules: {import_err}")
            await update.message.reply_html(
                f"❌ Database import error:\n<code>{str(import_err)}</code>"
            )
            return ConversationHandler.END
        
        try:
            async with get_db() as db:
                # ─────────────────────────────────────────────────────────
                # Detect file type and migrate accordingly
                # ─────────────────────────────────────────────────────────
                
                # Check if it's a config.json file
                if "panel" in data or "limits" in data or "timing" in data:
                    backup_logger.info("Detected config.json format")
                    
                    # Migrate panel settings (for reference only - actual auth is from .env)
                    if "panel" in data:
                        await ConfigCRUD.set(db, "panel_backup", data["panel"])
                        stats["config_items"] += 1
                    
                    # Migrate limits
                    if "limits" in data:
                        limits = data["limits"]
                        
                        # General limit
                        if "general" in limits:
                            await ConfigCRUD.set(db, "general_limit", limits["general"])
                            stats["config_items"] += 1
                        
                        # Special limits
                        special = limits.get("special", {})
                        for username, limit in special.items():
                            try:
                                await UserLimitCRUD.set_limit(db, username, int(limit))
                                stats["special_limits"] += 1
                            except Exception as e:
                                stats["errors"].append(f"Special limit {username}: {e}")
                        
                        # Except users from limits
                        except_list = limits.get("except_users", [])
                        for username in except_list:
                            try:
                                await ExceptUserCRUD.add(db, username, "Migrated from config.json")
                                stats["except_users"] += 1
                            except Exception as e:
                                stats["errors"].append(f"Except user {username}: {e}")
                
                # Root-level except_users
                if "except_users" in data and isinstance(data["except_users"], list):
                    for username in data["except_users"]:
                        try:
                            await ExceptUserCRUD.add(db, username, "Migrated from config.json")
                            stats["except_users"] += 1
                        except Exception:
                            pass  # May already exist
                
                # Timing settings
                if "timing" in data:
                    await ConfigCRUD.set(db, "timing", data["timing"])
                    stats["config_items"] += 1
                elif "check_interval" in data or "time_to_active_users" in data:
                    timing = {
                        "check_interval": data.get("check_interval", 60),
                        "time_to_active_users": data.get("time_to_active_users", 900),
                    }
                    await ConfigCRUD.set(db, "timing", timing)
                    stats["config_items"] += 1
                
                # Display settings
                if "display" in data:
                    await ConfigCRUD.set(db, "display", data["display"])
                    stats["config_items"] += 1
                
                if "enhanced_details" in data:
                    await ConfigCRUD.set(db, "enhanced_details", str(data["enhanced_details"]).lower())
                    stats["config_items"] += 1
                
                # Disable method
                if "disable_method" in data:
                    await ConfigCRUD.set(db, "disable_method", str(data["disable_method"]))
                    stats["config_items"] += 1
                
                if "disabled_group_id" in data:
                    await ConfigCRUD.set(db, "disabled_group_id", str(data["disabled_group_id"]))
                    stats["config_items"] += 1
                
                # Country code
                if "country_code" in data:
                    await ConfigCRUD.set(db, "country_code", data["country_code"])
                    stats["config_items"] += 1
                
                # Punishment settings
                if "punishment" in data:
                    await ConfigCRUD.set(db, "punishment", data["punishment"])
                    stats["config_items"] += 1
                
                # Group filter
                if "group_filter" in data:
                    await ConfigCRUD.set(db, "group_filter", data["group_filter"])
                    stats["config_items"] += 1
            
            # Check if it's a .disable_users.json file
            if "disabled_users" in data or "disable_user" in data or "enable_at" in data:
                backup_logger.info("Detected disable_users.json format")
                
                disabled_users = data.get("disabled_users", data.get("disable_user", {}))
                enable_at = data.get("enable_at", {})
                
                if isinstance(disabled_users, list):
                    # Old format: list of usernames
                    import time
                    current_time = time.time()
                    for username in disabled_users:
                        try:
                            await DisabledUserCRUD.add(
                                db,
                                username=username,
                                disabled_at=current_time,
                                reason="Migrated from JSON backup",
                            )
                            stats["disabled_users"] += 1
                        except Exception as e:
                            stats["errors"].append(f"Disabled user {username}: {e}")
                elif isinstance(disabled_users, dict):
                    # New format: {username: timestamp}
                    for username, disabled_at in disabled_users.items():
                        try:
                            user_enable_at = enable_at.get(username)
                            await DisabledUserCRUD.add(
                                db,
                                username=username,
                                disabled_at=disabled_at,
                                enable_at=user_enable_at,
                                reason="Migrated from JSON backup",
                            )
                            stats["disabled_users"] += 1
                        except Exception as e:
                            stats["errors"].append(f"Disabled user {username}: {e}")
            
            # Check if it's a .violation_history.json file
            if "violations" in data:
                backup_logger.info("Detected violation_history.json format")
                
                violations = data["violations"]
                for username, records in violations.items():
                    if isinstance(records, list):
                        for record in records:
                            try:
                                await ViolationHistoryCRUD.add(
                                    db,
                                    username=username,
                                    step_applied=record.get("step_applied", 0),
                                    disable_duration=record.get("disable_duration", 0),
                                )
                                stats["violations"] += 1
                            except Exception as e:
                                stats["errors"].append(f"Violation {username}: {e}")
        except Exception as db_err:
            backup_logger.error(f"Database error during migration: {db_err}")
            await update.message.reply_html(
                f"❌ Database error:\n<code>{str(db_err)}</code>"
            )
            return ConversationHandler.END
        
        # Build result message
        total = (
            stats["config_items"] + 
            stats["special_limits"] + 
            stats["except_users"] + 
            stats["disabled_users"] + 
            stats["violations"]
        )
        
        result_msg = (
            f"✅ <b>Migration Complete!</b>\n\n"
            f"📊 <b>Statistics:</b>\n"
            f"• Config items: {stats['config_items']}\n"
            f"• Special limits: {stats['special_limits']}\n"
            f"• Except users: {stats['except_users']}\n"
            f"• Disabled users: {stats['disabled_users']}\n"
            f"• Violations: {stats['violations']}\n"
            f"─────────────────\n"
            f"<b>Total items:</b> {total}\n"
        )
        
        if stats["errors"]:
            result_msg += f"\n⚠️ <b>Errors ({len(stats['errors'])}):</b>\n"
            for err in stats["errors"][:5]:  # Show first 5 errors
                result_msg += f"• <code>{err}</code>\n"
            if len(stats["errors"]) > 5:
                result_msg += f"... and {len(stats['errors']) - 5} more\n"
        
        result_msg += "\n💡 <i>Changes take effect immediately, no restart needed.</i>"
        
        await update.message.reply_html(result_msg)
        backup_logger.info(f"Migration complete: {stats}")
        
    except Exception as e:
        backup_logger.error(f"Migration error: {e}")
        await update.message.reply_html(
            f"❌ <b>Migration failed:</b>\n<code>{str(e)}</code>"
        )
    
    return ConversationHandler.END


async def migrate_backup_cancel(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Cancel the migration process."""
    await update.message.reply_text("❌ Migration cancelled.")
    return ConversationHandler.END


async def send_automatic_backup():
    """
    Send an automatic backup to all admins.
    Called by scheduler every 6 hours.
    """
    from telegram_bot.main import application
    from telegram_bot.utils import check_admin
    from telegram_bot.topics import TopicType, get_topics_manager
    
    backup_logger.info("📦 Creating automatic backup...")
    
    try:
        # Create temp directory for backup
        temp_dir = tempfile.mkdtemp()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"pg-limiter-auto-backup-{timestamp}.zip"
        zip_path = os.path.join(temp_dir, zip_name)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Check Docker mounted config directory
            docker_config_dir = "/etc/opt/pg-limiter"
            if os.path.exists(docker_config_dir):
                for filename in os.listdir(docker_config_dir):
                    filepath = os.path.join(docker_config_dir, filename)
                    if os.path.isfile(filepath):
                        zipf.write(filepath, f"config/{filename}")
            
            if os.path.exists(".env"):
                zipf.write(".env", "config/.env")
            
            # Add data files
            data_dirs = ["/var/lib/pg-limiter/data", "data"]
            for data_dir in data_dirs:
                if os.path.exists(data_dir) and os.path.isdir(data_dir):
                    for root, _, files in os.walk(data_dir):
                        for file in files:
                            filepath = os.path.join(root, file)
                            arcname = os.path.join("data", os.path.relpath(filepath, data_dir))
                            zipf.write(filepath, arcname)
                    break
            
            # Add legacy files
            for legacy_file in [".disable_users.json", ".violation_history.json", ".user_groups_backup.json"]:
                if os.path.exists(legacy_file):
                    zipf.write(legacy_file, f"legacy/{legacy_file}")
            
            # Add backup info
            backup_info = f"""PG-Limiter Automatic Backup
Created: {datetime.now().isoformat()}
Type: Automatic (scheduled every 6 hours)
"""
            zipf.writestr("backup_info.txt", backup_info)
        
        # Send to all admins
        admins = await check_admin()
        topics_manager = get_topics_manager()
        
        for admin in admins:
            thread_id = topics_manager.get_topic_id(admin, TopicType.BACKUPS)
            try:
                with open(zip_path, 'rb') as f:
                    await application.bot.send_document(
                        chat_id=admin,
                        document=f,
                        filename=zip_name,
                        caption=(
                            "💾 <b>Automatic Backup</b>\n\n"
                            f"🕐 Time: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                            "📁 Includes: Config, Database, Legacy files\n\n"
                            "💡 <i>Backups are sent every 6 hours</i>"
                        ),
                        parse_mode="HTML",
                        message_thread_id=thread_id
                    )
                backup_logger.info(f"✅ Automatic backup sent to admin {admin}")
            except Exception as e:
                backup_logger.error(f"❌ Failed to send backup to admin {admin}: {e}")
        
        # Cleanup
        shutil.rmtree(temp_dir)
        backup_logger.info("✅ Automatic backup completed successfully")
        
    except Exception as e:
        backup_logger.error(f"❌ Automatic backup failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-BACKUP SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

AUTO_BACKUP_CONFIG_FILE = "data/auto_backup_config.json"

# Default config: enabled with 1 hour interval
DEFAULT_AUTO_BACKUP_CONFIG = {
    "enabled": True,
    "interval_hours": 1
}


def get_auto_backup_config() -> dict:
    """Get the current auto-backup configuration."""
    if os.path.exists(AUTO_BACKUP_CONFIG_FILE):
        try:
            with open(AUTO_BACKUP_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            backup_logger.error(f"Error reading auto-backup config: {e}")
    return DEFAULT_AUTO_BACKUP_CONFIG.copy()


def save_auto_backup_config(config: dict):
    """Save the auto-backup configuration."""
    os.makedirs(os.path.dirname(AUTO_BACKUP_CONFIG_FILE), exist_ok=True)
    with open(AUTO_BACKUP_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)


def create_auto_backup_keyboard(config: dict) -> InlineKeyboardMarkup:
    """Create the auto-backup settings menu keyboard."""
    enabled = config.get("enabled", True)
    interval = config.get("interval_hours", 1)
    
    toggle_text = "🔴 Disable Auto-Backup" if enabled else "🟢 Enable Auto-Backup"
    
    keyboard = [
        [InlineKeyboardButton(toggle_text, callback_data="auto_backup_toggle")],
    ]
    
    if enabled:
        # Interval options with checkmarks
        intervals = [
            (1, "1h", "auto_backup_interval_1h"),
            (3, "3h", "auto_backup_interval_3h"),
            (6, "6h", "auto_backup_interval_6h"),
            (12, "12h", "auto_backup_interval_12h"),
        ]
        
        interval_buttons = []
        for hours, label, callback in intervals:
            check = "✅ " if interval == hours else ""
            interval_buttons.append(
                InlineKeyboardButton(f"{check}{label}", callback_data=callback)
            )
        
        # Split into rows of 2
        keyboard.append(interval_buttons[:2])
        keyboard.append(interval_buttons[2:])
        
        # Backup now button
        keyboard.append([
            InlineKeyboardButton("📦 Backup Now", callback_data="auto_backup_now")
        ])
    
    keyboard.append([
        InlineKeyboardButton("« Back to Settings", callback_data="settings_menu")
    ])
    
    return InlineKeyboardMarkup(keyboard)


async def auto_backup_menu(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Show the auto-backup settings menu."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    
    config = get_auto_backup_config()
    enabled = config.get("enabled", True)
    interval = config.get("interval_hours", 1)
    
    status_icon = "✅" if enabled else "❌"
    status_text = "Enabled" if enabled else "Disabled"
    
    message = (
        f"💾 <b>Auto-Backup Settings</b>\n\n"
        f"Status: {status_icon} <code>{status_text}</code>\n"
        f"Interval: <code>{interval} hour(s)</code>\n\n"
        f"💡 <i>Automatic backups are sent to all admins\n"
        f"containing config, database, and legacy files.</i>"
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=message,
            parse_mode="HTML",
            reply_markup=create_auto_backup_keyboard(config)
        )
    else:
        await update.message.reply_html(
            text=message,
            reply_markup=create_auto_backup_keyboard(config)
        )
    
    return ConversationHandler.END


async def auto_backup_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle auto-backup on/off."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    
    config = get_auto_backup_config()
    config["enabled"] = not config.get("enabled", True)
    save_auto_backup_config(config)
    
    # Reschedule the job
    await reschedule_auto_backup(context.application)
    
    return await auto_backup_menu(update, context)


async def auto_backup_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE, hours: int):
    """Set the auto-backup interval."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    
    config = get_auto_backup_config()
    config["interval_hours"] = hours
    save_auto_backup_config(config)
    
    # Reschedule the job
    await reschedule_auto_backup(context.application)
    
    if update.callback_query:
        await update.callback_query.answer(f"✅ Interval set to {hours} hour(s)")
    
    return await auto_backup_menu(update, context)


async def auto_backup_now(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Trigger an immediate backup."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    
    if update.callback_query:
        await update.callback_query.answer("📦 Creating backup...")
    
    # Run the backup
    await send_automatic_backup()
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text="✅ <b>Backup sent successfully!</b>\n\n"
                 "The backup has been sent to all admins.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data="auto_backup_menu")]
            ])
        )
    
    return ConversationHandler.END


async def reschedule_auto_backup(application):
    """Reschedule the auto-backup job based on current config."""
    job_queue = application.job_queue
    if not job_queue:
        backup_logger.warning("Job queue not available")
        return
    
    # Remove existing job
    current_jobs = job_queue.get_jobs_by_name("automatic_backup")
    for job in current_jobs:
        job.schedule_removal()
    
    config = get_auto_backup_config()
    if not config.get("enabled", True):
        backup_logger.info("Auto-backup disabled, job removed")
        return
    
    interval_hours = config.get("interval_hours", 1)
    interval_seconds = interval_hours * 3600
    
    job_queue.run_repeating(
        lambda context: send_automatic_backup(),
        interval=interval_seconds,
        first=interval_seconds,
        name="automatic_backup"
    )
    backup_logger.info(f"✓ Auto-backup scheduled (every {interval_hours} hour(s))")


# Callback handlers for interval settings
async def handle_auto_backup_interval_1h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await auto_backup_set_interval(update, context, 1)

async def handle_auto_backup_interval_3h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await auto_backup_set_interval(update, context, 3)

async def handle_auto_backup_interval_6h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await auto_backup_set_interval(update, context, 6)

async def handle_auto_backup_interval_12h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await auto_backup_set_interval(update, context, 12)
