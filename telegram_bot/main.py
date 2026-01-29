"""
Telegram Bot Main Module
Contains the main bot setup and handler registration.
"""

import os
import sys

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        ApplicationBuilder,
        CommandHandler,
        ContextTypes,
        ConversationHandler,
        MessageHandler,
        CallbackQueryHandler,
        filters,
    )
except ImportError:
    print(
        "Module 'python-telegram-bot' is not installed. "
        "Use: 'pip install python-telegram-bot' to install it"
    )
    sys.exit(1)

# Import constants and keyboards
from telegram_bot.constants import (
    CallbackData,
    START_MESSAGE,
    HELP_TEXT,
    GET_DOMAIN,
    GET_USERNAME,
    GET_PASSWORD,
    GET_CONFIRMATION,
    GET_CHAT_ID,
    GET_SPECIAL_LIMIT,
    GET_LIMIT_NUMBER,
    GET_CHAT_ID_TO_REMOVE,
    SET_EXCEPT_USERS,
    REMOVE_EXCEPT_USER,
    GET_GENERAL_LIMIT_NUMBER,
    SET_IPINFO_TOKEN,
    RESTORE_CONFIG,
)
from telegram_bot.keyboards import (
    create_main_menu_keyboard,
    create_settings_menu_keyboard,
    create_limits_menu_keyboard,
    create_users_menu_keyboard,
    create_monitoring_menu_keyboard,
    create_reports_menu_keyboard,
    create_admin_menu_keyboard,
    create_back_to_main_keyboard,
    create_disable_method_keyboard,
    create_whitelist_menu_keyboard,
    create_special_limits_menu_keyboard,
)

# Import handlers
from telegram_bot.handlers.admin import (
    add_admin,
    admins_list,
    check_admin_privilege,
    get_chat_id,
    get_chat_id_to_remove,
    remove_admin,
    handle_admins_list_callback,
    handle_admins_page_callback,
    handle_admin_info_callback,
    handle_delete_admin_callback,
)
from telegram_bot.handlers.limits import (
    set_special_limit,
    get_special_limit,
    get_limit_number,
    show_special_limit_function,
    get_general_limit_number,
    get_general_limit_number_handler,
    handle_general_limit_menu_callback,
    handle_general_limit_preset_callback,
    handle_general_limit_custom_callback,
    handle_set_special_limit_callback,
    handle_general_limit_input,
    handle_special_limit_username_input,
    handle_special_limit_number_input,
    handle_show_special_limit_callback,
    handle_special_limits_page_callback,
    handle_edit_special_limit_callback,
    handle_special_limit_info_callback,
    handle_remove_special_limit_callback,
    handle_special_limit_1_callback,
    handle_special_limit_2_callback,
)
from telegram_bot.handlers.users import (
    set_except_users,
    set_except_users_handler,
    remove_except_user,
    remove_except_user_handler,
    show_except_users,
    show_disabled_users_menu,
    enable_single_user,
    enable_all_disabled_users,
    cleanup_deleted_users_handler,
    handle_show_except_users_callback,
    handle_add_except_user_callback,
    handle_remove_except_user_callback,
    handle_except_user_input,
    handle_remove_except_user_input,
    handle_whitelist_page_callback,
    handle_whitelist_info_callback,
    handle_delete_whitelist_callback,
    handle_filtered_users_menu,
)
from telegram_bot.handlers.settings import (
    set_panel_domain,
    get_domain,
    get_username,
    get_password,
    set_ipinfo_token,
    ipinfo_token_handler,
    handle_enhanced_menu_callback,
    handle_enhanced_toggle_callback,
    handle_ipinfo_callback,
    handle_ipinfo_token_input,
    handle_disable_by_group_callback,
    handle_select_disabled_group_callback,
    handle_user_sync_menu_callback,
    handle_user_sync_interval_callback,
    handle_user_sync_now_callback,
    handle_pending_deletions_callback,
    handle_force_delete_callback,
)
from telegram_bot.handlers.monitoring import (
    monitoring_status,
    monitoring_details,
    clear_monitoring,
)
from telegram_bot.handlers.reports import (
    connection_report_command,
    node_usage_report_command,
    multi_device_users_command,
    users_by_node_command,
    users_by_protocol_command,
    ip_history_12h_command,
    ip_history_48h_command,
)
from telegram_bot.handlers.backup import (
    send_backup,
    restore_config,
    restore_config_handler,
    migrate_backup_start,
    migrate_backup_handler,
    migrate_backup_cancel,
    MIGRATE_WAITING_FILE,
)
from telegram_bot.handlers.punishment import (
    punishment_status,
    punishment_toggle,
    punishment_set_window,
    punishment_set_steps,
    user_violations,
    clear_user_violations,
)
from telegram_bot.handlers.group_filter import (
    group_filter_status,
    group_filter_toggle,
    group_filter_mode,
    group_filter_set,
    group_filter_add,
    group_filter_remove,
    handle_group_filter_menu_callback,
    handle_group_filter_toggle_callback,
    handle_group_filter_mode_callback,
    handle_group_filter_toggle_group_callback,
)
from telegram_bot.handlers.admin_filter import (
    admin_filter_status,
    admin_filter_toggle,
    admin_filter_mode,
    admin_filter_set,
    admin_filter_add,
    admin_filter_remove,
    handle_admin_filter_menu_callback,
    handle_admin_filter_toggle_callback,
    handle_admin_filter_mode_callback,
    handle_admin_filter_toggle_admin_callback,
)

