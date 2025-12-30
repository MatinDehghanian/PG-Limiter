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
            # Check standard Docker paths first
            docker_config_dir = "/etc/opt/pg-limiter"
            if os.path.exists(docker_config_dir):
                for filename in os.listdir(docker_config_dir):
                    filepath = os.path.join(docker_config_dir, filename)
                    if os.path.isfile(filepath):
                        zipf.write(filepath, f"config/{filename}")
            
            # Also check local .env
            if os.path.exists(".env"):
                zipf.write(".env", "config/.env")
            
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
            for env_name in ["config/.env", ".env"]:
                src_path = os.path.join(temp_dir, env_name)
                if os.path.exists(src_path):
                    env_dst = "/etc/opt/pg-limiter/.env" if os.path.exists("/etc/opt/pg-limiter") else ".env"
                    shutil.copy(src_path, env_dst)
                    env_restored = True
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
            
            await update.message.reply_html(
                "✅ <b>Backup restored successfully!</b>\n\n"
                f"• Environment file: {'✓' if env_restored else '✗'}\n"
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
    check = await check_admin_privilege(update)
    if check is not None:
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
    return MIGRATE_WAITING_FILE


async def migrate_backup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the uploaded JSON file and migrate it to database."""
    try:
        if not update.message.document:
            await update.message.reply_html(
                "❌ Please send a JSON file.\n"
                "Use /migrate_backup to try again."
            )
            return ConversationHandler.END
        
        file_name = update.message.document.file_name
        
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
        
        try:
            data = json.loads(file_content.decode('utf-8'))
        except json.JSONDecodeError as e:
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
        
        from db import get_db
        from db.crud import (
            ConfigCRUD,
            UserLimitCRUD,
            ExceptUserCRUD,
            DisabledUserCRUD,
            ViolationHistoryCRUD,
        )
        
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
