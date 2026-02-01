"""
Admin patterns handlers for the Telegram bot.
Manages prefix/postfix patterns for admin identification.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import BadRequest

from telegram_bot.utils import check_admin, add_admin_to_config
from telegram_bot.keyboards import create_back_to_main_keyboard
from telegram_bot.constants import CallbackData


# Conversation states
WAITING_FOR_ADMIN = 1
WAITING_FOR_PREFIX = 2
WAITING_FOR_POSTFIX = 3


async def _send_response(update: Update, text: str, reply_markup=None):
    """Send response handling both message and callback query contexts."""
    if update.callback_query:
        try:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
    else:
        await update.message.reply_html(
            text=text,
            reply_markup=reply_markup
        )


async def check_admin_privilege(update: Update):
    """Checks if the user has admin privileges."""
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        await _send_response(
            update,
            "Sorry, you do not have permission to use this bot."
        )
        return False
    
    admins = await check_admin()
    if not admins:
        await add_admin_to_config(user_id)
    admins = await check_admin()
    if user_id not in admins:
        await _send_response(
            update,
            "Sorry, you do not have permission to use this bot."
        )
        return False
    return True


def create_admin_patterns_keyboard():
    """Create main admin patterns menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("📋 List Patterns", callback_data=CallbackData.ADMIN_PATTERNS_LIST)],
        [InlineKeyboardButton("➕ Add Prefix", callback_data=CallbackData.ADMIN_PATTERNS_ADD_PREFIX)],
        [InlineKeyboardButton("➕ Add Postfix", callback_data=CallbackData.ADMIN_PATTERNS_ADD_POSTFIX)],
        [InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_SETTINGS)],
    ]
    return InlineKeyboardMarkup(keyboard)


async def handle_admin_patterns_menu_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin patterns menu callback."""
    try:
        from db.database import get_db
        from db.crud import AdminPatternCRUD
        
        async with get_db() as db:
            patterns = await AdminPatternCRUD.get_all(db)
        
        prefix_count = len([p for p in patterns if p.pattern_type == "prefix"])
        postfix_count = len([p for p in patterns if p.pattern_type == "postfix"])
        
        text = (
            "🏷️ <b>Admin Patterns (Prefix/Postfix)</b>\n\n"
            "Configure patterns to identify which admin owns a user "
            "based on their username.\n\n"
            f"📊 <b>Current Patterns:</b>\n"
            f"  • Prefixes: {prefix_count}\n"
            f"  • Postfixes: {postfix_count}\n\n"
            "<b>Examples:</b>\n"
            "• Prefix <code>2_user_</code> → <code>2_user_john</code>\n"
            "• Postfix <code>2User</code> → <code>john2User</code>\n"
            "• Postfix <code>.2.User</code> → <code>john.2.User</code>"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=create_admin_patterns_keyboard(),
            parse_mode="HTML"
        )
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


async def handle_admin_patterns_list_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle list patterns callback."""
    try:
        from db.database import get_db
        from db.crud import AdminPatternCRUD
        
        async with get_db() as db:
            patterns = await AdminPatternCRUD.get_all(db)
        
        if not patterns:
            text = (
                "🏷️ <b>Admin Patterns</b>\n\n"
                "❌ No patterns configured yet.\n\n"
                "Add prefixes or postfixes to identify users by their admin."
            )
            keyboard = [
                [InlineKeyboardButton("➕ Add Prefix", callback_data=CallbackData.ADMIN_PATTERNS_ADD_PREFIX)],
                [InlineKeyboardButton("➕ Add Postfix", callback_data=CallbackData.ADMIN_PATTERNS_ADD_POSTFIX)],
                [InlineKeyboardButton("🔙 Back", callback_data=CallbackData.ADMIN_PATTERNS_MENU)],
            ]
        else:
            # Group by admin
            by_admin = {}
            for p in patterns:
                if p.admin_username not in by_admin:
                    by_admin[p.admin_username] = {"prefix": [], "postfix": []}
                by_admin[p.admin_username][p.pattern_type].append(p)
            
            lines = ["🏷️ <b>Admin Patterns</b>\n"]
            for admin, types in by_admin.items():
                lines.append(f"\n👤 <b>{admin}</b>")
                if types["prefix"]:
                    for p in types["prefix"]:
                        lines.append(f"  🔹 Prefix: <code>{p.pattern}</code> [ID:{p.id}]")
                if types["postfix"]:
                    for p in types["postfix"]:
                        lines.append(f"  🔸 Postfix: <code>{p.pattern}</code> [ID:{p.id}]")
            
            text = "\n".join(lines)
            text += "\n\n<i>To delete a pattern, use: /delete_pattern &lt;ID&gt;</i>"
            
            keyboard = [
                [InlineKeyboardButton("➕ Add Prefix", callback_data=CallbackData.ADMIN_PATTERNS_ADD_PREFIX)],
                [InlineKeyboardButton("➕ Add Postfix", callback_data=CallbackData.ADMIN_PATTERNS_ADD_POSTFIX)],
                [InlineKeyboardButton("🔙 Back", callback_data=CallbackData.ADMIN_PATTERNS_MENU)],
            ]
        
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


