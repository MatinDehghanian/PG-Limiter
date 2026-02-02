"""
Punishment system handlers for the Telegram bot.
Includes functions for managing the smart punishment system.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from telegram_bot.handlers.admin import check_admin_privilege
from telegram_bot.utils import write_json_file
from telegram_bot.constants import CallbackData
from utils.read_config import read_config


async def _send_response(update: Update, text: str, reply_markup=None):
    """
    Helper to send response in both message and callback query contexts.
    """
    if update.callback_query:
        # Don't call answer() here - it's already called in the main callback handler
        try:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception:
            # If edit fails, reply instead
            await update.callback_query.message.reply_html(
                text=text,
                reply_markup=reply_markup
            )
    elif update.message:
        await update.message.reply_html(
            text=text,
            reply_markup=reply_markup
        )


def create_punishment_menu_keyboard(enabled: bool = True):
    """Create punishment menu keyboard with current status."""
    toggle_text = "🔴 Disable" if enabled else "🟢 Enable"
    keyboard = [
        [InlineKeyboardButton(toggle_text, callback_data=CallbackData.PUNISHMENT_TOGGLE)],
        [InlineKeyboardButton("⏰ Set Window", callback_data=CallbackData.PUNISHMENT_WINDOW)],
        [InlineKeyboardButton("📋 Configure Steps", callback_data=CallbackData.PUNISHMENT_STEPS)],
        [InlineKeyboardButton("« Back", callback_data=CallbackData.BACK_SETTINGS)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_window_selection_keyboard(current_hours: int = 72):
    """Create window hours selection keyboard."""
    def btn(hours: int, callback: str):
        mark = "✓ " if hours == current_hours else ""
        return InlineKeyboardButton(f"{mark}{hours}h", callback_data=callback)
    
    keyboard = [
        [
            btn(24, CallbackData.PUNISHMENT_WINDOW_24),
            btn(48, CallbackData.PUNISHMENT_WINDOW_48),
        ],
        [
            btn(72, CallbackData.PUNISHMENT_WINDOW_72),
            btn(168, CallbackData.PUNISHMENT_WINDOW_168),
        ],
        [InlineKeyboardButton("« Back", callback_data=CallbackData.PUNISHMENT_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_steps_menu_keyboard(steps: list):
    """Create steps configuration menu keyboard."""
    keyboard = []
    
    # Show current steps
    for i, step in enumerate(steps):
        step_type = step.get("type", "disable")
        duration = step.get("duration", 0)
        
        if step_type == "warning":
            text = f"{i+1}. ⚠️ Warning"
        elif step_type == "revoke":
            text = f"{i+1}. 🔄 Revoke + Disable"
        elif duration == 0:
            text = f"{i+1}. 🚫 Unlimited"
        else:
            text = f"{i+1}. 🔒 {duration}m"
        
        # Each step is clickable to edit, with a delete button
        keyboard.append([
            InlineKeyboardButton(text, callback_data=f"punishment_edit_step:{i}"),
            InlineKeyboardButton("🗑️", callback_data=f"punishment_remove_step:{i}")
        ])
    
    # Add step button
    if len(steps) < 10:  # Max 10 steps
        keyboard.append([InlineKeyboardButton("➕ Add Step", callback_data=CallbackData.PUNISHMENT_ADD_STEP)])
    
    # Reset to defaults
    keyboard.append([InlineKeyboardButton("🔄 Reset to Defaults", callback_data=CallbackData.PUNISHMENT_STEPS_RESET)])
    
    keyboard.append([InlineKeyboardButton("« Back", callback_data=CallbackData.PUNISHMENT_MENU)])
    
    return InlineKeyboardMarkup(keyboard)


def create_add_step_keyboard():
    """Create keyboard for adding a new step."""
    keyboard = [
        [InlineKeyboardButton("⚠️ Warning", callback_data=CallbackData.PUNISHMENT_STEP_WARNING)],
        [
            InlineKeyboardButton("🔒 10m", callback_data=CallbackData.PUNISHMENT_STEP_DISABLE_10),
            InlineKeyboardButton("🔒 30m", callback_data=CallbackData.PUNISHMENT_STEP_DISABLE_30),
        ],
        [
            InlineKeyboardButton("🔒 60m", callback_data=CallbackData.PUNISHMENT_STEP_DISABLE_60),
            InlineKeyboardButton("🔒 240m", callback_data=CallbackData.PUNISHMENT_STEP_DISABLE_240),
        ],
        [InlineKeyboardButton("🚫 Unlimited", callback_data=CallbackData.PUNISHMENT_STEP_DISABLE_UNLIMITED)],
        [InlineKeyboardButton("🔄 Revoke Sub + Disable", callback_data=CallbackData.PUNISHMENT_STEP_REVOKE)],
        [InlineKeyboardButton("« Back", callback_data=CallbackData.PUNISHMENT_STEPS)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_edit_step_keyboard(step_index: int, step: dict):
    """Create keyboard for editing a specific step."""
    step_type = step.get("type", "disable")
    duration = step.get("duration", 0)
    
    # Show current value with checkmark
    current_text = ""
    if step_type == "warning":
        current_text = "Current: ⚠️ Warning"
    elif step_type == "revoke":
        current_text = "Current: 🔄 Revoke + Disable"
    elif duration == 0:
        current_text = "Current: 🚫 Unlimited"
    else:
        current_text = f"Current: 🔒 {duration}m"
    
    keyboard = [
        # Warning option
        [InlineKeyboardButton(
            "✅ ⚠️ Warning" if step_type == "warning" else "⚠️ Warning",
            callback_data=f"punishment_update_step:{step_index}:warning:0"
        )],
        # Timed disable options
        [
            InlineKeyboardButton(
                "✅ 🔒 10m" if (step_type == "disable" and duration == 10) else "🔒 10m",
                callback_data=f"punishment_update_step:{step_index}:disable:10"
            ),
            InlineKeyboardButton(
                "✅ 🔒 30m" if (step_type == "disable" and duration == 30) else "🔒 30m",
                callback_data=f"punishment_update_step:{step_index}:disable:30"
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ 🔒 60m" if (step_type == "disable" and duration == 60) else "🔒 60m",
                callback_data=f"punishment_update_step:{step_index}:disable:60"
            ),
            InlineKeyboardButton(
                "✅ 🔒 240m" if (step_type == "disable" and duration == 240) else "🔒 240m",
                callback_data=f"punishment_update_step:{step_index}:disable:240"
            ),
        ],
        # Unlimited option
        [InlineKeyboardButton(
            "✅ 🚫 Unlimited" if (step_type == "disable" and duration == 0) else "🚫 Unlimited",
            callback_data=f"punishment_update_step:{step_index}:disable:0"
        )],
        # Revoke subscription option
        [InlineKeyboardButton(
            "✅ 🔄 Revoke Sub + Disable" if step_type == "revoke" else "🔄 Revoke Sub + Disable",
            callback_data=f"punishment_update_step:{step_index}:revoke:0"
        )],
        # Delete this step
        [InlineKeyboardButton("🗑️ Delete This Step", callback_data=f"punishment_remove_step:{step_index}")],
        # Back to steps list
        [InlineKeyboardButton("« Back to Steps", callback_data=CallbackData.PUNISHMENT_STEPS)],
    ]
    return InlineKeyboardMarkup(keyboard)


async def punishment_status(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """
    Shows the current punishment system configuration and status.
    """
    check = await check_admin_privilege(update)
    if check:
        return check

    try:
        from utils.punishment_system import get_punishment_system

        config_data = await read_config()
        system = get_punishment_system()
        system.load_config(config_data)

        enabled_text = "✅ Enabled" if system.enabled else "❌ Disabled"

        steps_text = []
        for i, step in enumerate(system.steps, 1):
            steps_text.append(f"  {i}. {step.get_display_text()}")

        message = (
            f"⚖️ <b>Smart Punishment System</b>\n\n"
            f"Status: {enabled_text}\n"
            f"Time Window: <code>{system.window_hours} hours</code>\n\n"
            f"<b>Punishment Steps:</b>\n"
            f"{chr(10).join(steps_text)}"
        )

        await _send_response(update, message, create_punishment_menu_keyboard(system.enabled))

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def punishment_toggle(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Toggle the punishment system on/off."""
    check = await check_admin_privilege(update)
    if check:
        return check

    try:
        config_data = await read_config()

        if "punishment" not in config_data:
            config_data["punishment"] = {"enabled": True, "window_hours": 72, "steps": []}

        current_state = config_data["punishment"].get("enabled", True)
        config_data["punishment"]["enabled"] = not current_state

        await write_json_file(config_data)

        # Return to punishment menu with updated status
        await punishment_status(update, _context)

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def punishment_set_window(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show window selection menu."""
    check = await check_admin_privilege(update)
    if check:
        return check

    try:
        config_data = await read_config()
        current_hours = config_data.get("punishment", {}).get("window_hours", 72)
        
        message = (
            "⏰ <b>Set Punishment Time Window</b>\n\n"
            f"Current: <code>{current_hours} hours</code>\n\n"
            "Select how long violations should be remembered.\n"
            "Older violations won't count toward punishment steps."
        )
        
        await _send_response(update, message, create_window_selection_keyboard(current_hours))

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def punishment_set_window_hours(update: Update, context: ContextTypes.DEFAULT_TYPE, hours: int):
    """Set the punishment window to specific hours."""
    check = await check_admin_privilege(update)
    if check:
        return check

    try:
        config_data = await read_config()
        
        if "punishment" not in config_data:
            config_data["punishment"] = {"enabled": True, "window_hours": hours, "steps": []}
        else:
            config_data["punishment"]["window_hours"] = hours

        await write_json_file(config_data)
        
        # Return to punishment menu
        await punishment_status(update, context)

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def punishment_set_steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show steps configuration menu."""
    check = await check_admin_privilege(update)
    if check:
        return check

    try:
        config_data = await read_config()
        steps = config_data.get("punishment", {}).get("steps", [])
        
        if not steps:
            # Use default steps for display
            steps = [
                {"type": "warning", "duration": 0},
                {"type": "disable", "duration": 10},
                {"type": "disable", "duration": 30},
                {"type": "disable", "duration": 60},
                {"type": "disable", "duration": 0}
            ]
        
        message = (
            "📋 <b>Configure Punishment Steps</b>\n\n"
            "Steps are applied in order for each violation.\n"
            "Click ➕ to add a step, or 🗑️ to remove one.\n\n"
            "<b>Current Steps:</b>"
        )
        
        await _send_response(update, message, create_steps_menu_keyboard(steps))

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def punishment_add_step_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show menu to add a new step."""
    check = await check_admin_privilege(update)
    if check:
        return check

    message = (
        "➕ <b>Add Punishment Step</b>\n\n"
        "Select the type of punishment to add:\n\n"
        "• <b>Warning</b> - Just send warning, no disable\n"
        "• <b>Timed disable</b> - Disable for set duration\n"
        "• <b>Unlimited</b> - Disable until manual enable\n"
        "• <b>Revoke + Disable</b> - Revoke subscription (changes UUID) and permanently disable"
    )
    
    await _send_response(update, message, create_add_step_keyboard())
    return ConversationHandler.END


async def punishment_add_step(update: Update, context: ContextTypes.DEFAULT_TYPE, step_type: str, duration: int):
    """Add a new punishment step."""
    check = await check_admin_privilege(update)
    if check:
        return check

    try:
        config_data = await read_config()
        
        if "punishment" not in config_data:
            config_data["punishment"] = {"enabled": True, "window_hours": 72, "steps": []}
        
        steps = config_data["punishment"].get("steps", [])
        if not steps:
            # Initialize with empty list
            steps = []
        
        # Add new step
        steps.append({"type": step_type, "duration": duration})
        config_data["punishment"]["steps"] = steps
        
        await write_json_file(config_data)
        
        # Return to steps menu
        await punishment_set_steps(update, context)

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def punishment_remove_step(update: Update, context: ContextTypes.DEFAULT_TYPE, step_index: int):
    """Remove a punishment step by index."""
    check = await check_admin_privilege(update)
    if check:
        return check

    try:
        config_data = await read_config()
        steps = config_data.get("punishment", {}).get("steps", [])
        
        if 0 <= step_index < len(steps):
            steps.pop(step_index)
            
            if "punishment" not in config_data:
                config_data["punishment"] = {"enabled": True, "window_hours": 72, "steps": steps}
            else:
                config_data["punishment"]["steps"] = steps
            
            await write_json_file(config_data)
        
        # Return to steps menu
        await punishment_set_steps(update, context)

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def punishment_edit_step(update: Update, context: ContextTypes.DEFAULT_TYPE, step_index: int):
    """Show edit menu for a specific step."""
    check = await check_admin_privilege(update)
    if check:
        return check

    try:
        config_data = await read_config()
        steps = config_data.get("punishment", {}).get("steps", [])
        
        # Use default steps if none are configured
        if not steps:
            steps = [
                {"type": "warning", "duration": 0},
                {"type": "disable", "duration": 10},
                {"type": "disable", "duration": 30},
                {"type": "disable", "duration": 60},
                {"type": "disable", "duration": 0}
            ]
        
        if 0 <= step_index < len(steps):
            step = steps[step_index]
            step_type = step.get("type", "disable")
            duration = step.get("duration", 0)
            
            # Show current value description
            if step_type == "warning":
                current_desc = "⚠️ Warning (no disable)"
            elif step_type == "revoke":
                current_desc = "🔄 Revoke subscription + Permanent disable"
            elif duration == 0:
                current_desc = "🚫 Unlimited disable"
            else:
                current_desc = f"🔒 Disable for {duration} minutes"
            
            message = (
                f"✏️ <b>Edit Step {step_index + 1}</b>\n\n"
                f"Current: {current_desc}\n\n"
                f"Select a new punishment type:"
            )
            
            await _send_response(update, message, create_edit_step_keyboard(step_index, step))
        else:
            await _send_response(update, "❌ Invalid step index")

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def punishment_update_step(update: Update, context: ContextTypes.DEFAULT_TYPE, step_index: int, step_type: str, duration: int):
    """Update an existing punishment step."""
    check = await check_admin_privilege(update)
    if check:
        return check

    try:
        config_data = await read_config()
        
        if "punishment" not in config_data:
            config_data["punishment"] = {"enabled": True, "window_hours": 72, "steps": []}
        
        steps = config_data["punishment"].get("steps", [])
        
        # Use default steps if none are configured
        if not steps:
            steps = [
                {"type": "warning", "duration": 0},
                {"type": "disable", "duration": 10},
                {"type": "disable", "duration": 30},
                {"type": "disable", "duration": 60},
                {"type": "disable", "duration": 0}
            ]
        
        if 0 <= step_index < len(steps):
            steps[step_index] = {"type": step_type, "duration": duration}
            config_data["punishment"]["steps"] = steps
            await write_json_file(config_data)
        
        # Return to steps menu
        await punishment_set_steps(update, context)

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def punishment_reset_steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset steps to defaults."""
    check = await check_admin_privilege(update)
    if check:
        return check

    try:
        config_data = await read_config()
        
        default_steps = [
            {"type": "warning", "duration": 0},
            {"type": "disable", "duration": 10},
            {"type": "disable", "duration": 30},
            {"type": "disable", "duration": 60},
            {"type": "disable", "duration": 0}
        ]
        
        if "punishment" not in config_data:
            config_data["punishment"] = {"enabled": True, "window_hours": 72, "steps": default_steps}
        else:
            config_data["punishment"]["steps"] = default_steps
        
        await write_json_file(config_data)
        
        # Return to steps menu
        await punishment_set_steps(update, context)

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def user_violations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check violation history for a specific user."""
    check = await check_admin_privilege(update)
    if check:
        return check

    if not context.args:
        await _send_response(
            update,
            "❌ Please provide a username.\n"
            "Example: <code>/user_violations username</code>"
        )
        return ConversationHandler.END

    username = context.args[0]

    try:
        from utils.punishment_system import get_punishment_system

        config_data = await read_config()
        system = get_punishment_system()
        system.load_config(config_data)

        status = system.get_user_status(username)

        if status["violation_count"] == 0:
            await _send_response(
                update,
                f"✅ User <code>{username}</code> has no violations in the last {status['window_hours']} hours."
            )
            return ConversationHandler.END

        violations_text = []
        for v in status["recent_violations"]:
            step_type = "⚠️ Warning" if v["duration"] == 0 and v["step"] == 0 else f"🔒 {v['duration']}m" if v["duration"] > 0 else "🚫 Unlimited"
            violations_text.append(f"  • {v['time_ago']} - Step {v['step'] + 1} ({step_type})")

        message = (
            f"⚖️ <b>Violation History: {username}</b>\n\n"
            f"Total violations: <code>{status['violation_count']}</code>\n"
            f"Window: <code>{status['window_hours']} hours</code>\n\n"
            f"<b>Recent Violations:</b>\n"
            f"{chr(10).join(violations_text)}\n\n"
            f"<b>Next Punishment:</b>\n"
            f"  {status['next_punishment']}"
        )

        await _send_response(update, message)

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def clear_user_violations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear violation history for a specific user."""
    check = await check_admin_privilege(update)
    if check:
        return check

    if not context.args:
        await _send_response(
            update,
            "❌ Please provide a username.\n"
            "Example: <code>/clear_user_violations username</code>\n\n"
            "Use <code>/clear_user_violations ALL</code> to clear all history."
        )
        return ConversationHandler.END

    username = context.args[0]

    try:
        from utils.punishment_system import get_punishment_system

        system = get_punishment_system()

        if username.upper() == "ALL":
            await system.clear_all_history()
            await _send_response(
                update,
                "✅ Cleared all violation history."
            )
        else:
            await system.clear_user_history(username)
            await _send_response(
                update,
                f"✅ Cleared violation history for <code>{username}</code>"
            )

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END
