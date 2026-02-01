"""
Limit patterns handlers for the Telegram bot.
Manages prefix/postfix patterns for automatic IP limit assignment.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from telegram_bot.utils import check_admin, add_admin_to_config
from telegram_bot.keyboards import create_back_to_main_keyboard
from telegram_bot.constants import CallbackData


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


def create_limit_patterns_keyboard():
    """Create main limit patterns menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("📋 List Patterns", callback_data=CallbackData.LIMIT_PATTERNS_LIST)],
        [InlineKeyboardButton("➕ Add Prefix", callback_data=CallbackData.LIMIT_PATTERNS_ADD_PREFIX)],
        [InlineKeyboardButton("➕ Add Postfix", callback_data=CallbackData.LIMIT_PATTERNS_ADD_POSTFIX)],
        [InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_SETTINGS)],
    ]
    return InlineKeyboardMarkup(keyboard)


async def handle_limit_patterns_menu_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle limit patterns menu callback."""
    try:
        from db.database import get_db
        from db.crud import LimitPatternCRUD
        
        async with get_db() as db:
            patterns = await LimitPatternCRUD.get_all(db)
        
        prefix_count = len([p for p in patterns if p.pattern_type == "prefix"])
        postfix_count = len([p for p in patterns if p.pattern_type == "postfix"])
        
        text = (
            "📊 <b>Limit Patterns (Prefix/Postfix)</b>\n\n"
            "Configure patterns to automatically set IP limits "
            "based on username patterns.\n\n"
            f"📊 <b>Current Patterns:</b>\n"
            f"  • Prefixes: {prefix_count}\n"
            f"  • Postfixes: {postfix_count}\n\n"
            "<b>Examples:</b>\n"
            "• Prefix <code>texiu_</code> → limit 2\n"
            "  → <code>texiu_john</code> gets limit of 2\n"
            "• Postfix <code>_vip</code> → limit 5\n"
            "  → <code>john_vip</code> gets limit of 5"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=create_limit_patterns_keyboard(),
            parse_mode="HTML"
        )
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


async def handle_limit_patterns_list_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle list patterns callback."""
    try:
        from db.database import get_db
        from db.crud import LimitPatternCRUD
        
        async with get_db() as db:
            patterns = await LimitPatternCRUD.get_all(db)
        
        if not patterns:
            text = (
                "📊 <b>Limit Patterns</b>\n\n"
                "❌ No patterns configured yet.\n\n"
                "Add prefixes or postfixes to set automatic IP limits."
            )
            keyboard = [
                [InlineKeyboardButton("➕ Add Prefix", callback_data=CallbackData.LIMIT_PATTERNS_ADD_PREFIX)],
                [InlineKeyboardButton("➕ Add Postfix", callback_data=CallbackData.LIMIT_PATTERNS_ADD_POSTFIX)],
                [InlineKeyboardButton("🔙 Back", callback_data=CallbackData.LIMIT_PATTERNS_MENU)],
            ]
        else:
            # Group by limit
            by_limit = {}
            for p in patterns:
                if p.ip_limit not in by_limit:
                    by_limit[p.ip_limit] = {"prefix": [], "postfix": []}
                by_limit[p.ip_limit][p.pattern_type].append(p)
            
            lines = ["📊 <b>Limit Patterns</b>\n"]
            for limit, types in sorted(by_limit.items()):
                lines.append(f"\n🎯 <b>Limit: {limit} IPs</b>")
                if types["prefix"]:
                    for p in types["prefix"]:
                        desc = f" ({p.description})" if p.description else ""
                        lines.append(f"  🔹 Prefix: <code>{p.pattern}</code> [ID:{p.id}]{desc}")
                if types["postfix"]:
                    for p in types["postfix"]:
                        desc = f" ({p.description})" if p.description else ""
                        lines.append(f"  🔸 Postfix: <code>{p.pattern}</code> [ID:{p.id}]{desc}")
            
            text = "\n".join(lines)
            text += "\n\n<i>To delete: /delete_limit_pattern &lt;ID&gt;</i>"
            text += "\n<i>To edit limit: /edit_limit_pattern &lt;ID&gt; &lt;new_limit&gt;</i>"
            
            keyboard = [
                [InlineKeyboardButton("➕ Add Prefix", callback_data=CallbackData.LIMIT_PATTERNS_ADD_PREFIX)],
                [InlineKeyboardButton("➕ Add Postfix", callback_data=CallbackData.LIMIT_PATTERNS_ADD_POSTFIX)],
                [InlineKeyboardButton("🔙 Back", callback_data=CallbackData.LIMIT_PATTERNS_MENU)],
            ]
        
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