async def handle_admin_patterns_add_prefix_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle add prefix callback - start conversation."""
    context.user_data["pattern_type"] = "prefix"
    context.user_data["waiting_for"] = "admin_pattern_admin"
    
    text = (
        "🔹 <b>Add Prefix Pattern</b>\n\n"
        "Step 1/2: Enter the <b>admin username</b> who owns users with this prefix:\n\n"
        "<i>Example: admin1</i>"
    )
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.ADMIN_PATTERNS_MENU)]]
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def handle_admin_patterns_add_postfix_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle add postfix callback - start conversation."""
    context.user_data["pattern_type"] = "postfix"
    context.user_data["waiting_for"] = "admin_pattern_admin"
    
    text = (
        "🔸 <b>Add Postfix Pattern</b>\n\n"
        "Step 1/2: Enter the <b>admin username</b> who owns users with this postfix:\n\n"
        "<i>Example: admin1</i>"
    )
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.ADMIN_PATTERNS_MENU)]]
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def handle_admin_pattern_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for admin pattern creation."""
    if not await check_admin_privilege(update):
        return
    
    waiting_for = context.user_data.get("waiting_for")
    
    if waiting_for == "admin_pattern_admin":
        # Got admin username, now ask for pattern
        admin_username = update.message.text.strip()
        context.user_data["pattern_admin"] = admin_username
        context.user_data["waiting_for"] = "admin_pattern_value"
        
        pattern_type = context.user_data.get("pattern_type", "prefix")
        type_emoji = "🔹" if pattern_type == "prefix" else "🔸"
        
        text = (
            f"{type_emoji} <b>Add {pattern_type.title()} Pattern</b>\n\n"
            f"Admin: <code>{admin_username}</code>\n\n"
            f"Step 2/2: Enter the <b>{pattern_type}</b> pattern:\n\n"
        )
        if pattern_type == "prefix":
            text += "<i>Example: 2_user_</i>\n<i>Users like 2_user_john will match</i>"
        else:
            text += "<i>Example: 2User or .2.User</i>\n<i>Users like john2User will match</i>"
        
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.ADMIN_PATTERNS_MENU)]]
        
        await update.message.reply_html(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif waiting_for == "admin_pattern_value":
        # Got pattern value, save it
        pattern = update.message.text.strip()
        admin_username = context.user_data.get("pattern_admin")
        pattern_type = context.user_data.get("pattern_type", "prefix")
        
        # Clear conversation state
        context.user_data["waiting_for"] = None
        context.user_data["pattern_admin"] = None
        context.user_data["pattern_type"] = None
        
        try:
            from db.database import get_db
            from db.crud import AdminPatternCRUD
            
            async with get_db() as db:
                new_pattern = await AdminPatternCRUD.create(
                    db,
                    admin_username=admin_username,
                    pattern_type=pattern_type,
                    pattern=pattern
                )
                await db.commit()
            
            type_emoji = "🔹" if pattern_type == "prefix" else "🔸"
            text = (
                f"✅ <b>Pattern Added Successfully!</b>\n\n"
                f"{type_emoji} <b>Type:</b> {pattern_type.title()}\n"
                f"👤 <b>Admin:</b> <code>{admin_username}</code>\n"
                f"🏷️ <b>Pattern:</b> <code>{pattern}</code>\n"
                f"🆔 <b>ID:</b> {new_pattern.id}\n\n"
            )
            if pattern_type == "prefix":
                text += f"<i>Usernames starting with <code>{pattern}</code> will be matched to {admin_username}</i>"
            else:
                text += f"<i>Usernames ending with <code>{pattern}</code> will be matched to {admin_username}</i>"
            
            await update.message.reply_html(
                text=text,
                reply_markup=create_admin_patterns_keyboard()
            )
            
        except Exception as e:
            await update.message.reply_html(
                f"❌ Error creating pattern: {str(e)}",
                reply_markup=create_admin_patterns_keyboard()
            )


async def delete_pattern_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delete_pattern command."""
    if not await check_admin_privilege(update):
        return
    
    if not context.args:
        await update.message.reply_html(
            "❌ Usage: <code>/delete_pattern &lt;ID&gt;</code>\n\n"
            "Get pattern IDs from the patterns list."
        )
        return
    
    try:
        pattern_id = int(context.args[0])
        
        from db.database import get_db
        from db.crud import AdminPatternCRUD
        
        async with get_db() as db:
            pattern = await AdminPatternCRUD.get_by_id(db, pattern_id)
            if not pattern:
                await update.message.reply_html(f"❌ Pattern ID {pattern_id} not found.")
                return
            
            admin = pattern.admin_username
            ptype = pattern.pattern_type
            pvalue = pattern.pattern
            
            deleted = await AdminPatternCRUD.delete_by_id(db, pattern_id)
            await db.commit()
            
            if deleted:
                await update.message.reply_html(
                    f"✅ Deleted pattern:\n\n"
                    f"🆔 ID: {pattern_id}\n"
                    f"👤 Admin: <code>{admin}</code>\n"
                    f"🏷️ {ptype.title()}: <code>{pvalue}</code>",
                    reply_markup=create_admin_patterns_keyboard()
                )
            else:
                await update.message.reply_html(f"❌ Failed to delete pattern ID {pattern_id}.")
                
    except ValueError:
        await update.message.reply_html("❌ Invalid pattern ID. Must be a number.")
    except Exception as e:
        await update.message.reply_html(f"❌ Error: {str(e)}")


