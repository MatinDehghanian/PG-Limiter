"""
Send logs to telegram bot with topic support.
"""

from utils.logs import get_logger
from telegram_bot.utils import check_admin
from telegram_bot.topics import TopicType, get_topics_manager

tg_send_logger = get_logger("telegram.send")


async def send_logs(msg, return_message_id=False, reply_markup=None, topic_type: TopicType = TopicType.GENERAL):
    """
    Send logs to all admins.
    
    Args:
        msg: The message to send
        return_message_id: If True, returns the message_id of the first admin's message
        reply_markup: Optional InlineKeyboardMarkup for buttons
        topic_type: Topic type to send to (default: GENERAL)
        
    Returns:
        If return_message_id is True, returns (message_id, chat_id) tuple or None
        Otherwise returns None
    """
    # Import application here to get the updated instance
    from telegram_bot.main import application
    
    admins = await check_admin()
    retries = 2
    first_message_info = None
    topics_manager = get_topics_manager()
    
    tg_send_logger.debug(f"📤 Sending log to {len(admins)} admins ({len(msg)} chars) topic={topic_type.value}")
    
    if admins:
        for admin in admins:
            thread_id = topics_manager.get_topic_id(admin, topic_type)
            for attempt in range(retries):
                try:
                    sent_message = await application.bot.sendMessage(
                        chat_id=admin, text=msg, parse_mode="HTML",
                        reply_markup=reply_markup,
                        message_thread_id=thread_id
                    )
                    # Store the first successful message info for editing later
                    if first_message_info is None and return_message_id:
                        first_message_info = (sent_message.message_id, admin)
                    tg_send_logger.debug(f"✅ Message sent to admin {admin} (thread={thread_id})")
                    break
                except Exception as e:  # pylint: disable=broad-except
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
    
    await send_logs(msg, reply_markup=reply_markup, topic_type=TopicType.DISABLE_ENABLE)


async def send_user_message(msg: str, username: str, device_count: int, has_special_limit: bool, is_except: bool, general_limit: int = 2):
    """
    Send a message for a single user with inline buttons for setting limits.
    Only shows buttons if user doesn't have special limit and is not in except list.
    Sends to NO_LIMIT topic since this is for users without special limits.
    
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
    
    tg_send_logger.debug(f"📤 Sending user message for {username} (devices: {device_count})")
    admins = await check_admin()
    retries = 2
    topics_manager = get_topics_manager()
    
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
    
    if admins:
        for admin in admins:
            thread_id = topics_manager.get_topic_id(admin, TopicType.NO_LIMIT)
            for attempt in range(retries):
                try:
                    await application.bot.sendMessage(
                        chat_id=admin, 
                        text=msg, 
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                        message_thread_id=thread_id
                    )
                    tg_send_logger.debug(f"✅ User message sent to admin {admin} (thread={thread_id})")
                    break
                except Exception as e:
                    tg_send_logger.warning(f"⚠️ Attempt {attempt + 1}/{retries} failed for admin {admin}: {e}")