# Import utilities
from telegram_bot.utils import check_admin, add_admin_to_config, add_except_user, handel_special_limit
from utils.logs import get_logger
from utils.read_config import save_config_value, read_config

# Module logger
bot_logger = get_logger("telegram.bot")


# ═══════════════════════════════════════════════════════════════════════════════
# BOT INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

bot_token = None
try:
    bot_token = os.environ.get("BOT_TOKEN", "")
    if bot_token:
        bot_logger.info(f"✓ Bot token loaded from environment: {bot_token[:15]}...")
    else:
        bot_logger.warning("⚠ BOT_TOKEN environment variable is empty")
except Exception as e:
    bot_logger.error(f"⚠ Error loading config at module import: {e}")

# Create application
if bot_token:
    bot_logger.debug("Creating Telegram application with real token...")
    application = ApplicationBuilder().token(bot_token).build()
    bot_logger.info("✓ Telegram application created successfully")
else:
    # Dummy token for module loading - replaced at runtime
    bot_logger.warning("⚠ Using dummy token for module loading")
    application = ApplicationBuilder().token("0000000000:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX").build()


# ═══════════════════════════════════════════════════════════════════════════════
# CORE COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    bot_logger.info(f"📩 Received /start from chat_id={update.effective_chat.id}")
    
    admins = await check_admin()
    bot_logger.debug(f"Admin list: {admins}")
    
    if not admins:
        bot_logger.info("No admins configured, adding first user as admin")
        await add_admin_to_config(update.effective_chat.id)
    admins = await check_admin()
    
    if update.effective_chat.id not in admins:
        bot_logger.warning(f"Unauthorized access attempt from chat_id={update.effective_chat.id}")
        await update.message.reply_html(
            text="Sorry, you do not have permission to use this bot."
        )
        return
    
    bot_logger.info(f"Sending main menu to chat_id={update.effective_chat.id}")
    await update.message.reply_html(
        text=START_MESSAGE,
        reply_markup=create_main_menu_keyboard()
    )


async def help_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    await update.message.reply_html(text=HELP_TEXT)


