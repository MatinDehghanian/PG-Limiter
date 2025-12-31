"""
Punishment system handlers for the Telegram bot.
Includes functions for managing the smart punishment system.
"""

import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from telegram_bot.handlers.admin import check_admin_privilege
from telegram_bot.utils import write_json_file
from telegram_bot.keyboards import create_back_to_main_keyboard
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


def create_punishment_menu_keyboard():
    """Create punishment menu keyboard."""
    from telegram_bot.constants import CallbackData
    keyboard = [
        [InlineKeyboardButton("🔄 Toggle On/Off", callback_data=CallbackData.PUNISHMENT_TOGGLE)],
        [InlineKeyboardButton("⏰ Set Window", callback_data=CallbackData.PUNISHMENT_WINDOW)],
        [InlineKeyboardButton("📋 Configure Steps", callback_data=CallbackData.PUNISHMENT_STEPS)],
        [InlineKeyboardButton("« Back", callback_data=CallbackData.BACK_MAIN)],
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
            f"{chr(10).join(steps_text)}\n\n"
            f"<b>Commands:</b>\n"
            f"/punishment_toggle - Enable/disable\n"
            f"/punishment_set_window - Set time window\n"
            f"/punishment_set_steps - Configure steps\n"
            f"/user_violations &lt;username&gt; - Check user\n"
            f"/clear_user_violations &lt;username&gt; - Clear history"
        )

        await _send_response(update, message, create_punishment_menu_keyboard())

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

        new_state = "✅ Enabled" if not current_state else "❌ Disabled"
        await _send_response(
            update,
            f"⚖️ Punishment system is now: {new_state}",
            create_back_to_main_keyboard()
        )

    except Exception as e:
        await _send_response(update, f"❌ Error: {str(e)}")

    return ConversationHandler.END


async def punishment_set_window(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the punishment time window."""
    check = await check_admin_privilege(update)
    if check:
        return check

    # Check if hours provided as argument
    if context.args:
        try:
            hours = int(context.args[0])
            if hours < 1 or hours > 720:  # Max 30 days
                await _send_response(
                    update,
                    "❌ Invalid value. Hours must be between 1 and 720."
                )
                return ConversationHandler.END

            config_data = await read_config()
            if "punishment" not in config_data:
                config_data["punishment"] = {"enabled": True, "window_hours": hours, "steps": []}
            else:
                config_data["punishment"]["window_hours"] = hours

            await write_json_file(config_data)
            await _send_response(
                update,
                f"✅ Punishment time window set to <code>{hours} hours</code>\n"
                f"Violations older than this will be forgotten.",
                create_back_to_main_keyboard()
            )
            return ConversationHandler.END
        except ValueError:
            pass

    await _send_response(
        update,
        "⚖️ <b>Set Punishment Time Window</b>\n\n"
        "Enter the number of hours for the violation window.\n"
        "Violations older than this will not count.\n\n"
        "Example: <code>/punishment_set_window 72</code> (3 days)"
    )
    return ConversationHandler.END


async def punishment_set_steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configure punishment steps."""
    check = await check_admin_privilege(update)
    if check:
        return check

    # Check if JSON provided as argument
    if context.args:
        try:
            steps_json = " ".join(context.args)
            steps_data = json.loads(steps_json)

            if not isinstance(steps_data, list) or len(steps_data) == 0:
                raise ValueError("Steps must be a non-empty array")

            # Validate each step
            validated_steps = []
            for step in steps_data:
                step_type = step.get("type", "disable")
                duration = step.get("duration", 0)
                if step_type not in ["warning", "disable"]:
                    raise ValueError(f"Invalid step type: {step_type}")
                if not isinstance(duration, int) or duration < 0:
                    raise ValueError(f"Invalid duration: {duration}")
                validated_steps.append({"type": step_type, "duration": duration})

            config_data = await read_config()
            if "punishment" not in config_data:
                config_data["punishment"] = {"enabled": True, "window_hours": 72, "steps": validated_steps}
            else:
                config_data["punishment"]["steps"] = validated_steps

            await write_json_file(config_data)

            steps_display = []
            for i, s in enumerate(validated_steps, 1):
                if s["type"] == "warning":
                    steps_display.append(f"  {i}. ⚠️ Warning")
                elif s["duration"] == 0:
                    steps_display.append(f"  {i}. 🚫 Unlimited disable")
                else:
                    steps_display.append(f"  {i}. 🔒 {s['duration']} min disable")

            await _send_response(
                update,
                f"✅ Punishment steps updated:\n\n{chr(10).join(steps_display)}",
                create_back_to_main_keyboard()
            )
            return ConversationHandler.END
        except (json.JSONDecodeError, ValueError) as e:
            await _send_response(update, f"❌ Invalid format: {str(e)}")
            return ConversationHandler.END

    await _send_response(
        update,
        "⚖️ <b>Configure Punishment Steps</b>\n\n"
        "Send steps as JSON array:\n"
        '<code>/punishment_set_steps [{"type":"warning","duration":0},{"type":"disable","duration":15},{"type":"disable","duration":60},{"type":"disable","duration":0}]</code>\n\n'
        "<b>Step types:</b>\n"
        "• <code>warning</code> - Just warn, don't disable\n"
        "• <code>disable</code> - Disable user\n\n"
        "<b>Duration (minutes):</b>\n"
        "• <code>0</code> = Unlimited (for warning: ignored, for disable: permanent)\n"
        "• <code>15</code> = 15 minutes\n"
        "• <code>60</code> = 1 hour\n"
        "• <code>240</code> = 4 hours"
    )
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
