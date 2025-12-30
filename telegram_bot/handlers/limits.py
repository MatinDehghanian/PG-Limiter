"""
Limit management handlers for the Telegram bot.
Includes functions for setting special limits, general limits, and viewing limits.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from telegram_bot.constants import (
    GET_SPECIAL_LIMIT,
    GET_LIMIT_NUMBER,
    GET_GENERAL_LIMIT_NUMBER,
    CallbackData,
)
from telegram_bot.utils import (
    check_admin,
    add_admin_to_config,
    get_special_limit_list,
    get_special_limits_dict,
    handel_special_limit,
    save_general_limit,
)
from telegram_bot.keyboards import (
    create_back_to_main_keyboard,
    create_special_limit_options_keyboard,
    create_general_limit_keyboard,
    create_limits_menu_keyboard,
)
from telegram_bot.handlers.admin import check_admin_privilege
from utils.read_config import read_config


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS (for /command style usage)
# ═══════════════════════════════════════════════════════════════════════════════


async def set_special_limit(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """
    Set a special limit for a user (command handler).
    This starts the conversation flow for setting a special limit.
    """
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    await update.message.reply_html(
        text="Please send the username. For example: <code>Test_User</code>"
    )
    return GET_SPECIAL_LIMIT


async def get_special_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Get the username for special limit setting (conversation step).
    """
    context.user_data["selected_user"] = update.message.text.strip()
    await update.message.reply_html(
        text="Please send the Number of limit. For example: <code>4</code> or <code>2</code>"
    )
    return GET_LIMIT_NUMBER


async def get_limit_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sets the special limit for a user if the provided input is a valid number.
    """
    try:
        context.user_data["limit_number"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_html(
            text=f"Wrong input: <code>{update.message.text.strip()}"
            + "</code>\ntry again <b>/set_special_limit</b>"
        )
        return ConversationHandler.END
    out_put = await handel_special_limit(
        context.user_data["selected_user"], context.user_data["limit_number"]
    )
    if out_put[0]:
        await update.message.reply_html(
            text=f"<code>{context.user_data['selected_user']}</code> already has a"
            + " special limit. Change it with new value"
        )
    await update.message.reply_html(
        text=f"Special limit for <code>{context.user_data['selected_user']}</code>"
        + f" set to <code>{out_put[1]}</code> successfully!"
    )
    return ConversationHandler.END


async def show_special_limit_function(
    update: Update, _context: ContextTypes.DEFAULT_TYPE
):
    """Show special limit list for all users (command handler)."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    
    special_limits = await get_special_limits_dict()
    
    if special_limits:
        total = len(special_limits)
        text = f"📋 <b>Special Limits</b> ({total} user{'s' if total != 1 else ''})\n\n"
        text += "Click on a user to view details or use Edit to change the limit."
        keyboard = create_special_limits_keyboard(special_limits, page=0)
    else:
        text = "📋 <b>Special Limits</b>\n\nNo special limits found!"
        keyboard = create_back_to_main_keyboard()
    
    await update.message.reply_html(text=text, reply_markup=keyboard)
    return ConversationHandler.END