async def send_logs(msg):
    """Send log messages to all admins."""
    admins = await check_admin()
    for admin in admins:
        try:
            await application.bot.send_message(chat_id=admin, text=msg)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACK QUERY HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all callback queries from inline keyboards."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Admin check
    admins = await check_admin()
    if update.effective_chat.id not in admins:
        await query.edit_message_text(
            text="Sorry, you do not have permission to use this bot."
        )
        return
    
    # Main menu
    if data in [CallbackData.MAIN_MENU, CallbackData.BACK_MAIN]:
        await query.edit_message_text(
            text=START_MESSAGE,
            reply_markup=create_main_menu_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # No-op callback (for buttons that just display info)
    if data == "noop":
        await query.answer()
        return
    
    # Settings menu
    if data == CallbackData.SETTINGS_MENU:
        await query.edit_message_text(
            text="⚙️ <b>Settings Menu</b>\n\nConfigure your bot settings:",
            reply_markup=create_settings_menu_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Limits menu
    if data == CallbackData.LIMITS_MENU:
        await query.edit_message_text(
            text="🎯 <b>Limits Menu</b>\n\nManage user connection limits:",
            reply_markup=create_limits_menu_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Users menu
    if data == CallbackData.USERS_MENU:
        await query.edit_message_text(
            text="👥 <b>Users Menu</b>\n\nManage users and view disabled accounts:",
            reply_markup=create_users_menu_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Monitoring menu
    if data == CallbackData.MONITORING_MENU:
        await query.edit_message_text(
            text="📡 <b>Monitoring Menu</b>\n\nView user monitoring status:",
            reply_markup=create_monitoring_menu_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Reports menu
    if data == CallbackData.REPORTS_MENU:
        await query.edit_message_text(
            text="📊 <b>Reports Menu</b>\n\nGenerate usage reports:",
            reply_markup=create_reports_menu_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Admin menu
    if data == CallbackData.ADMIN_MENU:
        await query.edit_message_text(
            text="👑 <b>Admin Menu</b>\n\nManage bot administrators:",
            reply_markup=create_admin_menu_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Disabled users
    if data == CallbackData.SHOW_DISABLED_USERS:
        await show_disabled_users_menu(query)
        return
    
    if data == CallbackData.ENABLE_ALL_DISABLED:
        await enable_all_disabled_users(query)
        return
    
    if data == "view_users_in_disabled_group":
        from telegram_bot.handlers.users import show_users_in_disabled_group
        await show_users_in_disabled_group(query)
        return
    
    if data.startswith("disabled_group_page:"):
        from telegram_bot.handlers.users import show_users_in_disabled_group
        page = int(data.split(":")[1])
        await show_users_in_disabled_group(query, page)
        return
    
    if data == "fix_stuck_users":
        from telegram_bot.handlers.users import fix_stuck_users_handler
        await fix_stuck_users_handler(query)
        return
    
    if data == CallbackData.CLEANUP_DELETED_USERS:
        await cleanup_deleted_users_handler(query)
        return
    
    # Backup/Restore callbacks
    if data == CallbackData.BACKUP:
        # Create a fake update with the query.message to use send_backup
        class FakeUpdate:
            def __init__(self, message, effective_user, effective_chat):
                self.message = message
                self.effective_user = effective_user
                self.effective_chat = effective_chat
        
        fake_update = FakeUpdate(query.message, update.effective_user, update.effective_chat)
        await query.message.reply_text("📦 Creating backup... Please wait.")
        await send_backup(fake_update, context)
        return
    
    if data == CallbackData.RESTORE:
        await query.edit_message_text(
            text="📥 <b>Restore from Backup</b>\n\n"
                 "Please send your backup file (zip or json format).\n\n"
                 "<b>⚠️ Warning:</b> This will replace your current data!\n\n"
                 "Use /restore command to upload your backup file.",
            reply_markup=create_back_to_main_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Admin management callbacks
    if data == CallbackData.LIST_ADMINS:
        await handle_admins_list_callback(query, context)
        return
    
    if data == CallbackData.ADD_ADMIN:
        await query.edit_message_text(
            text="👤 <b>Add Admin</b>\n\n"
                 "Use the command:\n"
                 "<code>/add_admin</code>\n\n"
                 "Then send the chat ID of the user to add.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back to Admins", callback_data=CallbackData.LIST_ADMINS)],
                [InlineKeyboardButton("« Back to Main Menu", callback_data=CallbackData.MAIN_MENU)],
            ]),
            parse_mode="HTML"
        )
        return
    
    if data == CallbackData.REMOVE_ADMIN:
        await query.edit_message_text(
            text="🗑 <b>Remove Admin</b>\n\n"
                 "Use the command:\n"
                 "<code>/remove_admin</code>\n\n"
                 "Then send the chat ID of the admin to remove.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back to Admins", callback_data=CallbackData.LIST_ADMINS)],
                [InlineKeyboardButton("« Back to Main Menu", callback_data=CallbackData.MAIN_MENU)],
            ]),
            parse_mode="HTML"
        )
        return
    
    # User management callbacks
    if data == CallbackData.WHITELIST_MENU:
        await query.edit_message_text(
            text="✅ <b>Whitelist Users</b>\n\n"
                 "Users in the whitelist are excluded from IP limits.\n"
                 "They can have unlimited connections.",
            reply_markup=create_whitelist_menu_keyboard(),
            parse_mode="HTML"
        )
        return
    
    if data == CallbackData.SPECIAL_LIMITS_MENU:
        await query.edit_message_text(
            text="🎯 <b>Special Limit Users</b>\n\n"
                 "Users with custom connection limits.\n"
                 "These limits override the general limit.",
            reply_markup=create_special_limits_menu_keyboard(),
            parse_mode="HTML"
        )
        return
    
    if data == CallbackData.FILTERED_USERS_MENU:
        await handle_filtered_users_menu(query, context)
        return
    
    if data == CallbackData.BACK_USERS:
        await query.edit_message_text(
            text="👥 <b>Users Menu</b>\n\nManage users and view disabled accounts:",
            reply_markup=create_users_menu_keyboard(),
            parse_mode="HTML"
        )
        return
    
    if data == CallbackData.SHOW_EXCEPT_USERS:
        await handle_show_except_users_callback(query, context)
        return
    
    if data == CallbackData.SET_EXCEPT_USER:
        await handle_add_except_user_callback(query, context)
        return
    
    if data == CallbackData.REMOVE_EXCEPT_USER:
        await handle_remove_except_user_callback(query, context)
        return
    
    if data == CallbackData.SHOW_SPECIAL_LIMIT:
        await handle_show_special_limit_callback(query, context)
        return
    
    if data == CallbackData.SET_SPECIAL_LIMIT:
        await handle_set_special_limit_callback(query, context)
        return
    
    # Monitoring callbacks
    if data == CallbackData.MONITORING_STATUS:
        await monitoring_status(update, context)
        return
    
    if data == CallbackData.MONITORING_DETAILS:
        await monitoring_details(update, context)
        return
    
    if data == CallbackData.MONITORING_CLEAR:
        await clear_monitoring(update, context)
        return
    
    # Reports callbacks
    if data == CallbackData.REPORT_CONNECTION:
        await connection_report_command(update, context)
        return
    
    if data == CallbackData.REPORT_NODE_USAGE:
        await node_usage_report_command(update, context)
        return
    
    if data == CallbackData.REPORT_MULTI_DEVICE:
        await multi_device_users_command(update, context)
        return
    
    if data == CallbackData.REPORT_IP_12H:
        await ip_history_12h_command(update, context)
        return
    
    if data == CallbackData.REPORT_IP_48H:
        await ip_history_48h_command(update, context)
        return
    
    # Settings callbacks
    if data == CallbackData.CREATE_CONFIG:
        await query.edit_message_text(
            text="⚙️ <b>Create Config</b>\n\n"
                 "Use the command:\n"
                 "<code>/create_config</code>",
            reply_markup=create_back_to_main_keyboard(),
            parse_mode="HTML"
        )
        return
    
    if data == CallbackData.SET_IPINFO:
        await handle_ipinfo_callback(query, context)
        return
    
    # Enhanced details callbacks
    if data == CallbackData.ENHANCED_ON:
        await handle_enhanced_toggle_callback(query, context, True)
        return
    
    if data == CallbackData.ENHANCED_OFF:
        await handle_enhanced_toggle_callback(query, context, False)
        return
    
    # Disable method callbacks
    if data == CallbackData.DISABLE_METHOD_MENU:
        config_data = await read_config()
        current_method = config_data.get("disable_method", "status")
        disabled_group_id = config_data.get("disabled_group_id")
        disabled_group_name = None
        
        # Get group name if group method is selected
        if current_method == "group" and disabled_group_id:
            try:
                from utils.user_group_filter import get_all_groups
                from utils.types import PanelType
                panel_config = config_data.get("panel", {})
                panel_data = PanelType(
                    panel_config.get("username", ""),
                    panel_config.get("password", ""),
                    panel_config.get("domain", "")
                )
                groups = await get_all_groups(panel_data)
                for group in groups:
                    if group.get("id") == int(disabled_group_id):
                        disabled_group_name = group.get("name", "Unknown")
                        break
            except Exception:
                pass
        
        await query.edit_message_text(
            text="🚫 <b>Disable Method</b>\n\n"
                 "Choose how users should be disabled:\n\n"
                 "• <b>By Status</b>: Set user status to 'disabled'\n"
                 "• <b>By Group</b>: Move user to a disabled group",
            reply_markup=create_disable_method_keyboard(current_method, disabled_group_name),
            parse_mode="HTML"
        )
        return
    
    if data == CallbackData.DISABLE_BY_STATUS:
        await save_config_value("disable_method", "status")
        await query.edit_message_text(
            text="🚫 <b>Disable Method</b>\n\n"
                 "✅ Method set to <b>By Status</b>\n\n"
                 "• <b>By Status</b>: Set user status to 'disabled'\n"
                 "• <b>By Group</b>: Move user to a disabled group",
            reply_markup=create_disable_method_keyboard("status", None),
            parse_mode="HTML"
        )
        return
    
    if data == CallbackData.DISABLE_BY_GROUP:
        await handle_disable_by_group_callback(query, context)
        return
    
    # Handle select disabled group callbacks
    if data.startswith("select_disabled_group:"):
        group_id = int(data.split(":")[1])
        await handle_select_disabled_group_callback(query, context, group_id)
        return
    
    # User sync callbacks
    if data == CallbackData.USER_SYNC_MENU:
        await handle_user_sync_menu_callback(query, context)
        return
    
    if data == CallbackData.USER_SYNC_1:
        await handle_user_sync_interval_callback(query, context, 1)
        return
    
    if data == CallbackData.USER_SYNC_5:
        await handle_user_sync_interval_callback(query, context, 5)
        return
    
    if data == CallbackData.USER_SYNC_10:
        await handle_user_sync_interval_callback(query, context, 10)
        return
    
    if data == CallbackData.USER_SYNC_15:
        await handle_user_sync_interval_callback(query, context, 15)
        return
    
    if data == CallbackData.USER_SYNC_NOW:
        await handle_user_sync_now_callback(query, context)
        return
    
    if data == CallbackData.USER_SYNC_PENDING:
        await handle_pending_deletions_callback(query, context)
        return
    
    if data == CallbackData.USER_SYNC_FORCE_DELETE:
        await handle_force_delete_callback(query, context)
        return
    
    # Topics callbacks
    if data == CallbackData.TOPICS_MENU:
        from telegram_bot.handlers.topics_settings import handle_topics_menu_callback
        await handle_topics_menu_callback(query, context)
        return
    
    if data == CallbackData.TOPICS_TOGGLE:
        from telegram_bot.handlers.topics_settings import handle_topics_toggle_callback
        await handle_topics_toggle_callback(query, context)
        return
    
    if data == CallbackData.TOPICS_SETUP:
        from telegram_bot.handlers.topics_settings import handle_topics_setup_callback
        await handle_topics_setup_callback(query, context)
        return
    
    if data == CallbackData.TOPICS_CLEAR:
        from telegram_bot.handlers.topics_settings import handle_topics_clear_callback
        await handle_topics_clear_callback(query, context)
        return
    
    # Back to settings callback
    if data == CallbackData.BACK_SETTINGS:
        await query.edit_message_text(
            text="⚙️ <b>Settings Menu</b>\n\nConfigure your bot settings:",
            reply_markup=create_settings_menu_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Punishment callbacks
    if data == CallbackData.PUNISHMENT_MENU:
        await punishment_status(update, context)
        return
    
    if data == CallbackData.PUNISHMENT_TOGGLE:
        await punishment_toggle(update, context)
        return
    
    if data == CallbackData.PUNISHMENT_WINDOW:
        await punishment_set_window(update, context)
        return
    
    if data == CallbackData.PUNISHMENT_STEPS:
        await punishment_set_steps(update, context)
        return
    
    # Punishment window hour selection callbacks
    if data == CallbackData.PUNISHMENT_WINDOW_24:
        from telegram_bot.handlers.punishment import punishment_set_window_hours
        await punishment_set_window_hours(update, context, 24)
        return
    
    if data == CallbackData.PUNISHMENT_WINDOW_48:
        from telegram_bot.handlers.punishment import punishment_set_window_hours
        await punishment_set_window_hours(update, context, 48)
        return
    
    if data == CallbackData.PUNISHMENT_WINDOW_72:
        from telegram_bot.handlers.punishment import punishment_set_window_hours
        await punishment_set_window_hours(update, context, 72)
        return
    
    if data == CallbackData.PUNISHMENT_WINDOW_168:
        from telegram_bot.handlers.punishment import punishment_set_window_hours
        await punishment_set_window_hours(update, context, 168)
        return
    
    # Punishment steps callbacks
    if data == CallbackData.PUNISHMENT_ADD_STEP:
        from telegram_bot.handlers.punishment import punishment_add_step_menu
        await punishment_add_step_menu(update, context)
        return
    
    if data == CallbackData.PUNISHMENT_STEPS_RESET:
        from telegram_bot.handlers.punishment import punishment_reset_steps
        await punishment_reset_steps(update, context)
        return
    
    # Punishment step type callbacks
    if data == CallbackData.PUNISHMENT_STEP_WARNING:
        from telegram_bot.handlers.punishment import punishment_add_step
        await punishment_add_step(update, context, "warning", 0)
        return
    
    if data == CallbackData.PUNISHMENT_STEP_DISABLE_10:
        from telegram_bot.handlers.punishment import punishment_add_step
        await punishment_add_step(update, context, "disable", 10)
        return
    
    if data == CallbackData.PUNISHMENT_STEP_DISABLE_30:
        from telegram_bot.handlers.punishment import punishment_add_step
        await punishment_add_step(update, context, "disable", 30)
        return
    
    if data == CallbackData.PUNISHMENT_STEP_DISABLE_60:
        from telegram_bot.handlers.punishment import punishment_add_step
        await punishment_add_step(update, context, "disable", 60)
        return
    
    if data == CallbackData.PUNISHMENT_STEP_DISABLE_240:
        from telegram_bot.handlers.punishment import punishment_add_step
        await punishment_add_step(update, context, "disable", 240)
        return
    
    if data == CallbackData.PUNISHMENT_STEP_DISABLE_UNLIMITED:
        from telegram_bot.handlers.punishment import punishment_add_step
        await punishment_add_step(update, context, "disable", 0)
        return
    
    # Handle remove step callbacks
    if data.startswith("punishment_remove_step:"):
        step_index = int(data.split(":")[1])
        from telegram_bot.handlers.punishment import punishment_remove_step
        await punishment_remove_step(update, context, step_index)
        return
    
    # Handle edit step callbacks (click on step to edit)
    if data.startswith("punishment_edit_step:"):
        step_index = int(data.split(":")[1])
        from telegram_bot.handlers.punishment import punishment_edit_step
        await punishment_edit_step(update, context, step_index)
        return
    
    # Handle update step callbacks (apply new type/duration to step)
    if data.startswith("punishment_update_step:"):
        parts = data.split(":")
        step_index = int(parts[1])
        step_type = parts[2]
        duration = int(parts[3])
        from telegram_bot.handlers.punishment import punishment_update_step
        await punishment_update_step(update, context, step_index, step_type, duration)
        return
    
    # Group filter callbacks
    if data == CallbackData.GROUP_FILTER_MENU:
        await handle_group_filter_menu_callback(query, context)
        return
    
    if data == CallbackData.GROUP_FILTER_TOGGLE:
        await handle_group_filter_toggle_callback(query, context)
        return
    
    if data == CallbackData.GROUP_FILTER_MODE_INCLUDE:
        await handle_group_filter_mode_callback(query, context, "include")
        return
    
    if data == CallbackData.GROUP_FILTER_MODE_EXCLUDE:
        await handle_group_filter_mode_callback(query, context, "exclude")
        return
    
    # Handle group filter toggle group callbacks
    if data.startswith("gf_toggle_group:"):
        group_id = int(data.split(":")[1])
        await handle_group_filter_toggle_group_callback(query, context, group_id)
        return
    
    # Admin filter callbacks
    if data == CallbackData.ADMIN_FILTER_MENU:
        await handle_admin_filter_menu_callback(query, context)
        return
    
    if data == CallbackData.ADMIN_FILTER_TOGGLE:
        await handle_admin_filter_toggle_callback(query, context)
        return
    
    if data == CallbackData.ADMIN_FILTER_MODE_INCLUDE:
        await handle_admin_filter_mode_callback(query, context, "include")
        return
    
    if data == CallbackData.ADMIN_FILTER_MODE_EXCLUDE:
        await handle_admin_filter_mode_callback(query, context, "exclude")
        return
    
    # Handle admin filter toggle admin callbacks
    if data.startswith("af_toggle_admin:"):
        username = data.split(":")[1]
        await handle_admin_filter_toggle_admin_callback(query, context, username)
        return
    
    # CDN mode callbacks
    if data == CallbackData.CDN_MODE_MENU:
        from telegram_bot.handlers.settings import cdn_mode_menu_callback
        await cdn_mode_menu_callback(query, context)
        return
    
    if data == CallbackData.CDN_MODE_ADD:
        from telegram_bot.handlers.settings import cdn_mode_add_callback
        result = await cdn_mode_add_callback(query, context)
        # If it returns a state, we're waiting for text input
        if result is not None:
            context.user_data["waiting_for"] = "cdn_inbound"
        return
    
    if data == CallbackData.CDN_MODE_REMOVE:
        from telegram_bot.handlers.settings import cdn_mode_remove_callback
        await cdn_mode_remove_callback(query, context)
        return
    
    if data == CallbackData.CDN_MODE_CLEAR:
        from telegram_bot.handlers.settings import cdn_mode_clear_callback
        await cdn_mode_clear_callback(query, context)
        return
    
    # Handle CDN remove inbound callbacks
    if data.startswith("cdn_remove_"):
        from telegram_bot.handlers.settings import cdn_mode_remove_inbound_callback
        await cdn_mode_remove_inbound_callback(query, context)
        return
    
    # Node settings callbacks
    if data == CallbackData.NODE_SETTINGS_MENU:
        from telegram_bot.handlers.settings import node_settings_menu_callback
        await node_settings_menu_callback(query, context)
        return
    
    if data == CallbackData.NODE_SETTINGS_REFRESH:
        from telegram_bot.handlers.settings import node_settings_refresh_callback
        await node_settings_refresh_callback(query, context)
        return
    
    if data == CallbackData.NODE_CDN_MENU:
        from telegram_bot.handlers.settings import node_cdn_menu_callback
        await node_cdn_menu_callback(query, context)
        return
    
    if data == CallbackData.NODE_DISABLED_MENU:
        from telegram_bot.handlers.settings import node_disabled_menu_callback
        await node_disabled_menu_callback(query, context)
        return
    
    if data == CallbackData.NODE_CDN_CLEAR:
        from telegram_bot.handlers.settings import node_cdn_clear_callback
        await node_cdn_clear_callback(query, context)
        return
    
    if data == CallbackData.NODE_DISABLED_CLEAR:
        from telegram_bot.handlers.settings import node_disabled_clear_callback
        await node_disabled_clear_callback(query, context)
        return
    
    # Handle node toggle callbacks
    if data.startswith("node_cdn_toggle:"):
        node_id = int(data.split(":")[1])
        from telegram_bot.handlers.settings import node_cdn_toggle_callback
        await node_cdn_toggle_callback(query, context, node_id)
        return
    
    if data.startswith("node_disabled_toggle:"):
        node_id = int(data.split(":")[1])
        from telegram_bot.handlers.settings import node_disabled_toggle_callback
        await node_disabled_toggle_callback(query, context, node_id)
        return
    
    # Handle dynamic callbacks
    if data.startswith("enable_user:"):
        username = data.split(":", 1)[1]
        await enable_single_user(query, username)
        return
    
    if data.startswith("disabled_page:"):
        page = int(data.split(":", 1)[1])
        await show_disabled_users_menu(query, page=page)
        return
    
    # Handle special limits pagination
    if data.startswith("special_limits_page:"):
        page = int(data.split(":", 1)[1])
        await handle_special_limits_page_callback(query, context, page)
        return
    
    # Handle edit special limit callback
    if data.startswith("edit_special_limit:"):
        username = data.split(":", 1)[1]
        await handle_edit_special_limit_callback(query, context, username)
        return
    
    # Handle special limit info callback
    if data.startswith("special_limit_info:"):
        username = data.split(":", 1)[1]
        await handle_special_limit_info_callback(query, context, username)
        return
    
    # Handle remove special limit callback
    if data.startswith("remove_special_limit:"):
        username = data.split(":", 1)[1]
        await handle_remove_special_limit_callback(query, context, username)
        return
    
    # Handle whitelist pagination
    if data.startswith("whitelist_page:"):
        page = int(data.split(":", 1)[1])
        await handle_whitelist_page_callback(query, context, page)
        return
    
    # Handle whitelist info callback
    if data.startswith("whitelist_info:"):
        username = data.split(":", 1)[1]
        await handle_whitelist_info_callback(query, context, username)
        return
    
    # Handle delete whitelist callback
    if data.startswith("delete_whitelist:"):
        username = data.split(":", 1)[1]
        await handle_delete_whitelist_callback(query, context, username)
        return
    
    # Handle filtered users pagination
    if data.startswith("filtered_page:"):
        page = int(data.split(":", 1)[1])
        await handle_filtered_users_menu(query, context, page)
        return
    
    # Handle filtered user info callback (placeholder - just shows user is monitored)
    if data.startswith("filtered_info:"):
        username = data.split(":", 1)[1]
        await query.answer(f"User {username} - under general limit", show_alert=True)
        return
    
    # Handle admins pagination
    if data.startswith("admins_page:"):
        page = int(data.split(":", 1)[1])
        await handle_admins_page_callback(query, context, page)
        return
    
    # Handle admin info callback
    if data.startswith("admin_info:"):
        admin_id = data.split(":", 1)[1]
        await handle_admin_info_callback(query, context, admin_id)
        return
    
    # Handle delete admin callback
    if data.startswith("delete_admin:"):
        admin_id = data.split(":", 1)[1]
        await handle_delete_admin_callback(query, context, admin_id)
        return
    
    # Handle add_except:username callback (from notification buttons)
    if data.startswith("add_except:"):
        username = data.split(":", 1)[1]
        result = await add_except_user(username)
        if result:
            await query.edit_message_text(
                text=f"✅ User <code>{username}</code> added to except list!",
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text(
                text=f"⚠️ Failed to add <code>{username}</code> to except list.",
                parse_mode="HTML"
            )
        return
    
    # Handle set_limit:username:limit callback (from notification buttons)
    if data.startswith("set_limit:"):
        parts = data.split(":")
        if len(parts) >= 3:
            username = parts[1]
            limit = int(parts[2])
            result = await handel_special_limit(username, limit)
            if result:
                await query.edit_message_text(
                    text=f"✅ Special limit <b>{limit}</b> set for <code>{username}</code>!",
                    parse_mode="HTML"
                )
            else:
                await query.edit_message_text(
                    text=f"⚠️ Failed to set special limit for <code>{username}</code>.",
                    parse_mode="HTML"
                )
        return
    
    # Handle custom_limit:username callback (from notification buttons)
    if data.startswith("custom_limit:"):
        username = data.split(":", 1)[1]
        context.user_data["selected_user"] = username
        context.user_data["waiting_for"] = "notification_custom_limit"
        await query.edit_message_text(
            text=f"🎯 <b>Set Custom Limit for: {username}</b>\n\n"
                 "Send the device limit number (e.g., <code>3</code>):",
            parse_mode="HTML"
        )
        return
    
    # General limit preset callbacks
    if data == CallbackData.GENERAL_LIMIT_2:
        await handle_general_limit_preset_callback(query, context, 2)
        return
    
    if data == CallbackData.GENERAL_LIMIT_3:
        await handle_general_limit_preset_callback(query, context, 3)
        return
    
    if data == CallbackData.GENERAL_LIMIT_4:
        await handle_general_limit_preset_callback(query, context, 4)
        return
    
    if data == CallbackData.GENERAL_LIMIT_CUSTOM:
        await handle_general_limit_custom_callback(query, context)
        return
    
    # Special limit preset callbacks (when setting limit for selected user)
    if data == CallbackData.SPECIAL_LIMIT_1:
        await handle_special_limit_1_callback(query, context)
        return
    
    if data == CallbackData.SPECIAL_LIMIT_2:
        await handle_special_limit_2_callback(query, context)
        return
    
    if data == CallbackData.SPECIAL_LIMIT_CUSTOM:
        from telegram_bot.handlers.limits import handle_special_limit_custom_callback
        await handle_special_limit_custom_callback(query, context)
        return
    
    # Handle user_info: callback (informational only, from disabled users list)
    if data.startswith("user_info:"):
        username = data.split(":", 1)[1]
        await query.answer(f"User: {username}", show_alert=False)
        return
    
    # Handle noop callback (page indicator buttons that should do nothing)
    if data == "noop":
        await query.answer()
        return
    
    # Fallback for unhandled callbacks
    await query.edit_message_text(
        text=f"⚠️ Unhandled callback: {data}",
        reply_markup=create_back_to_main_keyboard(),
        parse_mode="HTML"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for inline keyboard flows."""
    waiting_for = context.user_data.get("waiting_for")
    
    if not waiting_for:
        return
    
    # Handle different input types based on waiting_for state
    if waiting_for == "general_limit":
        await handle_general_limit_input(update, context)
        return
    
    if waiting_for == "special_limit_username":
        await handle_special_limit_username_input(update, context)
        return
    
    if waiting_for == "special_limit_number":
        await handle_special_limit_number_input(update, context)
        return
    
    if waiting_for == "ipinfo_token":
        await handle_ipinfo_token_input(update, context)
        return
    
    # Handle except user input
    if waiting_for == "except_user":
        await handle_except_user_input(update, context)
        return
    
    if waiting_for == "remove_except_user":
        await handle_remove_except_user_input(update, context)
        return
    
    # Handle notification custom limit input
    if waiting_for == "notification_custom_limit":
        username = context.user_data.get("selected_user")
        if username:
            text = update.message.text.strip()
            try:
                limit = int(text)
                result = await handel_special_limit(username, limit)
                if result:
                    await update.message.reply_html(
                        text=f"✅ Special limit <b>{limit}</b> set for <code>{username}</code>!",
                        reply_markup=create_back_to_main_keyboard()
                    )
                else:
                    await update.message.reply_html(
                        text=f"⚠️ Failed to set special limit for <code>{username}</code>.",
                        reply_markup=create_back_to_main_keyboard()
                    )
            except ValueError:
                await update.message.reply_html(
                    text="❌ Invalid number. Please send a valid number.",
                    reply_markup=create_back_to_main_keyboard()
                )
            context.user_data.pop("selected_user", None)
        context.user_data["waiting_for"] = None
        return
    
    # Handle CDN inbound input
    if waiting_for == "cdn_inbound":
        from telegram_bot.handlers.settings import cdn_mode_add_handler
        await cdn_mode_add_handler(update, context)
        context.user_data["waiting_for"] = None
        return
    
    # Reset if no handler found
    context.user_data["waiting_for"] = None


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

async def document_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads (for restore)."""
    waiting_for = context.user_data.get("waiting_for")
    
    if waiting_for == "restore":
        await restore_config_handler(update, context)
        return


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLER REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

# Core commands
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))

# Callback and message handlers
application.add_handler(CallbackQueryHandler(callback_query_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

# NOTE: Document handler is registered AFTER all ConversationHandlers
# to allow ConversationHandlers to handle documents first

# Admin management
application.add_handler(
    ConversationHandler(
        entry_points=[CommandHandler("add_admin", add_admin)],
        states={GET_CHAT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_chat_id)]},
        fallbacks=[],
    )
)
application.add_handler(
    ConversationHandler(
        entry_points=[CommandHandler("remove_admin", remove_admin)],
        states={GET_CHAT_ID_TO_REMOVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_chat_id_to_remove)]},
        fallbacks=[],
    )
)
application.add_handler(CommandHandler("admins_list", admins_list))