async def handle_limit_patterns_add_prefix_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle add prefix callback - start conversation."""
    context.user_data["limit_pattern_type"] = "prefix"
    context.user_data["waiting_for"] = "limit_pattern_value"
    
    text = (
        "🔹 <b>Add Prefix Pattern</b>\n\n"
        "Step 1/2: Enter the <b>prefix pattern</b>:\n\n"
        "<i>Example: texiu_</i>\n"
        "<i>Users like texiu_john will match</i>"
    )
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.LIMIT_PATTERNS_MENU)]]
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def handle_limit_patterns_add_postfix_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle add postfix callback - start conversation."""
    context.user_data["limit_pattern_type"] = "postfix"
    context.user_data["waiting_for"] = "limit_pattern_value"
    
    text = (
        "🔸 <b>Add Postfix Pattern</b>\n\n"
        "Step 1/2: Enter the <b>postfix pattern</b>:\n\n"
        "<i>Example: _vip or .premium</i>\n"
        "<i>Users like john_vip will match</i>"
    )
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.LIMIT_PATTERNS_MENU)]]
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def handle_limit_pattern_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for limit pattern creation."""
    if not await check_admin_privilege(update):
        return
    
    waiting_for = context.user_data.get("waiting_for")
    
    if waiting_for == "limit_pattern_value":
        # Got pattern value, now ask for limit
        pattern = update.message.text.strip()
        context.user_data["limit_pattern_value"] = pattern
        context.user_data["waiting_for"] = "limit_pattern_limit"
        
        pattern_type = context.user_data.get("limit_pattern_type", "prefix")
        type_emoji = "🔹" if pattern_type == "prefix" else "🔸"
        
        text = (
            f"{type_emoji} <b>Add {pattern_type.title()} Pattern</b>\n\n"
            f"Pattern: <code>{pattern}</code>\n\n"
            f"Step 2/2: Enter the <b>IP limit</b> for this pattern:\n\n"
            "<i>Example: 2</i>"
        )
        
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.LIMIT_PATTERNS_MENU)]]
        
        await update.message.reply_html(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif waiting_for == "limit_pattern_limit":
        # Got limit value, save it
        try:
            ip_limit = int(update.message.text.strip())
            if ip_limit < 1:
                await update.message.reply_html(
                    "❌ IP limit must be at least 1. Please enter a valid number.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.LIMIT_PATTERNS_MENU)
                    ]])
                )
                return
        except ValueError:
            await update.message.reply_html(
                "❌ Invalid number. Please enter a valid IP limit.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Cancel", callback_data=CallbackData.LIMIT_PATTERNS_MENU)
                ]])
            )
            return
        
        pattern = context.user_data.get("limit_pattern_value")
        pattern_type = context.user_data.get("limit_pattern_type", "prefix")
        
        # Clear conversation state
        context.user_data["waiting_for"] = None
        context.user_data["limit_pattern_value"] = None
        context.user_data["limit_pattern_type"] = None
        
        try:
            from db.database import get_db
            from db.crud import LimitPatternCRUD
            
            async with get_db() as db:
                new_pattern = await LimitPatternCRUD.create(
                    db,
                    pattern_type=pattern_type,
                    pattern=pattern,
                    ip_limit=ip_limit
                )
                await db.commit()
            
            type_emoji = "🔹" if pattern_type == "prefix" else "🔸"
            text = (
                f"✅ <b>Pattern Added Successfully!</b>\n\n"
                f"{type_emoji} <b>Type:</b> {pattern_type.title()}\n"
                f"🏷️ <b>Pattern:</b> <code>{pattern}</code>\n"
                f"🎯 <b>IP Limit:</b> {ip_limit}\n"
                f"🆔 <b>ID:</b> {new_pattern.id}\n\n"
            )
            if pattern_type == "prefix":
                text += f"<i>Usernames starting with <code>{pattern}</code> will get limit of {ip_limit}</i>"
            else:
                text += f"<i>Usernames ending with <code>{pattern}</code> will get limit of {ip_limit}</i>"
            
            await update.message.reply_html(
                text=text,
                reply_markup=create_limit_patterns_keyboard()
            )
            
        except Exception as e:
            await update.message.reply_html(
                f"❌ Error creating pattern: {str(e)}",
                reply_markup=create_limit_patterns_keyboard()
            )


async def delete_limit_pattern_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delete_limit_pattern command."""
    if not await check_admin_privilege(update):
        return
    
    if not context.args:
        await update.message.reply_html(
            "❌ Usage: <code>/delete_limit_pattern &lt;ID&gt;</code>\n\n"
            "Get pattern IDs from the patterns list."
        )
        return
    
    try:
        pattern_id = int(context.args[0])
        
        from db.database import get_db
        from db.crud import LimitPatternCRUD
        
        async with get_db() as db:
            pattern = await LimitPatternCRUD.get_by_id(db, pattern_id)
            if not pattern:
                await update.message.reply_html(f"❌ Pattern ID {pattern_id} not found.")
                return
            
            ip_limit = pattern.ip_limit
            ptype = pattern.pattern_type
            pvalue = pattern.pattern
            
            deleted = await LimitPatternCRUD.delete_by_id(db, pattern_id)
            await db.commit()
            
            if deleted:
                await update.message.reply_html(
                    f"✅ Deleted pattern:\n\n"
                    f"🆔 ID: {pattern_id}\n"
                    f"🎯 Limit: {ip_limit} IPs\n"
                    f"🏷️ {ptype.title()}: <code>{pvalue}</code>",
                    reply_markup=create_limit_patterns_keyboard()
                )
            else:
                await update.message.reply_html(f"❌ Failed to delete pattern ID {pattern_id}.")
                
    except ValueError:
        await update.message.reply_html("❌ Invalid pattern ID. Must be a number.")
    except Exception as e:
        await update.message.reply_html(f"❌ Error: {str(e)}")


