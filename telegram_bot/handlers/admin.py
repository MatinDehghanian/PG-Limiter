"""
Admin management handlers for the Telegram bot.
Includes functions for adding, removing, and listing admins.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from telegram_bot.utils import (
    add_admin_to_config,
    check_admin,
    remove_admin_from_config,
)
from telegram_bot.constants import (
    GET_CHAT_ID,
    GET_CHAT_ID_TO_REMOVE,
    CallbackData,
)


def create_admins_list_keyboard(admins: list, page: int = 0, per_page: int = 5):
    """
    Create a keyboard with admins as glass-style buttons.
    Each admin gets a delete button.
    
    Args:
        admins: List of admin chat IDs
        page: Current page number (0-indexed)
        per_page: Number of admins per page
    """
    keyboard = []
    total_admins = len(admins)
    total_pages = max(1, (total_admins + per_page - 1) // per_page)
    
    # Get current page admins
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total_admins)
    page_admins = admins[start_idx:end_idx]
    
    # Add admin buttons with glass-style appearance
    for admin_id in page_admins:
        keyboard.append([
            InlineKeyboardButton(
                f"👤 {admin_id}",
                callback_data=f"admin_info:{admin_id}"
            ),
            InlineKeyboardButton(
                "🗑️ Delete",
                callback_data=f"delete_admin:{admin_id}"
            )
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admins_page:{page-1}"))
    
    # Page indicator
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"admins_page:{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Add admin button
    keyboard.append([
        InlineKeyboardButton("➕ Add Admin", callback_data=CallbackData.ADD_ADMIN),
    ])
    
    # Refresh and back buttons
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data=CallbackData.LIST_ADMINS),
    ])
    keyboard.append([
        InlineKeyboardButton("« Back to Admin Menu", callback_data=CallbackData.ADMIN_MENU),
    ])
    
    return InlineKeyboardMarkup(keyboard)


def create_back_to_admins_keyboard():
    """Create a simple back to admins list keyboard."""
    keyboard = [
        [InlineKeyboardButton("« Back to Admins", callback_data=CallbackData.LIST_ADMINS)],
        [InlineKeyboardButton("« Back to Main Menu", callback_data=CallbackData.MAIN_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


async def _send_response(update: Update, text: str):
    """
    Helper to send response in both message and callback query contexts.
    """
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_html(text=text)
    elif update.message:
        await update.message.reply_html(text=text)


async def check_admin_privilege(update: Update):
    """
    Checks if the user has admin privileges.
    Returns ConversationHandler.END if user is not admin, None otherwise.
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
    return None