async def add_prefix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add_prefix command."""
    if not await check_admin_privilege(update):
        return
    
    if len(context.args) < 2:
        await update.message.reply_html(
            "❌ Usage: <code>/add_prefix &lt;admin_username&gt; &lt;prefix&gt;</code>\n\n"
            "Example: <code>/add_prefix admin1 2_user_</code>"
        )
        return
    
    admin_username = context.args[0]
    prefix = context.args[1]
    
    try:
        from db.database import get_db
        from db.crud import AdminPatternCRUD
        
        async with get_db() as db:
            new_pattern = await AdminPatternCRUD.create(
                db,
                admin_username=admin_username,
                pattern_type="prefix",
                pattern=prefix
            )
            await db.commit()
        
        await update.message.reply_html(
            f"✅ <b>Prefix Added!</b>\n\n"
            f"👤 Admin: <code>{admin_username}</code>\n"
            f"🔹 Prefix: <code>{prefix}</code>\n"
            f"🆔 ID: {new_pattern.id}\n\n"
            f"<i>Usernames starting with <code>{prefix}</code> will match {admin_username}</i>",
            reply_markup=create_admin_patterns_keyboard()
        )
    except Exception as e:
        await update.message.reply_html(f"❌ Error: {str(e)}")


async def add_postfix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add_postfix command."""
    if not await check_admin_privilege(update):
        return
    
    if len(context.args) < 2:
        await update.message.reply_html(
            "❌ Usage: <code>/add_postfix &lt;admin_username&gt; &lt;postfix&gt;</code>\n\n"
            "Example: <code>/add_postfix admin1 2User</code>"
        )
        return
    
    admin_username = context.args[0]
    postfix = context.args[1]
    
    try:
        from db.database import get_db
        from db.crud import AdminPatternCRUD
        
        async with get_db() as db:
            new_pattern = await AdminPatternCRUD.create(
                db,
                admin_username=admin_username,
                pattern_type="postfix",
                pattern=postfix
            )
            await db.commit()
        
        await update.message.reply_html(
            f"✅ <b>Postfix Added!</b>\n\n"
            f"👤 Admin: <code>{admin_username}</code>\n"
            f"🔸 Postfix: <code>{postfix}</code>\n"
            f"🆔 ID: {new_pattern.id}\n\n"
            f"<i>Usernames ending with <code>{postfix}</code> will match {admin_username}</i>",
            reply_markup=create_admin_patterns_keyboard()
        )
    except Exception as e:
        await update.message.reply_html(f"❌ Error: {str(e)}")


async def list_patterns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list_patterns command."""
    if not await check_admin_privilege(update):
        return
    
    try:
        from db.database import get_db
        from db.crud import AdminPatternCRUD
        
        async with get_db() as db:
            patterns = await AdminPatternCRUD.get_all(db)
        
        if not patterns:
            await update.message.reply_html(
                "🏷️ <b>Admin Patterns</b>\n\n"
                "❌ No patterns configured yet.\n\n"
                "Use /add_prefix or /add_postfix to add patterns.",
                reply_markup=create_admin_patterns_keyboard()
            )
            return
        
        # Group by admin
        by_admin = {}
        for p in patterns:
            if p.admin_username not in by_admin:
                by_admin[p.admin_username] = {"prefix": [], "postfix": []}
            by_admin[p.admin_username][p.pattern_type].append(p)
        
        lines = ["🏷️ <b>Admin Patterns</b>\n"]
        for admin, types in by_admin.items():
            lines.append(f"\n👤 <b>{admin}</b>")
            if types["prefix"]:
                for p in types["prefix"]:
                    lines.append(f"  🔹 Prefix: <code>{p.pattern}</code> [ID:{p.id}]")
            if types["postfix"]:
                for p in types["postfix"]:
                    lines.append(f"  🔸 Postfix: <code>{p.pattern}</code> [ID:{p.id}]")
        
        text = "\n".join(lines)
        text += "\n\n<b>Commands:</b>\n"
        text += "/add_prefix &lt;admin&gt; &lt;prefix&gt;\n"
        text += "/add_postfix &lt;admin&gt; &lt;postfix&gt;\n"
        text += "/delete_pattern &lt;ID&gt;"
        
        await update.message.reply_html(
            text=text,
            reply_markup=create_admin_patterns_keyboard()
        )
    except Exception as e:
        await update.message.reply_html(f"❌ Error: {str(e)}")