async def get_general_limit_number(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Get the general limit number for the bot (command handler)."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    await update.message.reply_text("Please send the general limit number:")
    return GET_GENERAL_LIMIT_NUMBER


async def get_general_limit_number_handler(
    update: Update, _context: ContextTypes.DEFAULT_TYPE
):
    """Write the general limit number to the config file (conversation step)."""
    try:
        limit_number = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_html(
            text=f"Wrong input: <code>{update.message.text.strip()}"
            + "</code>\ntry again <b>/set_general_limit_number</b>"
        )
        return ConversationHandler.END
    await save_general_limit(limit_number)
    await update.message.reply_text(f"General limit set to {limit_number}")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACK QUERY HANDLERS (for inline keyboard usage)
# ═══════════════════════════════════════════════════════════════════════════════


async def handle_limits_menu_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for limits menu display."""
    await query.edit_message_text(
        text="🎯 <b>Limits Menu</b>\n\nManage user connection limits:",
        reply_markup=create_limits_menu_keyboard(),
        parse_mode="HTML"
    )


async def handle_set_special_limit_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for initiating special limit setting."""
    context.user_data["waiting_for"] = "special_limit_username"
    await query.edit_message_text(
        text="🎯 <b>Set Special Limit</b>\n\nSend the username (e.g., <code>Test_User</code>):",
        parse_mode="HTML"
    )


async def handle_special_limit_1_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for setting special limit to 1 device."""
    if "selected_user" in context.user_data:
        username = context.user_data["selected_user"]
        out_put = await handel_special_limit(username, 1)
        msg = f"✅ Special limit for <b>{username}</b> set to <b>1 device</b>"
        if out_put[0]:
            msg = f"✅ Updated <b>{username}</b> limit to <b>1 device</b>"
        await query.edit_message_text(
            text=msg,
            reply_markup=create_back_to_main_keyboard(),
            parse_mode="HTML"
        )
        context.user_data.pop("selected_user", None)


async def handle_special_limit_2_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for setting special limit to 2 devices."""
    if "selected_user" in context.user_data:
        username = context.user_data["selected_user"]
        out_put = await handel_special_limit(username, 2)
        msg = f"✅ Special limit for <b>{username}</b> set to <b>2 devices</b>"
        if out_put[0]:
            msg = f"✅ Updated <b>{username}</b> limit to <b>2 devices</b>"
        await query.edit_message_text(
            text=msg,
            reply_markup=create_back_to_main_keyboard(),
            parse_mode="HTML"
        )
        context.user_data.pop("selected_user", None)


async def handle_special_limit_custom_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for setting a custom special limit."""
    context.user_data["waiting_for"] = "special_limit_number"
    await query.edit_message_text(
        text=f"🎯 <b>Custom Limit for {context.user_data.get('selected_user', 'user')}</b>\n\n"
             + "Send the limit number (e.g., <code>5</code>):",
        parse_mode="HTML"
    )


def create_special_limits_keyboard(special_limits: dict, page: int = 0, per_page: int = 5):
    """
    Create a keyboard with special limits as glass-style buttons.
    Each user gets an edit button.
    
    Args:
        special_limits: Dict of username -> limit
        page: Current page number (0-indexed)
        per_page: Number of users per page
    """
    keyboard = []
    users_list = list(special_limits.items())
    total_users = len(users_list)
    total_pages = max(1, (total_users + per_page - 1) // per_page)
    
    # Get current page users
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total_users)
    page_users = users_list[start_idx:end_idx]
    
    # Add user buttons with glass-style appearance
    for username, limit in page_users:
        # Glass-style button with user info and edit action
        keyboard.append([
            InlineKeyboardButton(
                f"👤 {username} | Limit: {limit}",
                callback_data=f"special_limit_info:{username}"
            ),
            InlineKeyboardButton(
                "✏️ Edit",
                callback_data=f"edit_special_limit:{username}"
            )
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"special_limits_page:{page-1}"))
    
    # Page indicator
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"special_limits_page:{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Refresh and back buttons
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data=CallbackData.SHOW_SPECIAL_LIMIT),
    ])
    keyboard.append([
        InlineKeyboardButton("« Back to Limits", callback_data=CallbackData.LIMITS_MENU),
    ])
    
    return InlineKeyboardMarkup(keyboard)


async def handle_show_special_limit_callback(query, _context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Handle callback for showing all special limits with pagination."""
    special_limits = await get_special_limits_dict()
    
    if special_limits:
        total = len(special_limits)
        text = f"📋 <b>Special Limits</b> ({total} user{'s' if total != 1 else ''})\n\n"
        text += "Click on a user to view details or use Edit to change the limit."
        keyboard = create_special_limits_keyboard(special_limits, page=page)
    else:
        text = "📋 <b>Special Limits</b>\n\nNo special limits found!"
        keyboard = create_back_to_main_keyboard()
    
    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def handle_special_limits_page_callback(query, _context: ContextTypes.DEFAULT_TYPE, page: int):
    """Handle callback for special limits pagination."""
    await handle_show_special_limit_callback(query, _context, page=page)


async def handle_edit_special_limit_callback(query, context: ContextTypes.DEFAULT_TYPE, username: str):
    """Handle callback for editing a special limit."""
    context.user_data["selected_user"] = username
    await query.edit_message_text(
        text=f"🎯 <b>Edit Limit for {username}</b>\n\nSelect a new limit:",
        reply_markup=create_special_limit_options_keyboard(),
        parse_mode="HTML"
    )


async def handle_special_limit_info_callback(query, _context: ContextTypes.DEFAULT_TYPE, username: str):
    """Handle callback for showing special limit info for a user."""
    special_limits = await get_special_limits_dict()
    limit = special_limits.get(username, "N/A")
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Edit Limit", callback_data=f"edit_special_limit:{username}"),
            InlineKeyboardButton("🗑️ Remove", callback_data=f"remove_special_limit:{username}")
        ],
        [InlineKeyboardButton("« Back to List", callback_data=CallbackData.SHOW_SPECIAL_LIMIT)]
    ])
    
    await query.edit_message_text(
        text=f"👤 <b>User:</b> <code>{username}</code>\n"
             f"🎯 <b>Special Limit:</b> {limit} device{'s' if limit != 1 else ''}\n\n"
             f"Use the buttons below to edit or remove this limit.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def handle_remove_special_limit_callback(query, _context: ContextTypes.DEFAULT_TYPE, username: str):
    """Handle callback for removing a special limit."""
    from db.database import get_db, DB_AVAILABLE
    from db.crud import UserLimitCRUD
    
    if DB_AVAILABLE:
        async with get_db() as db:
            deleted = await UserLimitCRUD.delete(db, username)
            if deleted:
                text = f"✅ Special limit for <b>{username}</b> removed!\n\nThis user will now use the general limit."
            else:
                text = f"❌ No special limit found for <b>{username}</b>."
    else:
        text = "❌ Database not available."
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back to List", callback_data=CallbackData.SHOW_SPECIAL_LIMIT)]
        ]),
        parse_mode="HTML"
    )


