"""
Group filter handlers for the Telegram bot.
Includes functions for managing group-based user filtering.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from telegram_bot.handlers.admin import check_admin_privilege
from telegram_bot.utils import write_json_file
from telegram_bot.keyboards import create_back_to_main_keyboard
from telegram_bot.constants import CallbackData
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


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACK HANDLERS FOR GLASS BUTTON UI
# ═══════════════════════════════════════════════════════════════════════════════


async def _get_groups_from_panel():
    """Helper to get groups from panel."""
    try:
        from utils.user_group_filter import get_all_groups
        from utils.types import PanelType
        
        config_data = await read_config()
        panel_config = config_data.get("panel", {})
        panel_data = PanelType(
            panel_config.get("username", ""),
            panel_config.get("password", ""),
            panel_config.get("domain", "")
        )
        
        groups = await get_all_groups(panel_data)
        return groups, config_data
    except Exception as e:
        return [], {}


def create_group_filter_keyboard(config_data: dict, groups: list):
    """Create keyboard for group filter with mode and group selection."""
    filter_config = config_data.get("group_filter", {})
    enabled = filter_config.get("enabled", False)
    mode = filter_config.get("mode", "include")
    selected_ids = filter_config.get("group_ids", [])
    
    keyboard = []
    
    # Enable/Disable toggle
    toggle_text = "🔴 Disable Filter" if enabled else "🟢 Enable Filter"
    keyboard.append([InlineKeyboardButton(toggle_text, callback_data=CallbackData.GROUP_FILTER_TOGGLE)])
    
    # Mode selection
    include_text = "✅ Include" if mode == "include" else "⬜ Include"
    exclude_text = "✅ Exclude" if mode == "exclude" else "⬜ Exclude"
    keyboard.append([
        InlineKeyboardButton(include_text, callback_data=CallbackData.GROUP_FILTER_MODE_INCLUDE),
        InlineKeyboardButton(exclude_text, callback_data=CallbackData.GROUP_FILTER_MODE_EXCLUDE),
    ])
    
    # Mode description
    if mode == "include":
        mode_desc = "Only users in selected groups will be monitored"
    else:
        mode_desc = "Users in selected groups will be whitelisted"
    
    # Group selection buttons
    for group in groups:
        gid = group.get("id", 0)
        name = group.get("name", "Unknown")
        is_selected = gid in selected_ids
        prefix = "✅" if is_selected else "⬜"
        keyboard.append([
            InlineKeyboardButton(
                f"{prefix} {name} (ID: {gid})",
                callback_data=f"gf_toggle_group:{gid}"
            )
        ])
    
    # Back button
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data=CallbackData.GROUP_FILTER_MENU)])
    keyboard.append([InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)])
    
    return InlineKeyboardMarkup(keyboard), mode_desc


async def handle_group_filter_menu_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for group filter menu with glass buttons."""
    groups, config_data = await _get_groups_from_panel()
    
    if not groups:
        await query.edit_message_text(
            text="🔍 <b>Group Filter</b>\n\n"
                 "❌ Could not load groups from panel.\n"
                 "Please check your panel connection.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Retry", callback_data=CallbackData.GROUP_FILTER_MENU)],
                [InlineKeyboardButton("« Back", callback_data=CallbackData.SETTINGS_MENU)]
            ]),
            parse_mode="HTML"
        )
        return
    
    keyboard, mode_desc = create_group_filter_keyboard(config_data, groups)
    filter_config = config_data.get("group_filter", {})
    enabled = filter_config.get("enabled", False)
    status = "✅ Enabled" if enabled else "❌ Disabled"
    
    await query.edit_message_text(
        text=f"🔍 <b>Group Filter</b>\n\n"
             f"<b>Status:</b> {status}\n"
             f"<b>Mode:</b> {mode_desc}\n\n"
             f"Select groups to include/exclude:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def handle_group_filter_toggle_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle toggle callback for group filter."""
    try:
        config_data = await read_config()
        
        if "group_filter" not in config_data:
            config_data["group_filter"] = {"enabled": True, "mode": "include", "group_ids": []}
        else:
            config_data["group_filter"]["enabled"] = not config_data["group_filter"].get("enabled", False)
        
        await write_json_file(config_data)
        
        # Refresh the menu
        await handle_group_filter_menu_callback(query, _context)
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=CallbackData.GROUP_FILTER_MENU)]
            ]),
            parse_mode="HTML"
        )


async def handle_group_filter_mode_callback(query, _context: ContextTypes.DEFAULT_TYPE, mode: str):
    """Handle mode selection callback for group filter."""
    try:
        config_data = await read_config()
        
        if "group_filter" not in config_data:
            config_data["group_filter"] = {"enabled": False, "mode": mode, "group_ids": []}
        else:
            config_data["group_filter"]["mode"] = mode
        
        await write_json_file(config_data)
        
        # Refresh the menu
        await handle_group_filter_menu_callback(query, _context)
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=CallbackData.GROUP_FILTER_MENU)]
            ]),
            parse_mode="HTML"
        )


async def handle_group_filter_toggle_group_callback(query, _context: ContextTypes.DEFAULT_TYPE, group_id: int):
    """Handle group toggle callback for group filter."""
    try:
        config_data = await read_config()
        
        if "group_filter" not in config_data:
            config_data["group_filter"] = {"enabled": False, "mode": "include", "group_ids": [group_id]}
        else:
            current_ids = config_data["group_filter"].get("group_ids", [])
            if group_id in current_ids:
                current_ids.remove(group_id)
            else:
                current_ids.append(group_id)
            config_data["group_filter"]["group_ids"] = current_ids
        
        await write_json_file(config_data)
        
        # Refresh the menu
        await handle_group_filter_menu_callback(query, _context)
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=CallbackData.GROUP_FILTER_MENU)]
            ]),
            parse_mode="HTML"
        )
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
