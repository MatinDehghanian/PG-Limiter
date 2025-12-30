"""
Group filter handlers for the Telegram bot.
Includes functions for managing group-based user filtering.
"""

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from telegram_bot.handlers.admin import check_admin_privilege
from telegram_bot.utils import write_json_file
from telegram_bot.keyboards import create_back_to_main_keyboard
from utils.read_config import read_config


async def _send_response(update: Update, text: str, reply_markup=None):
    """
    Helper to send response in both message and callback query contexts.
    """
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_html(
            text=text,
            reply_markup=reply_markup
        )
    elif update.message:
        await update.message.reply_html(
            text=text,
            reply_markup=reply_markup
        )


async def group_filter_status(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Show the current group filter configuration."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        from utils.user_group_filter import get_filter_status_text, get_all_groups
        from utils.types import PanelType
        
        config_data = await read_config()
        
        # Get panel data for group lookup
        panel_config = config_data.get("panel", {})
        panel_data = PanelType(
            panel_config.get("username", ""),
            panel_config.get("password", ""),
            panel_config.get("domain", "")
        )
        
        # Get all groups for name lookup
        groups = await get_all_groups(panel_data)
        
        # Get filter status
        status_text = get_filter_status_text(config_data, groups)
        
        # Build groups list
        groups_list = []
        for group in groups:
            gid = group.get("id", "?")
            name = group.get("name", "Unknown")
            groups_list.append(f"  • <code>{gid}</code> - {name}")
        
        groups_display = "\n".join(groups_list) if groups_list else "  No groups found"
        
        message = (
            f"🔍 <b>Group Filter Status</b>\n\n"
            f"{status_text}\n\n"
            f"<b>Available Groups:</b>\n{groups_display}\n\n"
            f"<b>Commands:</b>\n"
            f"/group_filter_toggle - Enable/disable\n"
            f"/group_filter_mode - Set include/exclude\n"
            f"/group_filter_set - Set groups\n"
            f"/group_filter_add - Add group\n"
            f"/group_filter_remove - Remove group"
        )
        
        await _send_response(update, message, create_back_to_main_keyboard())
        
    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def group_filter_toggle(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Toggle group filter on/off."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        config_data = await read_config()
        
        if "group_filter" not in config_data:
            config_data["group_filter"] = {"enabled": True, "mode": "include", "group_ids": []}
        
        current_state = config_data["group_filter"].get("enabled", False)
        config_data["group_filter"]["enabled"] = not current_state
        
        await write_json_file(config_data)
        
        new_state = "✅ Enabled" if not current_state else "❌ Disabled"
        await _send_response(
            update,
            f"🔍 Group filter is now: {new_state}",
            create_back_to_main_keyboard()
        )
        
    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def group_filter_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set group filter mode (include/exclude)."""
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
            config_data = await read_config()
            
            if "group_filter" not in config_data:
                config_data["group_filter"] = {"enabled": False, "mode": mode, "group_ids": []}
            else:
                config_data["group_filter"]["mode"] = mode
            
            await write_json_file(config_data)
            
            if mode == "include":
                desc = "Only users in specified groups will be monitored"
            else:
                desc = "Users in specified groups will be whitelisted"
            
            await _send_response(
                update,
                f"✅ Group filter mode set to: <code>{mode}</code>\n{desc}",
                create_back_to_main_keyboard()
            )
            
        except Exception as e:
            await _send_response(update, f"❌ Error: {str(e)}")
        
        return ConversationHandler.END
    
    await _send_response(
        update,
        "🔍 <b>Set Group Filter Mode</b>\n\n"
        "<code>/group_filter_mode include</code>\n"
        "  → Only users in specified groups are monitored\n\n"
        "<code>/group_filter_mode exclude</code>\n"
        "  → Users in specified groups are whitelisted (not limited)"
    )
    return ConversationHandler.END


async def group_filter_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the list of group IDs for filtering."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    if context.args:
        try:
            # Parse group IDs from arguments
            group_ids = []
            for arg in context.args:
                # Support comma-separated and space-separated
                for gid in arg.split(","):
                    gid = gid.strip()
                    if gid:
                        group_ids.append(int(gid))
            
            config_data = await read_config()
            
            if "group_filter" not in config_data:
                config_data["group_filter"] = {"enabled": False, "mode": "include", "group_ids": group_ids}
            else:
                config_data["group_filter"]["group_ids"] = group_ids
            
            await write_json_file(config_data)
            
            await _send_response(
                update,
                f"✅ Group filter set to IDs: <code>{group_ids}</code>"
            )
            
        except ValueError:
            await _send_response(
                update,
                "❌ Invalid group ID. Please provide numeric IDs."
            )
        except Exception as e:
            await _send_response(update, f"❌ Error: {str(e)}")
        
        return ConversationHandler.END
    
    await _send_response(
        update,
        "🔍 <b>Set Group Filter Groups</b>\n\n"
        "Usage: <code>/group_filter_set 1 2 3</code>\n"
        "Or: <code>/group_filter_set 1,2,3</code>\n\n"
        "Use /group_filter_status to see available groups."
    )
    return ConversationHandler.END


async def group_filter_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a group ID to the filter."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    if not context.args:
        await _send_response(
            update,
            "❌ Please provide a group ID.\n"
            "Example: <code>/group_filter_add 5</code>"
        )
        return ConversationHandler.END
    
    try:
        group_id = int(context.args[0])
        
        config_data = await read_config()
        
        if "group_filter" not in config_data:
            config_data["group_filter"] = {"enabled": False, "mode": "include", "group_ids": [group_id]}
        else:
            current_ids = config_data["group_filter"].get("group_ids", [])
            if group_id not in current_ids:
                current_ids.append(group_id)
                config_data["group_filter"]["group_ids"] = current_ids
            else:
                await _send_response(
                    update,
                    f"ℹ️ Group ID <code>{group_id}</code> is already in the filter."
                )
                return ConversationHandler.END
        
        await write_json_file(config_data)
        
        await _send_response(
            update,
            f"✅ Added group ID <code>{group_id}</code> to filter.\n"
            f"Current groups: <code>{config_data['group_filter']['group_ids']}</code>"
        )
        
    except ValueError:
        await _send_response(update, "❌ Invalid group ID. Please provide a number.")
    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def group_filter_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a group ID from the filter."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    if not context.args:
        await _send_response(
            update,
            "❌ Please provide a group ID.\n"
            "Example: <code>/group_filter_remove 5</code>"
        )
        return ConversationHandler.END
    
    try:
        group_id = int(context.args[0])
        
        config_data = await read_config()
        
        if "group_filter" not in config_data:
            await _send_response(
                update,
                "❌ No group filter configured."
            )
            return ConversationHandler.END
        
        current_ids = config_data["group_filter"].get("group_ids", [])
        if group_id in current_ids:
            current_ids.remove(group_id)
            config_data["group_filter"]["group_ids"] = current_ids
            await write_json_file(config_data)
            
            await _send_response(
                update,
                f"✅ Removed group ID <code>{group_id}</code> from filter.\n"
                f"Remaining groups: <code>{current_ids}</code>"
            )
        else:
            await _send_response(
                update,
                f"ℹ️ Group ID <code>{group_id}</code> is not in the filter."
            )
        
    except ValueError:
        await _send_response(update, "❌ Invalid group ID. Please provide a number.")
    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END