async def handle_general_limit_menu_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for general limit menu display."""
    try:
        config = await read_config()
        current = config.get("limits", {}).get("general", 2)
    except Exception:
        current = 2
    await query.edit_message_text(
        text=f"🔢 <b>General Limit</b>\n\nCurrent: <b>{current}</b>\n\nSelect new limit:",
        reply_markup=create_general_limit_keyboard(),
        parse_mode="HTML"
    )


async def handle_general_limit_preset_callback(query, _context: ContextTypes.DEFAULT_TYPE, limit: int):
    """Handle callback for setting a preset general limit (2, 3, or 4)."""
    await save_general_limit(limit)
    await query.edit_message_text(
        text=f"✅ General limit set to <b>{limit}</b>",
        reply_markup=create_back_to_main_keyboard(),
        parse_mode="HTML"
    )


async def handle_general_limit_custom_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for initiating custom general limit setting."""
    context.user_data["waiting_for"] = "general_limit"
    await query.edit_message_text(
        text="🔢 <b>Custom General Limit</b>\n\nSend the limit number (e.g., <code>5</code>):",
        parse_mode="HTML"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT MESSAGE HANDLERS (for inline keyboard input flows)
# ═══════════════════════════════════════════════════════════════════════════════


async def handle_special_limit_username_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle text input for special limit username.
    Called from the main text_message_handler when waiting_for == "special_limit_username".
    """
    text = update.message.text.strip()
    context.user_data["selected_user"] = text
    context.user_data["waiting_for"] = None
    await update.message.reply_html(
        text=f"🎯 <b>Set limit for: {text}</b>\n\nChoose the device limit:",
        reply_markup=create_special_limit_options_keyboard()
    )


async def handle_special_limit_number_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle text input for special limit number.
    Called from the main text_message_handler when waiting_for == "special_limit_number".
    """
    text = update.message.text.strip()
    try:
        limit = int(text)
        username = context.user_data.get("selected_user", "user")
        out_put = await handel_special_limit(username, limit)
        msg = f"✅ Special limit for <b>{username}</b> set to <b>{limit}</b>"
        if out_put[0]:
            msg = f"✅ Updated <b>{username}</b> limit to <b>{limit}</b>"
        await update.message.reply_html(
            text=msg,
            reply_markup=create_back_to_main_keyboard()
        )
        context.user_data.pop("selected_user", None)
        context.user_data["waiting_for"] = None
    except ValueError:
        await update.message.reply_html(
            text="❌ Invalid number. Please send a valid number.",
            reply_markup=create_back_to_main_keyboard()
        )
        context.user_data["waiting_for"] = None


async def handle_general_limit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle text input for general limit number.
    Called from the main text_message_handler when waiting_for == "general_limit".
    """
    text = update.message.text.strip()
    try:
        limit = int(text)
        await save_general_limit(limit)
        await update.message.reply_html(
            text=f"✅ General limit set to <b>{limit}</b>",
            reply_markup=create_back_to_main_keyboard()
        )
    except ValueError:
        await update.message.reply_html(
            text="❌ Invalid number.",
            reply_markup=create_back_to_main_keyboard()
        )
    context.user_data["waiting_for"] = None
