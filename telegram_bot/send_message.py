"""
Send logs to telegram bot with topic support.
Messages can be sent to:
1. Forum group topics (if topics are enabled and configured)
2. Admin private chats (fallback)
"""

import json
import os
from utils.logs import get_logger
from telegram_bot.utils import check_admin
from telegram_bot.topics import TopicType, get_topics_manager, send_to_topic

tg_send_logger = get_logger("telegram.send")

# File to track disable messages for deletion
DISABLE_MESSAGES_FILE = "data/disable_messages.json"


def _load_disable_messages() -> dict:
    """Load disable messages tracking from file."""
    try:
        if os.path.exists(DISABLE_MESSAGES_FILE):
            with open(DISABLE_MESSAGES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        tg_send_logger.error(f"Error loading disable messages: {e}")
    return {}


def _save_disable_messages(data: dict):
    """Save disable messages tracking to file."""
    try:
        os.makedirs(os.path.dirname(DISABLE_MESSAGES_FILE), exist_ok=True)
        with open(DISABLE_MESSAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        tg_send_logger.error(f"Error saving disable messages: {e}")


def track_disable_message(username: str, message_id: int, chat_id: int):
    """Track a disable message for later deletion."""
    data = _load_disable_messages()
    data[username] = {"message_id": message_id, "chat_id": chat_id}
    _save_disable_messages(data)
    tg_send_logger.debug(f"📝 Tracked disable message for {username}: msg={message_id}, chat={chat_id}")


def get_disable_message(username: str) -> tuple[int, int] | None:
    """Get tracked disable message for a user. Returns (message_id, chat_id) or None."""
    data = _load_disable_messages()
    msg_info = data.get(username)
    if msg_info:
        return (msg_info["message_id"], msg_info["chat_id"])
    return None


def remove_disable_message_tracking(username: str):
    """Remove tracking for a user's disable message."""
    data = _load_disable_messages()
    if username in data:
        del data[username]
        _save_disable_messages(data)
        tg_send_logger.debug(f"🗑️ Removed disable message tracking for {username}")


async def send_logs(msg, return_message_id=False, reply_markup=None, topic_type: TopicType = TopicType.GENERAL, message_key: str = None):
    """
    Send logs to forum group topic or all admins.
    
    Args:
        msg: The message to send
        return_message_id: If True, returns the message_id of the first message
        reply_markup: Optional InlineKeyboardMarkup for buttons
        topic_type: Topic type to send to (default: GENERAL)
        message_key: Optional key for deduplication (if provided, message won't be sent if already sent with same key)
        
    Returns:
        If return_message_id is True, returns (message_id, chat_id) tuple or None
        Otherwise returns None
    """
    # Import application here to get the updated instance
    from telegram_bot.main import application
    
    topics_manager = get_topics_manager()
    retries = 2
    first_message_info = None
    
    tg_send_logger.debug(f"📤 Sending log ({len(msg)} chars) topic={topic_type.value}")
    
    # Try sending to forum group first if topics are enabled
    if topics_manager.enabled and topics_manager.group_id:
        # Check for duplicate if message_key provided
        if message_key and topics_manager.is_message_sent(topic_type, message_key):
            tg_send_logger.debug(f"⏭️ Skipping duplicate message: {message_key[:50]}...")
            return None
        
        thread_id = topics_manager.get_topic_id(topic_type)
        
        for attempt in range(retries):
            try:
                sent_message = await application.bot.sendMessage(
                    chat_id=topics_manager.group_id,
                    text=msg,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    message_thread_id=thread_id
                )
                
                # Mark message as sent if key provided
                if message_key:
                    await topics_manager.mark_message_sent(topic_type, message_key)
                
                if return_message_id:
                    first_message_info = (sent_message.message_id, topics_manager.group_id)
                
                tg_send_logger.debug(f"✅ Message sent to forum group (thread={thread_id})")
                
                if return_message_id:
                    return first_message_info
                return None
                
            except Exception as e:
                tg_send_logger.warning(f"⚠️ Attempt {attempt + 1}/{retries} failed for forum group: {e}")
    
    # Fallback: send to admins
    admins = await check_admin()
    
    if admins:
        for admin in admins:
            for attempt in range(retries):
                try:
                    sent_message = await application.bot.sendMessage(
                        chat_id=admin, text=msg, parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                    # Store the first successful message info for editing later
                    if first_message_info is None and return_message_id:
                        first_message_info = (sent_message.message_id, admin)
                    tg_send_logger.debug(f"✅ Message sent to admin {admin}")
                    break
                except Exception as e:
                    tg_send_logger.warning(f"⚠️ Attempt {attempt + 1}/{retries} failed for admin {admin}: {e}")
    else:
        tg_send_logger.warning("⚠️ No admins found to send message")
    
    if return_message_id:
        return first_message_info
    return None


async def send_warning_log(msg, return_message_id=False, reply_markup=None):
    """Send a warning message to the warnings topic."""
    return await send_logs(msg, return_message_id, reply_markup, TopicType.WARNINGS)


async def send_disable_enable_log(msg, return_message_id=False, reply_markup=None):
    """Send a disable/enable message to the disable_enable topic."""
    return await send_logs(msg, return_message_id, reply_markup, TopicType.DISABLE_ENABLE)


async def send_active_users_log(msg, return_message_id=False, reply_markup=None):
    """Send an active users message to the active_users topic."""
    return await send_logs(msg, return_message_id, reply_markup, TopicType.ACTIVE_USERS)


async def send_backup_log(msg, return_message_id=False, reply_markup=None):
    """Send a backup message to the backups topic."""
    return await send_logs(msg, return_message_id, reply_markup, TopicType.BACKUPS)


async def send_no_limit_log(msg, return_message_id=False, reply_markup=None):
    """Send a no-limit message to the no_limit topic."""
    return await send_logs(msg, return_message_id, reply_markup, TopicType.NO_LIMIT)


async def send_monitoring_log(msg, return_message_id=False, reply_markup=None):
    """Send a monitoring message to the monitoring topic."""
    return await send_logs(msg, return_message_id, reply_markup, TopicType.MONITORING)


async def delete_message(message_info):
    """
    Delete a message.
    
    Args:
        message_info: Tuple of (message_id, chat_id) returned by send_logs with return_message_id=True
        
    Returns:
        True if successful, False otherwise
    """
    if not message_info:
        return False
        
    message_id, chat_id = message_info
    
    from telegram_bot.main import application
    
    tg_send_logger.debug(f"🗑️ Deleting message {message_id} in chat {chat_id}")
    try:
        await application.bot.delete_message(
            chat_id=chat_id,
            message_id=message_id
        )
        tg_send_logger.debug("✅ Message deleted successfully")
        return True
    except Exception as e:
        tg_send_logger.error(f"❌ Failed to delete message: {e}")
        return False


async def edit_message(message_info, new_text):
    """
    Edit an existing message.
    
    Args:
        message_info: Tuple of (message_id, chat_id) returned by send_logs with return_message_id=True
        new_text: The new text to replace the message with
        
    Returns:
        True if successful, False otherwise
    """
    if not message_info:
        return False
        
    message_id, chat_id = message_info
    
    from telegram_bot.main import application
    
    tg_send_logger.debug(f"✏️ Editing message {message_id} in chat {chat_id}")
    try:
        await application.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=new_text,
            parse_mode="HTML"
        )
        tg_send_logger.debug("✅ Message edited successfully")
        return True
    except Exception as e:
        tg_send_logger.error(f"❌ Failed to edit message: {e}")
        return False


async def send_disable_notification(msg: str, username: str):
    """
    Send a disable notification with an Enable button to the disable/enable topic.
    Tracks the message ID for later deletion when user is enabled.
    
    Args:
        msg: The message text to send
        username: The username that was disabled
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    tg_send_logger.debug(f"🚫 Sending disable notification for {username}")
    keyboard = [
        [InlineKeyboardButton(f"✅ Enable {username}", callback_data=f"enable_user:{username}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send with return_message_id to track for later deletion
    message_info = await send_logs(msg, return_message_id=True, reply_markup=reply_markup, topic_type=TopicType.DISABLE_ENABLE)
    
    # Track the message for deletion when user is enabled
    if message_info:
        track_disable_message(username, message_info[0], message_info[1])


async def send_enable_notification(username: str, delete_disable_msg: bool = True):
    """
    Send an enable notification and optionally delete the original disable message.
    
    Args:
        username: The username that was enabled
        delete_disable_msg: Whether to delete the original disable message
    """
    from datetime import datetime
    
    tg_send_logger.debug(f"✅ Sending enable notification for {username}")
    
    # Delete the original disable message if tracked
    if delete_disable_msg:
        message_info = get_disable_message(username)
        if message_info:
            deleted = await delete_message(message_info)
            if deleted:
                tg_send_logger.info(f"🗑️ Deleted disable message for {username}")
            remove_disable_message_tracking(username)
    
    # Send enable notification
    enable_time = datetime.now().strftime("%H:%M:%S")
    msg = f"✅ <b>User Enabled</b>\n\n👤 User: <code>{username}</code>\n🕐 Time: <code>{enable_time}</code>"
    await send_logs(msg, topic_type=TopicType.DISABLE_ENABLE)


async def delete_disable_message_for_user(username: str) -> bool:
    """
    Delete the tracked disable message for a user.
    Called when user is automatically re-enabled after the period.
    
    Args:
        username: The username to delete disable message for
        
    Returns:
        True if message was deleted, False otherwise
    """
    message_info = get_disable_message(username)
    if message_info:
        deleted = await delete_message(message_info)
        remove_disable_message_tracking(username)
        if deleted:
            tg_send_logger.info(f"🗑️ Deleted disable message for {username}")
        return deleted
    return False


async def send_user_message(msg: str, username: str, device_count: int, has_special_limit: bool, is_except: bool, general_limit: int = 2):
    """
    Send a message for a single user with inline buttons for setting limits.
    Only shows buttons if user doesn't have special limit and is not in except list.
    Sends to NO_LIMIT topic since this is for users without special limits.
    
    Uses deduplication to avoid sending duplicate messages for the same user.
    
    Args:
        msg: The message text to send
        username: The username
        device_count: Number of devices the user has
        has_special_limit: Whether user already has a special limit set
        is_except: Whether user is in except list
        general_limit: The current general limit value
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram_bot.main import application
    
    topics_manager = get_topics_manager()
    retries = 2
    
    # Create a unique key for this user message (for deduplication)
    message_key = f"no_limit:{username}"
    
    tg_send_logger.debug(f"📤 Sending user message for {username} (devices: {device_count})")
    
    # Create inline keyboard if user doesn't have special limit and is not except
    reply_markup = None
    if not has_special_limit and not is_except:
        keyboard = [
            [
                InlineKeyboardButton(f"📱 Set {device_count} limit", callback_data=f"set_limit:{username}:{device_count}"),
                InlineKeyboardButton("🚫 Add to except", callback_data=f"add_except:{username}"),
            ],
            [
                InlineKeyboardButton("1️⃣ Set 1 device", callback_data=f"set_limit:{username}:1"),
                InlineKeyboardButton(f"🔢 Set {general_limit} (general)", callback_data=f"set_limit:{username}:{general_limit}"),
            ],
            [
                InlineKeyboardButton("✏️ Custom limit", callback_data=f"custom_limit:{username}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Try sending to forum group first if topics are enabled
    if topics_manager.enabled and topics_manager.group_id:
        # Check for duplicate
        if topics_manager.is_message_sent(TopicType.NO_LIMIT, message_key):
            tg_send_logger.debug(f"⏭️ Skipping duplicate no-limit message for {username}")
            return
        
        thread_id = topics_manager.get_topic_id(TopicType.NO_LIMIT)
        
        for attempt in range(retries):
            try:
                await application.bot.sendMessage(
                    chat_id=topics_manager.group_id,
                    text=msg,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    message_thread_id=thread_id
                )
                
                # Mark message as sent for this user
                await topics_manager.mark_message_sent(TopicType.NO_LIMIT, message_key)
                
                tg_send_logger.debug(f"✅ User message sent to forum group (thread={thread_id})")
                return
            except Exception as e:
                tg_send_logger.warning(f"⚠️ Attempt {attempt + 1}/{retries} failed for forum group: {e}")
    
    # Fallback: send to admins
    admins = await check_admin()
    
    if admins:
        for admin in admins:
            for attempt in range(retries):
                try:
                    await application.bot.sendMessage(
                        chat_id=admin, 
                        text=msg, 
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                    tg_send_logger.debug(f"✅ User message sent to admin {admin}")
                    break
                except Exception as e:
                    tg_send_logger.warning(f"⚠️ Attempt {attempt + 1}/{retries} failed for admin {admin}: {e}")
