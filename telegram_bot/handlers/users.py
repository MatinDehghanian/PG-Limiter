"""
User management handlers for the Telegram bot.
Includes functions for except users, disabled users management, and cleanup.
"""

import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from telegram_bot.constants import (
    SET_EXCEPT_USERS,
    REMOVE_EXCEPT_USER,
    CallbackData,
)
from telegram_bot.utils import (
    add_except_user,
    remove_except_user_from_config,
    show_except_users_handler,
    get_except_users_list,
)
from telegram_bot.handlers.admin import check_admin_privilege
from telegram_bot.keyboards import (
    create_back_to_main_keyboard,
    create_users_menu_keyboard,
)
from utils.read_config import read_config


def create_back_to_users_keyboard():
    """Create a simple back to users menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("« Back to Users", callback_data=CallbackData.BACK_USERS)],
        [InlineKeyboardButton("« Back to Main Menu", callback_data=CallbackData.MAIN_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_whitelist_keyboard(whitelist_users: list, page: int = 0, per_page: int = 5):
    """
    Create a keyboard with whitelist users as glass-style buttons.
    Each user gets a delete button.
    
    Args:
        whitelist_users: List of usernames in the whitelist
        page: Current page number (0-indexed)
        per_page: Number of users per page
    """
    keyboard = []
    total_users = len(whitelist_users)
    total_pages = max(1, (total_users + per_page - 1) // per_page)
    
    # Get current page users
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total_users)
    page_users = whitelist_users[start_idx:end_idx]
    
    # Add user buttons with glass-style appearance
    for username in page_users:
        keyboard.append([
            InlineKeyboardButton(
                f"✅ {username}",
                callback_data=f"whitelist_info:{username}"
            ),
            InlineKeyboardButton(
                "🗑️ Delete",
                callback_data=f"delete_whitelist:{username}"
            )
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"whitelist_page:{page-1}"))
    
    # Page indicator
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"whitelist_page:{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Add user button
    keyboard.append([
        InlineKeyboardButton("➕ Add User", callback_data=CallbackData.SET_EXCEPT_USER),
    ])
    
    # Refresh and back buttons
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data=CallbackData.SHOW_EXCEPT_USERS),
    ])
    keyboard.append([
        InlineKeyboardButton("« Back to Users", callback_data=CallbackData.BACK_USERS),
    ])
    
    return InlineKeyboardMarkup(keyboard)


def create_disabled_users_keyboard(disabled_users: dict, page: int = 0, per_page: int = 5):
    """
    Create a keyboard with disabled users as glass-style buttons.
    Each user gets an enable button.
    
    Args:
        disabled_users: Dict of username -> disabled_timestamp
        page: Current page number (0-indexed)
        per_page: Number of users per page
    """
    keyboard = []
    users_list = list(disabled_users.items())
    total_users = len(users_list)
    total_pages = max(1, (total_users + per_page - 1) // per_page)
    
    # Get current page users
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total_users)
    page_users = users_list[start_idx:end_idx]
    
    current_time = time.time()
    
    # Add user buttons with glass-style appearance
    for username, disabled_time in page_users:
        elapsed = int(current_time - disabled_time)
        minutes = elapsed // 60
        if minutes >= 60:
            hours = minutes // 60
            time_str = f"{hours}h ago"
        else:
            time_str = f"{minutes}m ago"
        
        # Glass-style button with user info and enable action
        keyboard.append([
            InlineKeyboardButton(
                f"🔴 {username} ({time_str})",
                callback_data=f"user_info:{username}"
            ),
            InlineKeyboardButton(
                "✅ Enable",
                callback_data=f"enable_user:{username}"
            )
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"disabled_page:{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"disabled_page:{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Enable all button (only show if there are disabled users)
    if total_users > 0:
        keyboard.append([
            InlineKeyboardButton(
                f"✅ Enable All ({total_users} users)",
                callback_data=CallbackData.ENABLE_ALL_DISABLED
            )
        ])
    
    # Refresh and back buttons
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data=CallbackData.SHOW_DISABLED_USERS),
    ])
    keyboard.append([
        InlineKeyboardButton("« Back to Users", callback_data=CallbackData.BACK_USERS),
    ])
    
    return InlineKeyboardMarkup(keyboard)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS (for /command style usage)
# ═══════════════════════════════════════════════════════════════════════════════


async def set_except_users(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Set the except users for the bot."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    await update.message.reply_html(
        "Send the except (<code>users in this list have no limitation</code>) user:"
    )
    return SET_EXCEPT_USERS


async def set_except_users_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Write the except users to the config file."""
    except_user = update.message.text.strip()
    await add_except_user(except_user)
    await update.message.reply_html(
        f"Except user <code>{except_user}</code> added successfully!"
    )
    return ConversationHandler.END


