"""
Topics settings handlers for the Telegram bot.
Manages forum topics configuration in a supergroup.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from telegram_bot.constants import CallbackData, WAITING_GROUP_ID
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


def create_topics_menu_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    """Create the topics settings menu keyboard."""
    manager = get_topics_manager()
    all_topics = manager.get_all_topics()
    group_id = manager.group_id
    
    toggle_text = "🔴 Disable Topics" if enabled else "🟢 Enable Topics"
    
    keyboard = [
        [InlineKeyboardButton(toggle_text, callback_data=CallbackData.TOPICS_TOGGLE)],
    ]
    
    # Show group configuration
    if group_id:
        keyboard.append([
            InlineKeyboardButton(
                f"🔄 Change Group ID",
                callback_data=CallbackData.TOPICS_SET_GROUP
            )
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(
                "📝 Set Forum Group ID",
                callback_data=CallbackData.TOPICS_SET_GROUP
            )
        ])
    
    if enabled and group_id:
        # Show topic status
        topics_configured = len(all_topics)
        total_topics = len(TopicType)
        
        keyboard.append([
            InlineKeyboardButton(
                f"🔧 Create Topics ({topics_configured}/{total_topics})",
                callback_data=CallbackData.TOPICS_SETUP
            )
        ])
        
        keyboard.append([
            InlineKeyboardButton(
                "🔍 Check Bot Permissions",
                callback_data=CallbackData.TOPICS_CHECK_PERMISSIONS
            )
        ])
        
        if topics_configured > 0:
            keyboard.append([
                InlineKeyboardButton("🗑️ Clear All Topics", callback_data=CallbackData.TOPICS_CLEAR)
            ])
            keyboard.append([
                InlineKeyboardButton("🧹 Clear Message Cache", callback_data=CallbackData.TOPICS_CLEAR_CACHE)
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
        group_id = manager.group_id
        all_topics = manager.get_all_topics()
        
        # Build status message
        status_icon = "✅" if enabled else "❌"
        status_text = "Enabled" if enabled else "Disabled"
        
        group_info = f"<code>{group_id}</code>" if group_id else "<i>Not configured</i>"
        
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
            f"Status: {status_icon} <code>{status_text}</code>\n"
            f"Forum Group ID: {group_info}\n\n"
            f"<b>Topics organize messages into categories:</b>\n"
            f"{chr(10).join(topic_list)}\n\n"
            f"💡 <i>To use topics:\n"
            f"1. Create a group and enable Topics in group settings\n"
            f"2. Add the bot as admin with 'Manage Topics' permission\n"
            f"3. Get the group ID (use @myidbot in the group)\n"
            f"4. Set the group ID here and create topics</i>"
        )
        
        await _send_response(update, message, create_topics_menu_keyboard(enabled))
    
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
        
        # Check if group is configured before enabling
        if not manager.enabled and not manager.group_id:
            await _send_response(
                update,
                "❌ <b>Cannot Enable Topics</b>\n\n"
                "Please set a forum group ID first before enabling topics."
            )
            return ConversationHandler.END
        
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


async def topics_set_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the process to set forum group ID."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        manager = get_topics_manager()
        current_group = manager.group_id
        
        current_text = f"\n\nCurrent group ID: <code>{current_group}</code>" if current_group else ""
        
        keyboard = [[InlineKeyboardButton("« Cancel", callback_data=CallbackData.TOPICS_MENU)]]
        
        await _send_response(
            update,
            f"📝 <b>Set Forum Group ID</b>\n\n"
            f"Please send the group ID of your forum supergroup.\n\n"
            f"To get the group ID:\n"
            f"1. Add @myidbot to your group\n"
            f"2. Type /getgroupid in the group\n"
            f"3. Copy the group ID (starts with -100)"
            f"{current_text}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Set waiting_for to handle text input
        context.user_data["waiting_for"] = "forum_group_id"
        return ConversationHandler.END
    
    except Exception as e:
        topics_handler_logger.error(f"❌ Error starting group ID setup: {e}")
        await _send_response(update, f"❌ Error: {str(e)}")
        return ConversationHandler.END


async def topics_set_group_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and validate the forum group ID."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        text = update.message.text.strip()
        
        # Parse group ID
        try:
            group_id = int(text)
        except ValueError:
            await update.message.reply_html(
                "❌ Invalid group ID. Please send a valid number.\n"
                "Group IDs typically start with -100 for supergroups."
            )
            return WAITING_GROUP_ID
        
        manager = get_topics_manager()
        
        # Set the group ID first
        await manager.set_group_id(group_id)
        
        # Now check permissions
        from telegram_bot.main import application
        success, message = await manager.check_bot_permissions(application.bot)
        
        if success:
            await update.message.reply_html(
                f"✅ <b>Forum Group Set Successfully!</b>\n\n"
                f"Group ID: <code>{group_id}</code>\n"
                f"{message}\n\n"
                f"You can now enable topics and create them in the group."
            )
        else:
            await update.message.reply_html(
                f"⚠️ <b>Group ID Set</b>\n\n"
                f"Group ID: <code>{group_id}</code>\n\n"
                f"Warning: {message}\n\n"
                f"Please fix the issues above, then try again."
            )
        
        topics_handler_logger.info(f"📌 Forum group set to {group_id}")
        
        # Return to menu
        await topics_menu(update, context)
        return ConversationHandler.END
    
    except Exception as e:
        topics_handler_logger.error(f"❌ Error setting group ID: {e}")
        await update.message.reply_html(f"❌ Error: {str(e)}")
        return ConversationHandler.END


async def topics_check_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check bot permissions in the forum group."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        from telegram_bot.main import application
        
        manager = get_topics_manager()
        
        if not manager.group_id:
            await _send_response(
                update,
                "❌ No forum group configured. Please set a group ID first."
            )
            return ConversationHandler.END
        
        success, message = await manager.check_bot_permissions(application.bot)
        
        if success:
            await _send_response(
                update,
                f"🔍 <b>Permission Check</b>\n\n{message}"
            )
        else:
            await _send_response(
                update,
                f"🔍 <b>Permission Check Failed</b>\n\n❌ {message}"
            )
        
        # Return to menu
        await topics_menu(update, context)
    
    except Exception as e:
        topics_handler_logger.error(f"❌ Error checking permissions: {e}")
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def topics_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setup/create forum topics in the group."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        from telegram_bot.main import application
        
        manager = get_topics_manager()
        
        if not manager.group_id:
            await _send_response(
                update,
                "❌ <b>No Forum Group Configured</b>\n\n"
                "Please set a forum group ID first."
            )
            return ConversationHandler.END
        
        # Check permissions first
        success, message = await manager.check_bot_permissions(application.bot)
        
        if not success:
            await _send_response(
                update,
                f"❌ <b>Cannot Create Topics</b>\n\n{message}"
            )
            return ConversationHandler.END
        
        # Create topics
        await _send_response(
            update,
            "⏳ <b>Creating topics...</b>\n\n"
            "This may take a moment..."
        )
        
        created_topics = await manager.create_topics_for_group(application.bot)
        
        if created_topics:
            topic_list = []
            for topic_type, thread_id in created_topics.items():
                config = TOPIC_CONFIG[topic_type]
                topic_list.append(f"  ✅ {config['name']}")
            
            message = (
                f"✅ <b>Topics Created Successfully!</b>\n\n"
                f"Created {len(created_topics)} topics:\n"
                f"{chr(10).join(topic_list)}\n\n"
                f"Messages will now be organized by category in the forum group."
            )
        else:
            message = "⚠️ No topics were created. Please check permissions and try again."
        
        # Return to menu
        await _send_response(update, message, create_topics_menu_keyboard(manager.enabled))
    
    except Exception as e:
        topics_handler_logger.error(f"❌ Error setting up topics: {e}")
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def topics_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear all topic configurations."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        manager = get_topics_manager()
        
        await manager.clear_all_topics()
        
        topics_handler_logger.info("🗑️ Cleared all topics")
        
        await _send_response(
            update,
            "✅ <b>Topics Cleared</b>\n\n"
            "All topic configurations have been removed.\n"
            "Messages will be sent to the main chat or group."
        )
        
        # Return to menu
        await topics_menu(update, context)
    
    except Exception as e:
        topics_handler_logger.error(f"❌ Error clearing topics: {e}")
        await _send_response(update, f"❌ Error: {str(e)}")
    
    return ConversationHandler.END


async def topics_clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear the message deduplication cache."""
    check = await check_admin_privilege(update)
    if check:
        return check
    
    try:
        manager = get_topics_manager()
        
        await manager.clear_message_cache()
        
        topics_handler_logger.info("🧹 Cleared message cache")
        
        await _send_response(
            update,
            "✅ <b>Message Cache Cleared</b>\n\n"
            "The deduplication cache has been cleared.\n"
            "Previously sent 'no limit found' messages can be sent again."
        )
        
        # Return to menu
        await topics_menu(update, context)
    
    except Exception as e:
        topics_handler_logger.error(f"❌ Error clearing cache: {e}")
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


async def handle_topics_set_group_callback(query, context):
    """Handle callback for setting group ID."""
    update = Update(update_id=0, callback_query=query)
    return await topics_set_group_start(update, context)


async def handle_topics_check_permissions_callback(query, context):
    """Handle callback for checking permissions."""
    update = Update(update_id=0, callback_query=query)
    await topics_check_permissions(update, context)


async def handle_topics_clear_cache_callback(query, context):
    """Handle callback for clearing message cache."""
    update = Update(update_id=0, callback_query=query)
    await topics_clear_cache(update, context)