async def edit_limit_pattern_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /edit_limit_pattern command."""
    if not await check_admin_privilege(update):
        return
    
    if len(context.args) < 2:
        await update.message.reply_html(
            "❌ Usage: <code>/edit_limit_pattern &lt;ID&gt; &lt;new_limit&gt;</code>\n\n"
            "Example: <code>/edit_limit_pattern 1 3</code>"
        )
        return
    
    try:
        pattern_id = int(context.args[0])
        new_limit = int(context.args[1])
        
        if new_limit < 1:
            await update.message.reply_html("❌ IP limit must be at least 1.")
            return
        
        from db.database import get_db
        from db.crud import LimitPatternCRUD
        
        async with get_db() as db:
            pattern = await LimitPatternCRUD.get_by_id(db, pattern_id)
            if not pattern:
                await update.message.reply_html(f"❌ Pattern ID {pattern_id} not found.")
                return
            
            old_limit = pattern.ip_limit
            ptype = pattern.pattern_type
            pvalue = pattern.pattern
            
            updated = await LimitPatternCRUD.update_limit(db, pattern_id, new_limit)
            await db.commit()
            
            if updated:
                await update.message.reply_html(
                    f"✅ Updated pattern:\n\n"
                    f"🆔 ID: {pattern_id}\n"
                    f"🏷️ {ptype.title()}: <code>{pvalue}</code>\n"
                    f"🎯 Limit: {old_limit} → {new_limit} IPs",
                    reply_markup=create_limit_patterns_keyboard()
                )
            else:
                await update.message.reply_html(f"❌ Failed to update pattern ID {pattern_id}.")
                
    except ValueError:
        await update.message.reply_html("❌ Invalid ID or limit. Both must be numbers.")
    except Exception as e:
        await update.message.reply_html(f"❌ Error: {str(e)}")


async def add_limit_prefix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add_limit_prefix command."""
    if not await check_admin_privilege(update):
        return
    
    if len(context.args) < 2:
        await update.message.reply_html(
            "❌ Usage: <code>/add_limit_prefix &lt;prefix&gt; &lt;limit&gt;</code>\n\n"
            "Example: <code>/add_limit_prefix texiu_ 2</code>"
        )
        return
    
    prefix = context.args[0]
    try:
        ip_limit = int(context.args[1])
        if ip_limit < 1:
            await update.message.reply_html("❌ IP limit must be at least 1.")
            return
    except ValueError:
        await update.message.reply_html("❌ Invalid limit. Must be a number.")
        return
    
    try:
        from db.database import get_db
        from db.crud import LimitPatternCRUD
        
        async with get_db() as db:
            new_pattern = await LimitPatternCRUD.create(
                db,
                pattern_type="prefix",
                pattern=prefix,
                ip_limit=ip_limit
            )
            await db.commit()
        
        await update.message.reply_html(
            f"✅ <b>Prefix Added!</b>\n\n"
            f"🔹 Prefix: <code>{prefix}</code>\n"
            f"🎯 IP Limit: {ip_limit}\n"
            f"🆔 ID: {new_pattern.id}\n\n"
            f"<i>Usernames starting with <code>{prefix}</code> will get limit of {ip_limit}</i>",
            reply_markup=create_limit_patterns_keyboard()
        )
    except Exception as e:
        await update.message.reply_html(f"❌ Error: {str(e)}")