async def remove_except_user(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Remove the except users for the bot."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    await update.message.reply_html("Send the except user to remove:")
    return REMOVE_EXCEPT_USER


async def remove_except_user_handler(
    update: Update, _context: ContextTypes.DEFAULT_TYPE
):
    """Remove the except users from the config file."""
    except_user = await remove_except_user_from_config(update.message.text.strip())
    if except_user:
        await update.message.reply_html(
            f"Except user <code>{except_user}</code> removed successfully!"
        )
    else:
        await update.message.reply_html(
            f"Except user <code>{update.message.text.strip()}</code> not found!"
        )
    return ConversationHandler.END


async def show_except_users(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Show the except users for the bot with paginated keyboard."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    
    whitelist_users = await get_except_users_list()
    
    if whitelist_users:
        total = len(whitelist_users)
        text = f"✅ <b>Whitelist (Except Users)</b> ({total} user{'s' if total != 1 else ''})\n\n"
        text += "These users are exempt from IP limits.\nClick to view details or use Delete to remove."
        keyboard = create_whitelist_keyboard(whitelist_users, page=0)
    else:
        text = "✅ <b>Whitelist (Except Users)</b>\n\nNo users in the whitelist."
        keyboard = create_back_to_users_keyboard()
    
    await update.message.reply_html(text=text, reply_markup=keyboard)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
# DISABLED USERS HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════


async def show_disabled_users_menu(query, page: int = 0):
    """Display the disabled users menu with enable buttons."""
    from utils.handel_dis_users import DisabledUsers
    
    try:
        # Load disabled users
        dis_users = DisabledUsers()
        disabled_dict = dis_users.disabled_users
        
        if not disabled_dict:
            text = (
                "🚫 <b>Disabled Users</b>\n\n"
                "✅ No users are currently disabled by the limiter.\n\n"
                "Users get disabled when they exceed their IP limit."
            )
            keyboard = create_back_to_users_keyboard()
        else:
            # Get time to active for info
            try:
                config = await read_config()
                time_to_active = config.get("timing", {}).get("time_to_active_users", 300)
            except Exception:
                time_to_active = 300
            
            total_users = len(disabled_dict)
            text = (
                f"🚫 <b>Disabled Users</b>\n\n"
                f"📊 Total: <b>{total_users}</b> users disabled by limiter\n"
                f"⏱️ Auto-enable after: <b>{time_to_active // 60}</b> minutes\n\n"
                f"<i>Click the ✅ button to manually enable a user:</i>"
            )
            keyboard = create_disabled_users_keyboard(disabled_dict, page=page)
        
        await query.edit_message_text(
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error loading disabled users: {e}",
            reply_markup=create_back_to_users_keyboard(),
            parse_mode="HTML"
        )


async def enable_single_user(query, username: str):
    """Enable a single disabled user."""
    from utils.handel_dis_users import DisabledUsers
    from utils.panel_api import enable_selected_users
    from utils.types import PanelType
    
    try:
        # Load config for panel data
        config = await read_config()
        panel_config = config.get("panel", {})
        panel_data = PanelType(
            panel_username=panel_config.get("username", ""),
            panel_password=panel_config.get("password", ""),
            panel_domain=panel_config.get("domain", "")
        )
        
        # Enable user on panel
        await enable_selected_users(panel_data, {username})
        
        # Remove from disabled users list
        dis_users = DisabledUsers()
        await dis_users.remove_user(username)
        
        # Show updated list
        await query.answer(f"✅ User {username} enabled!")
        await show_disabled_users_menu(query)
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error enabling user {username}: {e}",
            reply_markup=create_back_to_users_keyboard(),
            parse_mode="HTML"
        )


async def enable_all_disabled_users(query):
    """Enable all disabled users."""
    from utils.handel_dis_users import DisabledUsers
    from utils.panel_api import enable_selected_users
    from utils.types import PanelType
    
    try:
        # Load disabled users
        dis_users = DisabledUsers()
        disabled_dict = dis_users.disabled_users.copy()
        
        if not disabled_dict:
            await query.answer("No disabled users to enable!")
            return
        
        usernames = set(disabled_dict.keys())
        count = len(usernames)
        
        await query.edit_message_text(
            text=f"⏳ Enabling {count} users...",
            parse_mode="HTML"
        )
        
        # Load config for panel data
        config = await read_config()
        panel_config = config.get("panel", {})
        panel_data = PanelType(
            panel_username=panel_config.get("username", ""),
            panel_password=panel_config.get("password", ""),
            panel_domain=panel_config.get("domain", "")
        )
        
        # Enable all users on panel
        await enable_selected_users(panel_data, usernames)
        
        # Clear disabled users list
        await dis_users.read_and_clear_users()
        
        await query.edit_message_text(
            text=f"✅ <b>Successfully enabled {count} users!</b>\n\n"
                 f"All disabled users have been re-enabled on the panel.",
            reply_markup=create_back_to_users_keyboard(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error enabling users: {e}",
            reply_markup=create_back_to_users_keyboard(),
            parse_mode="HTML"
        )


async def show_user_info(query, username: str):
    """Show detailed info for a disabled user."""
    from utils.handel_dis_users import DisabledUsers
    
    dis_users = DisabledUsers()
    disabled_time = dis_users.disabled_users.get(username)
    
    if disabled_time:
        elapsed = int(time.time() - disabled_time)
        minutes = elapsed // 60
        seconds = elapsed % 60
        disabled_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(disabled_time))
        
        info_text = (
            f"ℹ️ <b>User Info: {username}</b>\n\n"
            f"🔴 <b>Status:</b> Disabled\n"
            f"📅 <b>Disabled at:</b> {disabled_at}\n"
            f"⏱️ <b>Elapsed:</b> {minutes}m {seconds}s\n\n"
            f"<i>Click Enable to re-activate this user.</i>"
        )
        
        keyboard = [
            [InlineKeyboardButton(f"✅ Enable {username}", callback_data=f"enable_user:{username}")],
            [InlineKeyboardButton("« Back to Disabled Users", callback_data=CallbackData.SHOW_DISABLED_USERS)],
        ]
        await query.edit_message_text(
            text=info_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    else:
        await query.answer(f"User {username} is no longer disabled!")
        await show_disabled_users_menu(query)


# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════


async def cleanup_deleted_users_handler(query):
    """Clean up users from limiter config that no longer exist in the panel."""
    from utils.panel_api import cleanup_deleted_users
    from utils.types import PanelType
    
    try:
        await query.edit_message_text(
            text="⏳ <b>Cleaning up deleted users...</b>\n\n"
                 "Fetching all users from panel and checking limiter config...",
            parse_mode="HTML"
        )
        
        # Load config for panel data
        config = await read_config()
        panel_config = config.get("panel", {})
        panel_data = PanelType(
            panel_username=panel_config.get("username", ""),
            panel_password=panel_config.get("password", ""),
            panel_domain=panel_config.get("domain", "")
        )
        
        # Perform cleanup
        result = await cleanup_deleted_users(panel_data)
        
        # Build result message
        total_removed = (
            len(result.get("special_limits_removed", [])) +
            len(result.get("except_users_removed", [])) +
            len(result.get("disabled_users_removed", [])) +
            len(result.get("user_groups_backup_removed", []))
        )
        
        if total_removed == 0:
            await query.edit_message_text(
                text="✅ <b>Cleanup Complete!</b>\n\n"
                     "No deleted users found in limiter config.\n"
                     "Everything is clean! 🎉",
                reply_markup=create_back_to_users_keyboard(),
                parse_mode="HTML"
            )
        else:
            message_parts = ["🧹 <b>Cleanup Complete!</b>\n"]
            
            special_limits = result.get("special_limits_removed", [])
            if special_limits:
                message_parts.append(
                    f"\n📊 <b>Special Limits:</b> Removed {len(special_limits)} users\n"
                    f"<code>{', '.join(special_limits[:10])}</code>"
                )
                if len(special_limits) > 10:
                    message_parts.append(f" and {len(special_limits) - 10} more...")
            
            except_users = result.get("except_users_removed", [])
            if except_users:
                message_parts.append(
                    f"\n📋 <b>Except Users:</b> Removed {len(except_users)} users\n"
                    f"<code>{', '.join(except_users[:10])}</code>"
                )
                if len(except_users) > 10:
                    message_parts.append(f" and {len(except_users) - 10} more...")
            
            disabled_users = result.get("disabled_users_removed", [])
            if disabled_users:
                message_parts.append(
                    f"\n🚫 <b>Disabled Users:</b> Removed {len(disabled_users)} users\n"
                    f"<code>{', '.join(disabled_users[:10])}</code>"
                )
                if len(disabled_users) > 10:
                    message_parts.append(f" and {len(disabled_users) - 10} more...")
            
            group_users = result.get("user_groups_backup_removed", [])
            if group_users:
                message_parts.append(
                    f"\n📁 <b>Groups Backup:</b> Removed {len(group_users)} users\n"
                    f"<code>{', '.join(group_users[:10])}</code>"
                )
                if len(group_users) > 10:
                    message_parts.append(f" and {len(group_users) - 10} more...")
            
            message_parts.append(f"\n\n<b>Total removed:</b> {total_removed} user entries")
            
            await query.edit_message_text(
                text="".join(message_parts),
                reply_markup=create_back_to_users_keyboard(),
                parse_mode="HTML"
            )
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ <b>Error during cleanup:</b>\n\n{e}",
            reply_markup=create_back_to_users_keyboard(),
            parse_mode="HTML"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACK QUERY HANDLERS (for inline keyboard usage)
# ═══════════════════════════════════════════════════════════════════════════════


async def handle_users_menu_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for users menu display."""
    await query.edit_message_text(
        text="👥 <b>Users Menu</b>\n\nManage users and view disabled accounts:",
        reply_markup=create_users_menu_keyboard(),
        parse_mode="HTML"
    )


async def handle_show_except_users_callback(query, _context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Handle callback for showing except users list (whitelist) with pagination."""
    whitelist_users = await get_except_users_list()
    
    if whitelist_users:
        total = len(whitelist_users)
        text = f"✅ <b>Whitelist (Except Users)</b> ({total} user{'s' if total != 1 else ''})\n\n"
        text += "These users are exempt from IP limits.\nClick to view details or use Delete to remove."
        keyboard = create_whitelist_keyboard(whitelist_users, page=page)
    else:
        text = "✅ <b>Whitelist (Except Users)</b>\n\nNo users in the whitelist."
        keyboard = create_back_to_users_keyboard()
    
    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def handle_whitelist_page_callback(query, _context: ContextTypes.DEFAULT_TYPE, page: int):
    """Handle callback for whitelist pagination."""
    await handle_show_except_users_callback(query, _context, page=page)


async def handle_whitelist_info_callback(query, _context: ContextTypes.DEFAULT_TYPE, username: str):
    """Handle callback for showing whitelist user info."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Delete from Whitelist", callback_data=f"delete_whitelist:{username}")
        ],
        [InlineKeyboardButton("« Back to List", callback_data=CallbackData.SHOW_EXCEPT_USERS)]
    ])
    
    await query.edit_message_text(
        text=f"👤 <b>User:</b> <code>{username}</code>\n\n"
             f"✅ <b>Status:</b> Whitelisted\n\n"
             f"This user is exempt from IP limits and will never be disabled by the limiter.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def handle_delete_whitelist_callback(query, _context: ContextTypes.DEFAULT_TYPE, username: str):
    """Handle callback for deleting a user from whitelist."""
    result = await remove_except_user_from_config(username)
    
    if result:
        text = f"✅ User <b>{username}</b> removed from whitelist!\n\nThis user will now be subject to IP limits."
    else:
        text = f"❌ User <b>{username}</b> not found in whitelist."
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back to List", callback_data=CallbackData.SHOW_EXCEPT_USERS)]
        ]),
        parse_mode="HTML"
    )


async def handle_add_except_user_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for initiating add except user."""
    context.user_data["waiting_for"] = "except_user"
    await query.edit_message_text(
        text="➕ <b>Add User to Whitelist</b>\n\n"
             "Send the username to add to the whitelist:\n\n"
             "<i>Example: <code>john_doe</code></i>",
        parse_mode="HTML"
    )


async def handle_remove_except_user_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for initiating remove except user."""
    context.user_data["waiting_for"] = "remove_except_user"
    await query.edit_message_text(
        text="➖ <b>Remove User from Whitelist</b>\n\n"
             "Send the username to remove from the whitelist:\n\n"
             "<i>Example: <code>john_doe</code></i>",
        parse_mode="HTML"
    )


async def handle_show_disabled_users_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for showing disabled users menu."""
    await show_disabled_users_menu(query)


async def handle_enable_all_disabled_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for enabling all disabled users."""
    await enable_all_disabled_users(query)


async def handle_cleanup_deleted_users_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for cleaning up deleted users."""
    await cleanup_deleted_users_handler(query)


async def handle_enable_user_callback(query, _context: ContextTypes.DEFAULT_TYPE, username: str):
    """Handle callback for enabling a single user."""
    await enable_single_user(query, username)


async def handle_disabled_page_callback(query, _context: ContextTypes.DEFAULT_TYPE, page: int):
    """Handle callback for disabled users pagination."""
    await show_disabled_users_menu(query, page=page)


async def handle_user_info_callback(query, _context: ContextTypes.DEFAULT_TYPE, username: str):
    """Handle callback for showing user info."""
    await show_user_info(query, username)


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT MESSAGE HANDLERS (for inline keyboard input flows)
# ═══════════════════════════════════════════════════════════════════════════════


async def handle_except_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle text input for adding except user.
    Called from the main text_message_handler when waiting_for == "except_user".
    """
    text = update.message.text.strip()
    await add_except_user(text)
    context.user_data["waiting_for"] = None
    await update.message.reply_html(
        text=f"✅ Except user <b>{text}</b> added successfully!",
        reply_markup=create_back_to_users_keyboard()
    )


async def handle_remove_except_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle text input for removing except user.
    Called from the main text_message_handler when waiting_for == "remove_except_user".
    """
    text = update.message.text.strip()
    result = await remove_except_user_from_config(text)
    context.user_data["waiting_for"] = None
    
    if result:
        await update.message.reply_html(
            text=f"✅ Except user <b>{text}</b> removed successfully!",
            reply_markup=create_back_to_users_keyboard()
        )
    else:
        await update.message.reply_html(
            text=f"❌ Except user <b>{text}</b> not found!",
            reply_markup=create_back_to_users_keyboard()
        )
