"""
Topics settings handlers for the Telegram bot.
Manages forum topics configuration.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from telegram_bot.constants import CallbackData
from telegram_bot.handlers.admin import check_admin_privilege
from telegram_bot.topics import (
    TopicType,
    TOPIC_CONFIG,
    get_topics_manager,
)
from utils.logs import get_logger

topics_handler_logger = get_logger("topics.handler")


async def _send_response(update: Update, text: str, reply_markup=None):
    """Helper to send response in both message and callback query contexts."""
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception:
            await update.callback_query.message.reply_html(
                text=text,
                reply_markup=reply_markup
            )
    elif update.message:
        await update.message.reply_html(
            text=text,
            reply_markup=reply_markup
        )


def create_topics_menu_keyboard(enabled: bool, chat_id: int) -> InlineKeyboardMarkup:
    """Create the topics settings menu keyboard."""
    manager = get_topics_manager()
    all_topics = manager.get_all_topics(chat_id)
    
    toggle_text = "🔴 Disable Topics" if enabled else "🟢 Enable Topics"
    
    keyboard = [
        [InlineKeyboardButton(toggle_text, callback_data=CallbackData.TOPICS_TOGGLE)],
    ]
    
    if enabled:
        # Show topic status
        topics_configured = len(all_topics)
        total_topics = len(TopicType)
        
        keyboard.append([
            InlineKeyboardButton(
                f"🔧 Setup Topics ({topics_configured}/{total_topics})",
                callback_data=CallbackData.TOPICS_SETUP
            )
        ])
        
        if topics_configured > 0:
            keyboard.append([
                InlineKeyboardButton("🗑️ Clear All Topics", callback_data=CallbackData.TOPICS_CLEAR)
            ])
    
    keyboard.append([
        InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.BACK_SETTINGS)
    ])
    
    return InlineKeyboardMarkup(keyboard)


async def topics_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the topics settings menu."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        manager = get_topics_manager()
        enabled = manager.enabled
        chat_id = update.effective_chat.id
        all_topics = manager.get_all_topics(chat_id)
        
        # Build status message
        status_icon = "✅" if enabled else "❌"
        status_text = "Enabled" if enabled else "Disabled"
        
        topic_list = []
        for topic_type in TopicType:
            config = TOPIC_CONFIG[topic_type]
            thread_id = all_topics.get(topic_type.value)
            if thread_id:
                topic_list.append(f"  ✅ {config['name']}: <code>#{thread_id}</code>")
            else:
                topic_list.append(f"  ❌ {config['name']}: <i>Not configured</i>")
        
        message = (
            f"📌 <b>Forum Topics Settings</b>\n\n"
            f"Status: {status_icon} <code>{status_text}</code>\n\n"
            f"<b>Topics organize messages into categories:</b>\n"
            f"{chr(10).join(topic_list)}\n\n"
            f"💡 <i>Enable forum topics in your chat first, then use Setup to create topics.</i>"
        )
        
        await _send_response(update, message, create_topics_menu_keyboard(enabled, chat_id))
    
    except Exception as e:
        topics_handler_logger.error(f"❌ Error in topics_menu: {e}")
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def topics_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle topics feature on/off."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        manager = get_topics_manager()
        new_state = not manager.enabled
        await manager.set_enabled(new_state)
        
        status = "enabled ✅" if new_state else "disabled ❌"
        topics_handler_logger.info(f"📌 Topics {status}")
        
        # Return to menu
        await topics_menu(update, context)
    
    except Exception as e:
        topics_handler_logger.error(f"❌ Error toggling topics: {e}")
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def topics_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setup/create forum topics."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        from telegram_bot.main import application
        
        manager = get_topics_manager()
        chat_id = update.effective_chat.id
        
        # Check if chat has topics enabled
        chat = await application.bot.get_chat(chat_id)
        
        if not getattr(chat, 'has_topics_enabled', False):
            await _send_response(
                update,
                "❌ <b>Forum Topics Not Enabled</b>\n\n"
                "Please enable forum topics in your chat settings first:\n"
                "1. Open chat settings\n"
                "2. Enable 'Topics' feature\n"
                "3. Return here and try again"
            )
            return ConversationHandler.END
        
        # Create topics
        await _send_response(
            update,
            "⏳ <b>Creating topics...</b>\n\n"
            "This may take a moment..."
        )
        
        created_topics = await manager.create_topics_for_chat(chat_id, application.bot)
        
        if created_topics:
            topic_list = []
            for topic_type, thread_id in created_topics.items():
                config = TOPIC_CONFIG[topic_type]
                topic_list.append(f"  ✅ {config['name']}")
            
            message = (
                f"✅ <b>Topics Created Successfully!</b>\n\n"
                f"Created {len(created_topics)} topics:\n"
                f"{chr(10).join(topic_list)}\n\n"
                f"Messages will now be organized by category."
            )
        else:
            message = "⚠️ No topics were created. Please try again."
        
        # Return to menu
        await _send_response(update, message, create_topics_menu_keyboard(manager.enabled, chat_id))
    
    except Exception as e:
        topics_handler_logger.error(f"❌ Error setting up topics: {e}")
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def topics_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear all topic configurations for this chat."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        manager = get_topics_manager()
        chat_id = update.effective_chat.id
        
        await manager.clear_chat_topics(chat_id)
        
        topics_handler_logger.info(f"🗑️ Cleared topics for chat {chat_id}")
        
        await _send_response(
            update,
            "✅ <b>Topics Cleared</b>\n\n"
            "All topic configurations have been removed.\n"
            "Messages will be sent to the main chat."
        )
        
        # Return to menu
        await topics_menu(update, context)
    
    except Exception as e:
        topics_handler_logger.error(f"❌ Error clearing topics: {e}")
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


# Callback handlers for use in main.py
async def handle_topics_menu_callback(query, context):
    """Handle callback for topics menu."""
    update = Update(update_id=0, callback_query=query)
    await topics_menu(update, context)


async def handle_topics_toggle_callback(query, context):
    """Handle callback for topics toggle."""
    update = Update(update_id=0, callback_query=query)
    await topics_toggle(update, context)


async def handle_topics_setup_callback(query, context):
    """Handle callback for topics setup."""
    update = Update(update_id=0, callback_query=query)
    await topics_setup(update, context)


async def handle_topics_clear_callback(query, context):
    """Handle callback for topics clear."""
    update = Update(update_id=0, callback_query=query)
    await topics_clear(update, context)
