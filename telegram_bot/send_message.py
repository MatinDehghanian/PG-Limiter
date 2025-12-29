"""
Send logs to telegram bot.
"""

from telegram_bot.utils import check_admin


async def send_logs(msg, return_message_id=False, reply_markup=None):
    """
    Send logs to all admins.
    
    Args:
        msg: The message to send
        return_message_id: If True, returns the message_id of the first admin's message
        reply_markup: Optional InlineKeyboardMarkup for buttons
        
    Returns:
        If return_message_id is True, returns (message_id, chat_id) tuple or None
        Otherwise returns None
    """
    # Import application here to get the updated instance
    from telegram_bot.main import application
    
    admins = await check_admin()
    retries = 2
    first_message_info = None
    
    if admins:
        for admin in admins:
            for _ in range(retries):
                try:
                    sent_message = await application.bot.sendMessage(
                        chat_id=admin, text=msg, parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                    # Store the first successful message info for editing later
                    if first_message_info is None and return_message_id:
                        first_message_info = (sent_message.message_id, admin)
                    break
                except Exception as e:  # pylint: disable=broad-except
                    print(f"Failed to send message to admin {admin}: {e}")
    else:
        print("No admins found.")
    
    if return_message_id:
        return first_message_info
    return None


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
    
    try:
        await application.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=new_text,
            parse_mode="HTML"
        )
        return True
    except Exception as e:
        print(f"Failed to edit message: {e}")
        return False


async def send_disable_notification(msg: str, username: str):
    """
    Send a disable notification with an Enable button.
    
    Args:
        msg: The message text to send
        username: The username that was disabled
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = [
        [InlineKeyboardButton(f"✅ Enable {username}", callback_data=f"enable_user:{username}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_logs(msg, reply_markup=reply_markup)


async def send_user_message(msg: str, username: str, device_count: int, has_special_limit: bool, is_except: bool):
    """
    Send a message for a single user with inline buttons for setting limits.
    Only shows buttons if user doesn't have special limit and is not in except list.
    
    Args:
        msg: The message text to send
        username: The username
        device_count: Number of devices the user has
        has_special_limit: Whether user already has a special limit set
        is_except: Whether user is in except list
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram_bot.main import application
    
    admins = await check_admin()
    retries = 2
    
    # Create inline keyboard if user doesn't have special limit and is not except
    reply_markup = None
    if not has_special_limit and not is_except:
        keyboard = [
            [
                InlineKeyboardButton(f"📱 Set {device_count} limit", callback_data=f"set_limit:{username}:{device_count}"),
                InlineKeyboardButton("🚫 Add to except", callback_data=f"add_except:{username}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    if admins:
        for admin in admins:
            for _ in range(retries):
                try:
                    await application.bot.sendMessage(
                        chat_id=admin, 
                        text=msg, 
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                    break
                except Exception as e:
                    print(f"Failed to send user message to admin {admin}: {e}")