# Config management
application.add_handler(
    ConversationHandler(
        entry_points=[CommandHandler("create_config", set_panel_domain)],
        states={
            GET_DOMAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_domain)],
            GET_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_username)],
            GET_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
        },
        fallbacks=[],
    )
)

# Limits management
application.add_handler(
    ConversationHandler(
        entry_points=[CommandHandler("set_special_limit", set_special_limit)],
        states={
            GET_SPECIAL_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_special_limit)],
            GET_LIMIT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_limit_number)],
        },
        fallbacks=[],
    )
)
application.add_handler(CommandHandler("show_special_limit", show_special_limit_function))
application.add_handler(
    ConversationHandler(
        entry_points=[CommandHandler("set_general_limit_number", get_general_limit_number)],
        states={GET_GENERAL_LIMIT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_general_limit_number_handler)]},
        fallbacks=[],
    )
)

# User management
application.add_handler(
    ConversationHandler(
        entry_points=[CommandHandler("set_except_user", set_except_users)],
        states={SET_EXCEPT_USERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_except_users_handler)]},
        fallbacks=[],
    )
)
application.add_handler(
    ConversationHandler(
        entry_points=[CommandHandler("remove_except_user", remove_except_user)],
        states={REMOVE_EXCEPT_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_except_user_handler)]},
        fallbacks=[],
    )
)
application.add_handler(CommandHandler("show_except_users", show_except_users))