async def add_admin(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """
    Adds an admin to the bot.
    At first checks if the user has admin privileges.
    """
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    if len(await check_admin()) > 5:
        await update.message.reply_html(
            text="You set more than '5' admins you need to delete one of them to add a new admin\n"
            + "check your active admins with /admins_list\n"
            + "you can delete with /remove_admin command"
        )
        return ConversationHandler.END
    await update.message.reply_html(text="Send chat id: ")
    return GET_CHAT_ID


async def get_chat_id(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """
    Adds a new admin if the provided chat ID is valid and not already an admin.
    """
    new_admin_id = update.message.text.strip()
    try:
        if await add_admin_to_config(new_admin_id):
            await update.message.reply_html(
                text=f"Admin <code>{new_admin_id}</code> added successfully!"
            )
        else:
            await update.message.reply_html(
                text=f"Admin <code>{new_admin_id}</code> already exists!"
            )
    except ValueError:
        await update.message.reply_html(
            text=f"Wrong input: <code>{update.message.text.strip()}"
            + "</code>\ntry again <b>/add_admin</b>"
        )
    return ConversationHandler.END


async def admins_list(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """
    Sends a list of current admins with glass-style buttons.
    """
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    
    admins = await check_admin()
    
    if admins:
        total = len(admins)
        text = f"👥 <b>Bot Admins</b> ({total} admin{'s' if total != 1 else ''})\n\n"
        text += "Click to view details or use Delete to remove."
        keyboard = create_admins_list_keyboard(admins, page=0)
    else:
        text = "👥 <b>Bot Admins</b>\n\nNo admins found!"
        keyboard = create_back_to_admins_keyboard()
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    elif update.message:
        await update.message.reply_html(text=text, reply_markup=keyboard)
    
    return ConversationHandler.END


async def handle_admins_list_callback(query, _context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Handle callback for showing admins list with pagination."""
    admins = await check_admin()
    
    if admins:
        total = len(admins)
        text = f"👥 <b>Bot Admins</b> ({total} admin{'s' if total != 1 else ''})\n\n"
        text += "Click to view details or use Delete to remove."
        keyboard = create_admins_list_keyboard(admins, page=page)
    else:
        text = "👥 <b>Bot Admins</b>\n\nNo admins found!"
        keyboard = create_back_to_admins_keyboard()
    
    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def handle_admins_page_callback(query, _context: ContextTypes.DEFAULT_TYPE, page: int):
    """Handle callback for admins list pagination."""
    await handle_admins_list_callback(query, _context, page=page)


async def handle_admin_info_callback(query, _context: ContextTypes.DEFAULT_TYPE, admin_id: str):
    """Handle callback for showing admin info."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Delete Admin", callback_data=f"delete_admin:{admin_id}")
        ],
        [InlineKeyboardButton("« Back to List", callback_data=CallbackData.LIST_ADMINS)]
    ])
    
    await query.edit_message_text(
        text=f"👤 <b>Admin Info</b>\n\n"
             f"<b>Chat ID:</b> <code>{admin_id}</code>\n\n"
             f"This user has full admin access to the bot.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def handle_delete_admin_callback(query, _context: ContextTypes.DEFAULT_TYPE, admin_id: str):
    """Handle callback for deleting an admin."""
    admins = await check_admin()
    
    # Check if this is the last admin
    if len(admins) <= 1:
        await query.edit_message_text(
            text="⚠️ <b>Cannot delete last admin!</b>\n\n"
                 "There must be at least one admin. Add another admin first before removing this one.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back to List", callback_data=CallbackData.LIST_ADMINS)]
            ]),
            parse_mode="HTML"
        )
        return
    
    try:
        admin_id_int = int(admin_id)
        result = await remove_admin_from_config(admin_id_int)
        
        if result:
            text = f"✅ Admin <code>{admin_id}</code> removed successfully!"
        else:
            text = f"❌ Admin <code>{admin_id}</code> not found."
    except ValueError:
        text = f"❌ Invalid admin ID: <code>{admin_id}</code>"
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back to List", callback_data=CallbackData.LIST_ADMINS)]
        ]),
        parse_mode="HTML"
    )


async def remove_admin(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Removes an admin from admin list"""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    admins_count = len(await check_admin())
    if admins_count == 1:
        await update.message.reply_html(
            text="there is just <b>1</b> active admin remain."
            + " <b>if you delete this chat id, then first person start bot "
            + "is new admin</b> or <b>add admin chat id</b> in <code>ADMIN_IDS</code> environment variable"
        )
    await update.message.reply_html(text="Send chat id of the admin to remove: ")
    return GET_CHAT_ID_TO_REMOVE


async def get_chat_id_to_remove(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Get admin chat id to delete it from admin list"""
    try:
        admin_id_to_remove = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_html(
            text=f"Wrong input: <code>{update.message.text.strip()}"
            + "</code>\ntry again <b>/remove_admin</b>"
        )
        return ConversationHandler.END
    if await remove_admin_from_config(admin_id_to_remove):
        await update.message.reply_html(
            text=f"Admin <code>{admin_id_to_remove}</code> removed successfully!"
        )
    else:
        await update.message.reply_html(
            text=f"Admin <code>{admin_id_to_remove}</code> does not exist!"
        )
    return ConversationHandler.END
