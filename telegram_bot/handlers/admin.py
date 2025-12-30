"""
Admin management handlers for the Telegram bot.
Includes functions for adding, removing, and listing admins.
"""

from telegram import Update
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
)


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
    Sends a list of current admins.
    """
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    admins = await check_admin()
    if admins:
        admins_str = "\n- ".join(map(str, admins))
        await update.message.reply_html(text=f"Admins: \n- {admins_str}")
    else:
        await update.message.reply_html(text="No admins found!")
    return ConversationHandler.END


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