# Settings
application.add_handler(
    ConversationHandler(
        entry_points=[CommandHandler("set_ipinfo_token", set_ipinfo_token)],
        states={SET_IPINFO_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ipinfo_token_handler)]},
        fallbacks=[],
    )
)

# Monitoring
application.add_handler(CommandHandler("monitoring_status", monitoring_status))
application.add_handler(CommandHandler("monitoring_details", monitoring_details))
application.add_handler(CommandHandler("clear_monitoring", clear_monitoring))

# Reports
application.add_handler(CommandHandler("connection_report", connection_report_command))
application.add_handler(CommandHandler("node_usage", node_usage_report_command))
application.add_handler(CommandHandler("multi_device_users", multi_device_users_command))
application.add_handler(CommandHandler("users_by_node", users_by_node_command))
application.add_handler(CommandHandler("users_by_protocol", users_by_protocol_command))
application.add_handler(CommandHandler("ip_history_12h", ip_history_12h_command))
application.add_handler(CommandHandler("ip_history_48h", ip_history_48h_command))

# Backup
application.add_handler(CommandHandler("backup", send_backup))
application.add_handler(
    ConversationHandler(
        entry_points=[CommandHandler("restore", restore_config)],
        states={RESTORE_CONFIG: [MessageHandler(filters.Document.ALL, restore_config_handler)]},
        fallbacks=[],
    )
)

