"""
Admin filter handlers for the Telegram bot.
Commands for managing admin-based user filtering.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from telegram_bot.utils import check_admin, add_admin_to_config, read_json_file, write_json_file
from telegram_bot.keyboards import create_back_to_main_keyboard
from utils.read_config import read_config


async def _send_response(update: Update, text: str, reply_markup=None):
    """Send response handling both message and callback query contexts."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_html(
            text=text,
            reply_markup=reply_markup
        )


async def check_admin_privilege(update: Update):
    """
    Checks if the user has admin privileges.
    """
    admins = await check_admin()
    if not admins:
        await add_admin_to_config(update.effective_chat.id)
    admins = await check_admin()
    if update.effective_chat.id not in admins:
        await _send_response(
            update,
            "Sorry, you do not have permission to execute this command."
        )
        return ConversationHandler.END


async def admin_filter_status(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Show the current admin filter configuration."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        from utils.admin_filter import get_admin_filter_status_text, get_all_admins
        from utils.types import PanelType
        
        config_data = await read_config()
        
        # Get panel data for admin lookup
        panel_config = config_data.get("panel", {})
        panel_data = PanelType(
            panel_config.get("username", ""),
            panel_config.get("password", ""),
            panel_config.get("domain", "")
        )
        
        # Get all admins for display
        admins = await get_all_admins(panel_data)
        
        # Get filter status
        status_text = get_admin_filter_status_text(config_data, admins)
        
        # Build admins list
        admins_list = []
        for admin in admins:
            username = admin.get("username", "?")
            is_sudo = "👑" if admin.get("is_sudo", False) else ""
            is_disabled = "🔒" if admin.get("is_disabled", False) else ""
            admins_list.append(f"  • <code>{username}</code> {is_sudo}{is_disabled}")
        
        admins_display = "\n".join(admins_list) if admins_list else "  No admins found"
        
        message = (
            f"👤 <b>Admin Filter Status</b>\n\n"
            f"{status_text}\n\n"
            f"<b>Available Admins:</b>\n{admins_display}\n\n"
            f"<b>Commands:</b>\n"
            f"/admin_filter_toggle - Enable/disable\n"
            f"/admin_filter_mode - Set include/exclude\n"
            f"/admin_filter_set - Set admin usernames\n"
            f"/admin_filter_add - Add admin\n"
            f"/admin_filter_remove - Remove admin"
        )
        
        await _send_response(update, message, reply_markup=create_back_to_main_keyboard())
        
    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def admin_filter_toggle(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Toggle admin filter on/off."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        from utils.read_config import save_config_value, invalidate_config_cache
        
        config_data = await read_config()
        filter_config = config_data.get("admin_filter", {})
        current_state = filter_config.get("enabled", False)
        new_state = not current_state
        
        await save_config_value("admin_filter_enabled", "true" if new_state else "false")
        await invalidate_config_cache()
        
        status = "✅ Enabled" if new_state else "❌ Disabled"
        await _send_response(update, f"👤 Admin filter is now: {status}")
        
    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def admin_filter_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set admin filter mode (include/exclude)."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    if context.args:
        mode = context.args[0].lower()
        if mode not in ["include", "exclude"]:
            await _send_response(
                update,
                "❌ Invalid mode. Use <code>include</code> or <code>exclude</code>"
            )
            return ConversationHandler.END
        
        try:
            from utils.read_config import save_config_value, invalidate_config_cache
            
            await save_config_value("admin_filter_mode", mode)
            await invalidate_config_cache()
            
            if mode == "include":
                desc = "Only users of specified admins will be monitored"
            else:
                desc = "Users of specified admins will be whitelisted"
            
            await _send_response(
                update,
                f"✅ Admin filter mode set to: <code>{mode}</code>\n{desc}"
            )
            
        except Exception as e:
            await _send_response(update, f"❌ Error: {str(e)}")
        
        return ConversationHandler.END
    
    await _send_response(
        update,
        "👤 <b>Set Admin Filter Mode</b>\n\n"
        "<code>/admin_filter_mode include</code>\n"
        "  → Only users of specified admins are monitored\n\n"
        "<code>/admin_filter_mode exclude</code>\n"
        "  → Users of specified admins are whitelisted (not limited)"
    )
    return ConversationHandler.END


async def admin_filter_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the list of admin usernames for filtering."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    if context.args:
        try:
            from utils.read_config import save_config_value, invalidate_config_cache
            
            # Parse admin usernames from arguments
            admin_usernames = []
            for arg in context.args:
                # Support comma-separated and space-separated
                for username in arg.split(","):
                    username = username.strip()
                    if username:
                        admin_usernames.append(username)
            
            # Save as comma-separated string
            await save_config_value("admin_filter_usernames", ",".join(admin_usernames))
            await invalidate_config_cache()
            
            await _send_response(
                update,
                f"✅ Admin filter set to: <code>{admin_usernames}</code>"
            )
            
        except Exception as e:
            await _send_response(update, f"❌ Error: {str(e)}")
        
        return ConversationHandler.END
    
    await _send_response(
        update,
        "👤 <b>Set Admin Filter Admins</b>\n\n"
        "Usage: <code>/admin_filter_set admin1 admin2</code>\n"
        "Or: <code>/admin_filter_set admin1,admin2</code>\n\n"
        "Use /admin_filter_status to see available admins."
    )
    return ConversationHandler.END


async def admin_filter_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add an admin username to the filter."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    if not context.args:
        await _send_response(
            update,
            "❌ Please provide an admin username.\n"
            "Example: <code>/admin_filter_add admin1</code>"
        )
        return ConversationHandler.END
    
    try:
        from utils.read_config import save_config_value, invalidate_config_cache
        
        admin_username = context.args[0].strip()
        
        config_data = await read_config()
        filter_config = config_data.get("admin_filter", {})
        current_admins = filter_config.get("admin_usernames", [])
        
        if admin_username in current_admins:
            await _send_response(
                update,
                f"ℹ️ Admin <code>{admin_username}</code> is already in the filter."
            )
            return ConversationHandler.END
        
        current_admins.append(admin_username)
        await save_config_value("admin_filter_usernames", ",".join(current_admins))
        await invalidate_config_cache()
        
        await _send_response(
            update,
            f"✅ Added admin <code>{admin_username}</code> to filter.\n"
            f"Current admins: <code>{current_admins}</code>"
        )
        
    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def admin_filter_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove an admin username from the filter."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    if not context.args:
        await _send_response(
            update,
            "❌ Please provide an admin username.\n"
            "Example: <code>/admin_filter_remove admin1</code>"
        )
        return ConversationHandler.END
    
    try:
        from utils.read_config import save_config_value, invalidate_config_cache
        
        admin_username = context.args[0].strip()
        
        config_data = await read_config()
        filter_config = config_data.get("admin_filter", {})
        current_admins = filter_config.get("admin_usernames", [])
        
        if admin_username not in current_admins:
            await _send_response(
                update,
                f"ℹ️ Admin <code>{admin_username}</code> is not in the filter."
            )
            return ConversationHandler.END
        
        current_admins.remove(admin_username)
        await save_config_value("admin_filter_usernames", ",".join(current_admins))
        await invalidate_config_cache()
        
        await _send_response(
            update,
            f"✅ Removed admin <code>{admin_username}</code> from filter.\n"
            f"Remaining admins: <code>{current_admins}</code>"
        )
        
    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END
