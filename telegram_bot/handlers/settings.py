"""
Settings handlers for the Telegram bot.
Contains all settings-related handlers for panel, intervals, and configuration.
"""

import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from telegram_bot.constants import (
    CallbackData,
    GET_DOMAIN,
    GET_USERNAME,
    GET_PASSWORD,
    GET_CONFIRMATION,
    SET_COUNTRY_CODE,
    GET_CHECK_INTERVAL,
    GET_TIME_TO_ACTIVE_USERS,
    SET_IPINFO_TOKEN,
)
from telegram_bot.utils import (
    add_base_information,
    read_json_file,
    save_check_interval,
    save_time_to_active_users,
    write_country_code_json,
    write_json_file,
)
from telegram_bot.handlers.admin import check_admin_privilege
from telegram_bot.keyboards import (
    create_back_to_main_keyboard,
    create_settings_menu_keyboard,
)
from utils.read_config import read_config, save_config_value


def create_back_to_settings_keyboard():
    """Create a keyboard with only a back to settings button."""
    keyboard = [
        [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_country_keyboard():
    """Create country code options keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🇮🇷 Iran", callback_data=CallbackData.COUNTRY_IR),
            InlineKeyboardButton("🇷🇺 Russia", callback_data=CallbackData.COUNTRY_RU),
        ],
        [
            InlineKeyboardButton("🇨🇳 China", callback_data=CallbackData.COUNTRY_CN),
            InlineKeyboardButton("🌐 None", callback_data=CallbackData.COUNTRY_NONE),
        ],
        [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_interval_keyboard():
    """Create check interval options keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("2 min", callback_data=CallbackData.INTERVAL_120),
            InlineKeyboardButton("3 min", callback_data=CallbackData.INTERVAL_180),
            InlineKeyboardButton("4 min", callback_data=CallbackData.INTERVAL_240),
        ],
        [InlineKeyboardButton("✏️ Custom", callback_data=CallbackData.INTERVAL_CUSTOM)],
        [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_time_to_active_keyboard():
    """Create time to active options keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("5 min", callback_data=CallbackData.TIME_300),
            InlineKeyboardButton("10 min", callback_data=CallbackData.TIME_600),
            InlineKeyboardButton("15 min", callback_data=CallbackData.TIME_900),
        ],
        [InlineKeyboardButton("✏️ Custom", callback_data=CallbackData.TIME_CUSTOM)],
        [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_enhanced_details_keyboard():
    """Create enhanced details toggle keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✅ ON", callback_data=CallbackData.ENHANCED_ON),
            InlineKeyboardButton("❌ OFF", callback_data=CallbackData.ENHANCED_OFF),
        ],
        [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_single_ip_keyboard():
    """Create single IP users toggle keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✅ ON", callback_data=CallbackData.SINGLE_IP_ON),
            InlineKeyboardButton("❌ OFF", callback_data=CallbackData.SINGLE_IP_OFF),
        ],
        [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


# ═══════════════════════════════════════════════════════════════════════════════
# PANEL SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════


async def set_panel_domain(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Add panel domain, username, and password to the config file."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    
    # Check if environment variables are already set
    from utils.read_config import load_env_config
    env_config = load_env_config()
    panel_config = env_config.get("panel", {})
    domain = panel_config.get("domain")
    password = panel_config.get("password")
    
    if domain and password:
        await update.message.reply_html(
            text="⚠️ Panel credentials are stored in <code>.env</code> file.\n"
            + "To change them, edit the .env file or use:\n"
            + "<code>pg-limiter config</code>\n\n"
            + f"<b>Current domain:</b> <code>{domain}</code>"
        )
        return ConversationHandler.END
    
    await update.message.reply_html(
        text="Send your <b>panel address</b>\n"
        + "Format: <code>sub.domain.com:8333</code>\n"
        + "<b>without</b> <code>https://</code> or <code>http://</code>",
    )
    return GET_DOMAIN


async def get_domain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get panel domain from user"""
    context.user_data["domain"] = update.message.text.strip()
    await update.message.reply_text("Send Your Username: (For example: 'admin')")
    return GET_USERNAME


async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get panel username from user"""
    context.user_data["username"] = update.message.text.strip()
    await update.message.reply_text("Send Your Password:")
    return GET_PASSWORD


async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get panel password from user and save config"""
    context.user_data["password"] = update.message.text.strip()
    await update.message.reply_text("Please wait to check panel credentials...")
    try:
        await add_base_information(
            context.user_data["domain"],
            context.user_data["password"],
            context.user_data["username"],
        )
        await update.message.reply_text("Config saved successfully 🎊")
    except ValueError:
        await update.message.reply_html(
            text="<b>Error with your information!</b>\n"
            + f"Domain: <code>{context.user_data['domain']}</code>\n"
            + f"Username: <code>{context.user_data['username']}</code>\n"
            + "Try again /create_config",
        )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK INTERVAL SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════


async def set_check_interval(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Get the 'check_interval' variable"""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    await update.message.reply_text(
        "Please send the check interval time in seconds (recommended: 240)"
    )
    return GET_CHECK_INTERVAL


async def check_interval_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Save the 'check_interval' variable"""
    try:
        check_interval = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_html(
            text=f"Wrong input: <code>{update.message.text.strip()}</code>\n"
            + "try again <b>/set_check_interval</b>"
        )
        return ConversationHandler.END
    await save_check_interval(check_interval)
    await update.message.reply_text(f"CHECK_INTERVAL set to {check_interval}")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
# TIME TO ACTIVE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════


async def set_time_to_active(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Get the 'time_to_active' variable"""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    await update.message.reply_text(
        "Please send the time to active users in seconds (e.g., 600)"
    )
    return GET_TIME_TO_ACTIVE_USERS


async def time_to_active_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Save the 'time_to_active' variable"""
    try:
        time_to_active_users = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_html(
            text=f"Wrong input: <code>{update.message.text.strip()}</code>\n"
            + "try again <b>/set_time_to_active_users</b>"
        )
        return ConversationHandler.END
    await save_time_to_active_users(time_to_active_users)
    await update.message.reply_text(f"TIME_TO_ACTIVE_USERS set to {time_to_active_users}")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
# COUNTRY CODE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════


async def set_country_code(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Set the country code for the bot."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    await update.message.reply_html(
        "Select country code:\n"
        + "1. <code>IR</code> (Iran)\n"
        + "2. <code>RU</code> (Russia)\n"
        + "3. <code>CN</code> (China)\n"
        + "4. <code>None</code>\n"
        + "Send number: <code>1</code>, <code>2</code>, <code>3</code>, or <code>4</code>"
    )
    return SET_COUNTRY_CODE


async def country_code_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Write the country code to the config file."""
    country_code = update.message.text.strip()
    country_codes = {"1": "IR", "2": "RU", "3": "CN", "4": "None"}
    selected_country = country_codes.get(country_code, "None")
    await write_country_code_json(selected_country)
    await update.message.reply_html(
        f"Country code <code>{selected_country}</code> set successfully!"
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
# IPINFO TOKEN SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════


async def set_ipinfo_token(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Set the ipinfo.io API token."""
    check = await check_admin_privilege(update)
    if check is not None:
        return check
    await update.message.reply_html(
        "Send your ipinfo.io API token:\n\n"
        + "Get one at https://ipinfo.io\n"
        + "Or send <code>remove</code> to remove the token"
    )
    return SET_IPINFO_TOKEN


async def ipinfo_token_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Write the ipinfo.io token to the config file."""
    token = update.message.text.strip()
    
    if token.lower() == "remove":
        await save_ipinfo_token("")
        await update.message.reply_html("✅ IPINFO_TOKEN removed!")
        return ConversationHandler.END
    
    if len(token) < 10:
        await update.message.reply_html(
            "❌ Invalid token format!\nTry again with <b>/set_ipinfo_token</b>"
        )
        return ConversationHandler.END
    
    await save_ipinfo_token(token)
    await update.message.reply_html("✅ IPINFO_TOKEN set successfully!")
    return ConversationHandler.END


async def save_ipinfo_token(token: str):
    """Save the ipinfo.io token to the config file."""
    try:
        config = await read_json_file()
        if "api" not in config:
            config["api"] = {}
        config["api"]["ipinfo_token"] = token
        await write_json_file(config)
        return True
    except Exception as e:
        print(f"Error saving ipinfo token: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════


async def handle_settings_menu_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for settings menu display."""
    await query.edit_message_text(
        text="⚙️ <b>Settings Menu</b>\n\nConfigure your bot settings:",
        reply_markup=create_settings_menu_keyboard(),
        parse_mode="HTML"
    )


async def handle_country_menu_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for country menu display."""
    await query.edit_message_text(
        text="🌍 <b>Select Country</b>\n\nOnly IPs from the selected country will be counted:",
        reply_markup=create_country_keyboard(),
        parse_mode="HTML"
    )


async def handle_country_selection_callback(query, _context: ContextTypes.DEFAULT_TYPE, country_code: str):
    """Handle callback for country selection."""
    country_names = {"IR": "🇮🇷 Iran", "RU": "🇷🇺 Russia", "CN": "🇨🇳 China", "None": "🌐 None"}
    await write_country_code_json(country_code)
    await query.edit_message_text(
        text=f"✅ Country set to <b>{country_names.get(country_code, country_code)}</b>",
        reply_markup=create_back_to_main_keyboard(),
        parse_mode="HTML"
    )


async def handle_interval_menu_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for interval menu display."""
    await query.edit_message_text(
        text="⏱️ <b>Check Interval</b>\n\nHow often should the bot check users:",
        reply_markup=create_interval_keyboard(),
        parse_mode="HTML"
    )


async def handle_interval_preset_callback(query, _context: ContextTypes.DEFAULT_TYPE, interval: int):
    """Handle callback for interval preset selection."""
    await save_check_interval(interval)
    await query.edit_message_text(
        text=f"✅ Check interval set to <b>{interval} seconds</b> ({interval // 60} min)",
        reply_markup=create_back_to_main_keyboard(),
        parse_mode="HTML"
    )


async def handle_interval_custom_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for custom interval input."""
    context.user_data["waiting_for"] = "check_interval"
    await query.edit_message_text(
        text="⏱️ <b>Custom Check Interval</b>\n\nSend the interval in seconds:",
        parse_mode="HTML"
    )


async def handle_time_menu_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for time to active menu display."""
    await query.edit_message_text(
        text="⏰ <b>Time to Active</b>\n\nHow long users stay active:",
        reply_markup=create_time_to_active_keyboard(),
        parse_mode="HTML"
    )


async def handle_time_preset_callback(query, _context: ContextTypes.DEFAULT_TYPE, time_val: int):
    """Handle callback for time preset selection."""
    await save_time_to_active_users(time_val)
    await query.edit_message_text(
        text=f"✅ Time to active set to <b>{time_val} seconds</b> ({time_val // 60} min)",
        reply_markup=create_back_to_main_keyboard(),
        parse_mode="HTML"
    )


async def handle_time_custom_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for custom time input."""
    context.user_data["waiting_for"] = "time_to_active"
    await query.edit_message_text(
        text="⏰ <b>Custom Time to Active</b>\n\nSend the time in seconds:",
        parse_mode="HTML"
    )


async def handle_enhanced_menu_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for enhanced details menu display."""
    try:
        config = await read_config()
        value = config.get("enhanced_details", True)
        status = "ON ✅" if value else "OFF ❌"
    except Exception:
        status = "Unknown"
    await query.edit_message_text(
        text=f"📋 <b>Enhanced Details</b>\n\nCurrently: <b>{status}</b>\n\n"
             + "• <b>ON</b>: Shows node names, IDs, and protocols\n"
             + "• <b>OFF</b>: Shows only IP addresses",
        reply_markup=create_enhanced_details_keyboard(),
        parse_mode="HTML"
    )


async def handle_enhanced_toggle_callback(query, _context: ContextTypes.DEFAULT_TYPE, enable: bool):
    """Handle callback for enhanced details toggle."""
    try:
        await save_config_value("enhanced_details", str(enable).lower())
        status = "ON ✅" if enable else "OFF ❌"
        await query.edit_message_text(
            text=f"📋 <b>Enhanced Details</b>\n\nCurrently: <b>{status}</b>\n\n"
                 + "• <b>ON</b>: Shows node names, IDs, and protocols\n"
                 + "• <b>OFF</b>: Shows only IP addresses",
            reply_markup=create_enhanced_details_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error: {e}",
            reply_markup=create_back_to_main_keyboard(),
            parse_mode="HTML"
        )


async def handle_single_ip_menu_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for single IP menu display."""
    try:
        config = await read_config()
        value = config.get("show_single_ip_users", False)
        status = "ON ✅" if value else "OFF ❌"
    except Exception:
        status = "Unknown"
    await query.edit_message_text(
        text=f"1️⃣ <b>Single IP Users</b>\n\nCurrently: <b>{status}</b>\n\n"
             + "• <b>ON</b>: Include users with 1 IP in reports\n"
             + "• <b>OFF</b>: Only show users with multiple IPs",
        reply_markup=create_single_ip_keyboard(),
        parse_mode="HTML"
    )


async def handle_single_ip_toggle_callback(query, _context: ContextTypes.DEFAULT_TYPE, enable: bool):
    """Handle callback for single IP toggle."""
    try:
        await save_config_value("show_single_ip_users", str(enable).lower())
        status = "ON ✅" if enable else "OFF ❌"
        await query.edit_message_text(
            text=f"1️⃣ <b>Single IP Users</b>\n\nCurrently: <b>{status}</b>\n\n"
                 + "• <b>ON</b>: Include users with 1 IP in reports\n"
                 + "• <b>OFF</b>: Only show users with multiple IPs",
            reply_markup=create_single_ip_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error: {e}",
            reply_markup=create_back_to_main_keyboard(),
            parse_mode="HTML"
        )


async def handle_ipinfo_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for IPInfo token input."""
    context.user_data["waiting_for"] = "ipinfo_token"
    await query.edit_message_text(
        text="🔑 <b>IPInfo Token</b>\n\n"
             + "Send your ipinfo.io API token:\n\n"
             + "Get one at: https://ipinfo.io\n\n"
             + "Or send <code>remove</code> to remove the token\n\n"
             + "<i>Or click Back to cancel.</i>",
        reply_markup=create_back_to_main_keyboard(),
        parse_mode="HTML"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT MESSAGE HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════


async def handle_check_interval_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for check interval."""
    text = update.message.text.strip()
    try:
        interval = int(text)
        await save_check_interval(interval)
        await update.message.reply_html(
            text=f"✅ Check interval set to <b>{interval} seconds</b>",
            reply_markup=create_back_to_main_keyboard()
        )
    except ValueError:
        await update.message.reply_html(
            text="❌ Invalid number.",
            reply_markup=create_back_to_main_keyboard()
        )
    context.user_data["waiting_for"] = None


async def handle_time_to_active_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for time to active."""
    text = update.message.text.strip()
    try:
        time_val = int(text)
        await save_time_to_active_users(time_val)
        await update.message.reply_html(
            text=f"✅ Time to active set to <b>{time_val} seconds</b>",
            reply_markup=create_back_to_main_keyboard()
        )
    except ValueError:
        await update.message.reply_html(
            text="❌ Invalid number.",
            reply_markup=create_back_to_main_keyboard()
        )
    context.user_data["waiting_for"] = None


async def handle_ipinfo_token_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for IPInfo token."""
    text = update.message.text.strip()
    if text.lower() == "remove":
        await save_ipinfo_token("")
        await update.message.reply_html(
            text="✅ IPInfo token removed!",
            reply_markup=create_back_to_main_keyboard()
        )
    elif len(text) < 10:
        await update.message.reply_html(
            text="❌ Invalid token format!",
            reply_markup=create_back_to_main_keyboard()
        )
    else:
        await save_ipinfo_token(text)
        await update.message.reply_html(
            text="✅ IPInfo token set successfully!",
            reply_markup=create_back_to_main_keyboard()
        )
    context.user_data["waiting_for"] = None

# ═══════════════════════════════════════════════════════════════════════════════
# DISABLE METHOD HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════


async def _get_groups_from_panel():
    """Helper to get groups from panel."""
    try:
        from utils.user_group_filter import get_all_groups
        from utils.types import PanelType
        
        config_data = await read_config()
        panel_config = config_data.get("panel", {})
        panel_data = PanelType(
            panel_config.get("username", ""),
            panel_config.get("password", ""),
            panel_config.get("domain", "")
        )
        
        groups = await get_all_groups(panel_data)
        return groups, config_data
    except Exception as e:
        return [], {}


def create_disable_group_keyboard(groups: list, current_group_id: int = None):
    """Create keyboard for selecting disabled group."""
    keyboard = []
    
    for group in groups:
        gid = group.get("id", 0)
        name = group.get("name", "Unknown")
        is_selected = gid == current_group_id
        prefix = "✅" if is_selected else "⬜"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{prefix} {name} (ID: {gid})",
                callback_data=f"select_disabled_group:{gid}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data=CallbackData.DISABLE_BY_GROUP)])
    keyboard.append([InlineKeyboardButton("« Back to Disable Method", callback_data=CallbackData.DISABLE_METHOD_MENU)])
    
    return InlineKeyboardMarkup(keyboard)


async def handle_disable_by_group_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for selecting group to use for disabled users."""
    from telegram.error import BadRequest
    
    groups, config_data = await _get_groups_from_panel()
    
    if not groups:
        try:
            await query.edit_message_text(
                text="📁 <b>Disable by Group</b>\n\n"
                     "❌ Could not load groups from panel.\n"
                     "Please check your panel connection.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Retry", callback_data=CallbackData.DISABLE_BY_GROUP)],
                    [InlineKeyboardButton("« Back", callback_data=CallbackData.DISABLE_METHOD_MENU)]
                ]),
                parse_mode="HTML"
            )
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return
    
    # Get current disabled group ID
    current_group_id = config_data.get("disabled_group_id")
    if current_group_id:
        try:
            current_group_id = int(current_group_id)
        except (ValueError, TypeError):
            current_group_id = None
    
    keyboard = create_disable_group_keyboard(groups, current_group_id)
    
    try:
        await query.edit_message_text(
            text="📁 <b>Disable by Group</b>\n\n"
                 "Select the group where disabled users will be moved:\n\n"
                 "<i>When a user exceeds their IP limit, they will be moved to this group.</i>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


async def handle_select_disabled_group_callback(query, _context: ContextTypes.DEFAULT_TYPE, group_id: int):
    """Handle callback for selecting specific disabled group."""
    try:
        await save_config_value("disable_method", "group")
        await save_config_value("disabled_group_id", str(group_id))
        
        # Get group name for confirmation
        groups, _ = await _get_groups_from_panel()
        group_name = "Unknown"
        for group in groups:
            if group.get("id") == group_id:
                group_name = group.get("name", "Unknown")
                break
        
        await query.edit_message_text(
            text=f"✅ <b>Disable Method Updated</b>\n\n"
                 f"Method: <b>By Group</b>\n"
                 f"Group: <b>{group_name}</b> (ID: {group_id})\n\n"
                 f"Users exceeding IP limits will be moved to this group.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)]
            ]),
            parse_mode="HTML"
        )
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=CallbackData.DISABLE_BY_GROUP)]
            ]),
            parse_mode="HTML"
        )