# Migrate backup (JSON to SQLite)
application.add_handler(
    ConversationHandler(
        entry_points=[CommandHandler("migrate_backup", migrate_backup_start)],
        states={
            MIGRATE_WAITING_FILE: [
                MessageHandler(filters.Document.ALL, migrate_backup_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, migrate_backup_handler),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", migrate_backup_cancel),
        ],
        allow_reentry=True,
    )
)

# Punishment system
application.add_handler(CommandHandler("punishment_status", punishment_status))
application.add_handler(CommandHandler("punishment_toggle", punishment_toggle))
application.add_handler(CommandHandler("punishment_set_window", punishment_set_window))
application.add_handler(CommandHandler("punishment_set_steps", punishment_set_steps))
application.add_handler(CommandHandler("user_violations", user_violations))
application.add_handler(CommandHandler("clear_user_violations", clear_user_violations))

# Group filter
application.add_handler(CommandHandler("group_filter_status", group_filter_status))
application.add_handler(CommandHandler("group_filter_toggle", group_filter_toggle))
application.add_handler(CommandHandler("group_filter_mode", group_filter_mode))
application.add_handler(CommandHandler("group_filter_set", group_filter_set))
application.add_handler(CommandHandler("group_filter_add", group_filter_add))
application.add_handler(CommandHandler("group_filter_remove", group_filter_remove))

# Admin filter
application.add_handler(CommandHandler("admin_filter_status", admin_filter_status))
application.add_handler(CommandHandler("admin_filter_toggle", admin_filter_toggle))
application.add_handler(CommandHandler("admin_filter_mode", admin_filter_mode))
application.add_handler(CommandHandler("admin_filter_set", admin_filter_set))
application.add_handler(CommandHandler("admin_filter_add", admin_filter_add))
application.add_handler(CommandHandler("admin_filter_remove", admin_filter_remove))
# Fallback document handler (must be after all ConversationHandlers)
application.add_handler(MessageHandler(filters.Document.ALL, document_message_handler))