async def add_limit_postfix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add_limit_postfix command."""
    if not await check_admin_privilege(update):
        return
    
    if len(context.args) < 2:
        await update.message.reply_html(
            "❌ Usage: <code>/add_limit_postfix &lt;postfix&gt; &lt;limit&gt;</code>\n\n"
            "Example: <code>/add_limit_postfix _vip 5</code>"
        )
        return
    
    postfix = context.args[0]
    try:
        ip_limit = int(context.args[1])
        if ip_limit < 1:
            await update.message.reply_html("❌ IP limit must be at least 1.")
            return
    except ValueError:
        await update.message.reply_html("❌ Invalid limit. Must be a number.")
        return
    
    try:
        from db.database import get_db
        from db.crud import LimitPatternCRUD
        
        async with get_db() as db:
            new_pattern = await LimitPatternCRUD.create(
                db,
                pattern_type="postfix",
                pattern=postfix,
                ip_limit=ip_limit
            )
            await db.commit()
        
        await update.message.reply_html(
            f"✅ <b>Postfix Added!</b>\n\n"
            f"🔸 Postfix: <code>{postfix}</code>\n"
            f"🎯 IP Limit: {ip_limit}\n"
            f"🆔 ID: {new_pattern.id}\n\n"
            f"<i>Usernames ending with <code>{postfix}</code> will get limit of {ip_limit}</i>",
            reply_markup=create_limit_patterns_keyboard()
        )
    except Exception as e:
        await update.message.reply_html(f"❌ Error: {str(e)}")


async def list_limit_patterns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list_limit_patterns command."""
    if not await check_admin_privilege(update):
        return
    
    try:
        from db.database import get_db
        from db.crud import LimitPatternCRUD
        
        async with get_db() as db:
            patterns = await LimitPatternCRUD.get_all(db)
        
        if not patterns:
            await update.message.reply_html(
                "📊 <b>Limit Patterns</b>\n\n"
                "❌ No patterns configured yet.\n\n"
                "Use /add_limit_prefix or /add_limit_postfix to add patterns.",
                reply_markup=create_limit_patterns_keyboard()
            )
            return
        
        # Group by limit
        by_limit = {}
        for p in patterns:
            if p.ip_limit not in by_limit:
                by_limit[p.ip_limit] = {"prefix": [], "postfix": []}
            by_limit[p.ip_limit][p.pattern_type].append(p)
        
        lines = ["📊 <b>Limit Patterns</b>\n"]
        for limit, types in sorted(by_limit.items()):
            lines.append(f"\n🎯 <b>Limit: {limit} IPs</b>")
            if types["prefix"]:
                for p in types["prefix"]:
                    desc = f" ({p.description})" if p.description else ""
                    lines.append(f"  🔹 Prefix: <code>{p.pattern}</code> [ID:{p.id}]{desc}")
            if types["postfix"]:
                for p in types["postfix"]:
                    desc = f" ({p.description})" if p.description else ""
                    lines.append(f"  🔸 Postfix: <code>{p.pattern}</code> [ID:{p.id}]{desc}")
        
        text = "\n".join(lines)
        text += "\n\n<b>Commands:</b>\n"
        text += "/add_limit_prefix &lt;prefix&gt; &lt;limit&gt;\n"
        text += "/add_limit_postfix &lt;postfix&gt; &lt;limit&gt;\n"
        text += "/edit_limit_pattern &lt;ID&gt; &lt;new_limit&gt;\n"
        text += "/delete_limit_pattern &lt;ID&gt;"
        
        await update.message.reply_html(
            text=text,
            reply_markup=create_limit_patterns_keyboard()
        )
    except Exception as e:
        await update.message.reply_html(f"❌ Error: {str(e)}")
