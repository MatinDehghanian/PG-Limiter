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
    from telegram_bot.keyboards import create_disable_method_keyboard
    
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
            text="🚫 <b>Disable Method</b>\n\n"
                 f"✅ Method set to <b>By Group</b>\n"
                 f"Group: <b>{group_name}</b> (ID: {group_id})\n\n"
                 "• <b>By Status</b>: Set user status to 'disabled'\n"
                 "• <b>By Group</b>: Move user to a disabled group",
            reply_markup=create_disable_method_keyboard("group", group_name),
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


# ═══════════════════════════════════════════════════════════════════════════════
# FALLBACK GROUP HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════


def create_fallback_group_keyboard(groups: list, current_group_id: int = None):
    """Create keyboard for selecting fallback group."""
    keyboard = []
    
    for group in groups:
        gid = group.get("id", 0)
        name = group.get("name", "Unknown")
        is_selected = gid == current_group_id
        prefix = "✅" if is_selected else "⬜"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{prefix} {name} (ID: {gid})",
                callback_data=f"select_fallback_group:{gid}"
            )
        ])
    
    # Add option to clear fallback group
    if current_group_id:
        keyboard.append([InlineKeyboardButton("❌ Clear Fallback Group", callback_data=CallbackData.CLEAR_FALLBACK_GROUP)])
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data=CallbackData.FALLBACK_GROUP_MENU)])
    keyboard.append([InlineKeyboardButton("« Back to Disable Method", callback_data=CallbackData.DISABLE_METHOD_MENU)])
    
    return InlineKeyboardMarkup(keyboard)


async def handle_fallback_group_menu_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for selecting fallback group."""
    from telegram.error import BadRequest
    
    groups, config_data = await _get_groups_from_panel()
    
    if not groups:
        try:
            await query.edit_message_text(
                text="🔄 <b>Fallback Group</b>\n\n"
                     "❌ Could not load groups from panel.\n"
                     "Please check your panel connection.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Retry", callback_data=CallbackData.FALLBACK_GROUP_MENU)],
                    [InlineKeyboardButton("« Back", callback_data=CallbackData.DISABLE_METHOD_MENU)]
                ]),
                parse_mode="HTML"
            )
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return
    
    # Get current fallback group ID
    current_group_id = config_data.get("fallback_group_id")
    if current_group_id:
        try:
            current_group_id = int(current_group_id)
        except (ValueError, TypeError):
            current_group_id = None
    
    keyboard = create_fallback_group_keyboard(groups, current_group_id)
    
    current_name = "Not set"
    if current_group_id:
        for group in groups:
            if group.get("id") == current_group_id:
                current_name = group.get("name", "Unknown")
                break
    
    try:
        await query.edit_message_text(
            text="🔄 <b>Fallback Group</b>\n\n"
                 f"Current: <b>{current_name}</b>\n\n"
                 "Select the group that will be assigned to users when:\n"
                 "• Their original groups cannot be found when re-enabling\n"
                 "• All active users should have this group\n\n"
                 "<i>This ensures all enabled users have at least one valid group.</i>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


async def handle_select_fallback_group_callback(query, _context: ContextTypes.DEFAULT_TYPE, group_id: int):
    """Handle callback for selecting specific fallback group."""
    from telegram_bot.keyboards import create_disable_method_keyboard
    
    try:
        await save_config_value("fallback_group_id", str(group_id))
        
        # Get group name for confirmation
        groups, config_data = await _get_groups_from_panel()
        group_name = "Unknown"
        disabled_group_name = None
        for group in groups:
            if group.get("id") == group_id:
                group_name = group.get("name", "Unknown")
            disabled_group_id = config_data.get("disabled_group_id")
            if disabled_group_id and group.get("id") == int(disabled_group_id):
                disabled_group_name = group.get("name", "Unknown")
        
        current_method = config_data.get("disable_method", "status")
        
        await query.edit_message_text(
            text="🚫 <b>Disable Method</b>\n\n"
                 f"✅ Fallback group set to <b>{group_name}</b> (ID: {group_id})\n\n"
                 "• <b>By Status</b>: Set user status to 'disabled'\n"
                 "• <b>By Group</b>: Move user to a disabled group\n"
                 "• <b>Fallback Group</b>: Default group for re-enabled users",
            reply_markup=create_disable_method_keyboard(current_method, disabled_group_name, group_name),
            parse_mode="HTML"
        )
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=CallbackData.FALLBACK_GROUP_MENU)]
            ]),
            parse_mode="HTML"
        )


async def handle_clear_fallback_group_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for clearing fallback group."""
    from telegram_bot.keyboards import create_disable_method_keyboard
    
    try:
        await save_config_value("fallback_group_id", "")
        
        groups, config_data = await _get_groups_from_panel()
        current_method = config_data.get("disable_method", "status")
        disabled_group_name = None
        disabled_group_id = config_data.get("disabled_group_id")
        if disabled_group_id:
            for group in groups:
                if group.get("id") == int(disabled_group_id):
                    disabled_group_name = group.get("name", "Unknown")
                    break
        
        await query.edit_message_text(
            text="🚫 <b>Disable Method</b>\n\n"
                 "✅ Fallback group has been cleared.\n\n"
                 "• <b>By Status</b>: Set user status to 'disabled'\n"
                 "• <b>By Group</b>: Move user to a disabled group\n"
                 "• <b>Fallback Group</b>: Default group for re-enabled users",
            reply_markup=create_disable_method_keyboard(current_method, disabled_group_name, None),
            parse_mode="HTML"
        )
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=CallbackData.FALLBACK_GROUP_MENU)]
            ]),
            parse_mode="HTML"
        )


def create_user_sync_keyboard(current_interval: int):
    """Create keyboard for user sync interval settings."""
    keyboard = []
    
    intervals = [
        (1, "1 minute"),
        (5, "5 minutes"),
        (10, "10 minutes"),
        (15, "15 minutes"),
    ]
    
    for value, label in intervals:
        prefix = "✅" if current_interval == value else "⬜"
        callback = getattr(CallbackData, f"USER_SYNC_{value}")
        keyboard.append([InlineKeyboardButton(f"{prefix} {label}", callback_data=callback)])
    
    keyboard.append([InlineKeyboardButton("🔄 Sync Now", callback_data=CallbackData.USER_SYNC_NOW)])
    keyboard.append([InlineKeyboardButton("🗑️ Review Pending Deletions", callback_data=CallbackData.USER_SYNC_PENDING)])
    keyboard.append([InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)])
    
    return InlineKeyboardMarkup(keyboard)


async def handle_user_sync_menu_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for user sync menu."""
    from telegram.error import BadRequest
    
    config_data = await read_config()
    current_interval = config_data.get("user_sync_interval", 5)
    
    # Get last sync time
    try:
        from utils.user_sync import get_last_sync_time
        last_sync = await get_last_sync_time()
        if last_sync:
            sync_status = f"Last sync: <code>{last_sync.strftime('%H:%M:%S')}</code>"
        else:
            sync_status = "Last sync: <i>Never</i>"
    except Exception:
        sync_status = "Last sync: <i>Unknown</i>"
    
    keyboard = create_user_sync_keyboard(current_interval)
    
    try:
        await query.edit_message_text(
            text=f"🔄 <b>User Sync Settings</b>\n\n"
                 f"Periodically syncs user data from panel to local database\n"
                 f"for faster group/admin filtering.\n\n"
                 f"<b>Current interval:</b> {current_interval} minutes\n"
                 f"{sync_status}\n\n"
                 f"Select sync interval:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


async def handle_user_sync_interval_callback(query, _context: ContextTypes.DEFAULT_TYPE, interval: int):
    """Handle callback for setting user sync interval."""
    from utils.read_config import invalidate_config_cache
    
    try:
        await save_config_value("user_sync_interval", str(interval))
        await invalidate_config_cache()
        
        # Refresh the menu
        await handle_user_sync_menu_callback(query, _context)
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=CallbackData.USER_SYNC_MENU)]
            ]),
            parse_mode="HTML"
        )


async def handle_user_sync_now_callback(query, _context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for immediate user sync."""
    try:
        await query.edit_message_text(
            text="🔄 <b>Syncing users from panel...</b>\n\n"
                 "<i>This may take a moment...</i>",
            parse_mode="HTML"
        )
        
        # Perform sync
        from utils.user_sync import sync_users_to_database
        from utils.read_config import read_config
        from utils.types import PanelType
        
        config_data = await read_config()
        panel_config = config_data.get("panel", {})
        panel_data = PanelType(
            panel_config.get("username", ""),
            panel_config.get("password", ""),
            panel_config.get("domain", "")
        )
        
        synced, errors, deleted = await sync_users_to_database(panel_data)
        
        # Build result message
        result_lines = [
            f"Synced: <code>{synced}</code> users",
            f"Errors: <code>{errors}</code>",
        ]
        if deleted > 0:
            result_lines.append(f"Deleted: <code>{deleted}</code> users (removed from panel)")
        
        await query.edit_message_text(
            text=f"✅ <b>User Sync Complete</b>\n\n"
                 + "\n".join(result_lines) + "\n\n"
                 f"User data is now cached locally for faster filtering.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Sync Again", callback_data=CallbackData.USER_SYNC_NOW)],
                [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)]
            ]),
            parse_mode="HTML"
        )
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Sync Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Retry", callback_data=CallbackData.USER_SYNC_NOW)],
                [InlineKeyboardButton("« Back", callback_data=CallbackData.USER_SYNC_MENU)]
            ]),
            parse_mode="HTML"
        )


async def handle_pending_deletions_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for reviewing pending user deletions."""
    try:
        await query.edit_message_text(
            text="🔍 <b>Checking pending deletions...</b>\n\n"
                 "<i>Comparing local database with panel...</i>",
            parse_mode="HTML"
        )
        
        from utils.user_sync import get_pending_deletions
        from utils.types import PanelType
        
        config_data = await read_config()
        panel_config = config_data.get("panel", {})
        panel_data = PanelType(
            panel_config.get("username", ""),
            panel_config.get("password", ""),
            panel_config.get("domain", "")
        )
        
        result = await get_pending_deletions(panel_data)
        pending = result["pending_deletions"]
        
        if not pending:
            await query.edit_message_text(
                text="✅ <b>No Pending Deletions</b>\n\n"
                     f"Local users: <code>{result['local_count']}</code>\n"
                     f"Panel users: <code>{result['panel_count']}</code>\n\n"
                     "All local users exist in the panel.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh", callback_data=CallbackData.USER_SYNC_PENDING)],
                    [InlineKeyboardButton("« Back", callback_data=CallbackData.USER_SYNC_MENU)]
                ]),
                parse_mode="HTML"
            )
            return
        
        # Build user list (limit to 30 for display)
        display_limit = 30
        if len(pending) <= display_limit:
            user_list = "\n".join(f"• <code>{u}</code>" for u in pending)
        else:
            user_list = "\n".join(f"• <code>{u}</code>" for u in pending[:display_limit])
            user_list += f"\n... and {len(pending) - display_limit} more"
        
        # Store pending list in context for force delete
        context.user_data["pending_deletions"] = pending
        
        status_icon = "⚠️" if not result["safe_to_delete"] else "📋"
        safety_note = ""
        if not result["safe_to_delete"]:
            safety_note = f"\n\n⚠️ <b>Safety Warning:</b>\n{result['reason']}"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data=CallbackData.USER_SYNC_PENDING)]
        ]
        
        # Only show force delete if there are pending deletions
        if pending:
            keyboard.append([InlineKeyboardButton(
                f"🗑️ Force Delete All ({len(pending)} users)", 
                callback_data=CallbackData.USER_SYNC_FORCE_DELETE
            )])
        
        keyboard.append([InlineKeyboardButton("« Back", callback_data=CallbackData.USER_SYNC_MENU)])
        
        await query.edit_message_text(
            text=f"{status_icon} <b>Pending Deletions</b>\n\n"
                 f"Local users: <code>{result['local_count']}</code>\n"
                 f"Panel users: <code>{result['panel_count']}</code>\n"
                 f"Would delete: <code>{len(pending)}</code> ({result['deletion_percentage']:.1f}%)\n"
                 f"{safety_note}\n\n"
                 f"<b>Users not in panel:</b>\n{user_list}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Retry", callback_data=CallbackData.USER_SYNC_PENDING)],
                [InlineKeyboardButton("« Back", callback_data=CallbackData.USER_SYNC_MENU)]
            ]),
            parse_mode="HTML"
        )


async def handle_force_delete_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for force deleting pending users."""
    try:
        pending = context.user_data.get("pending_deletions", [])
        
        if not pending:
            await query.edit_message_text(
                text="⚠️ No pending deletions found.\n\n"
                     "Please refresh the pending deletions list first.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh", callback_data=CallbackData.USER_SYNC_PENDING)],
                    [InlineKeyboardButton("« Back", callback_data=CallbackData.USER_SYNC_MENU)]
                ]),
                parse_mode="HTML"
            )
            return
        
        await query.edit_message_text(
            text=f"🗑️ <b>Deleting {len(pending)} users...</b>\n\n"
                 "<i>This may take a moment...</i>",
            parse_mode="HTML"
        )
        
        from utils.user_sync import force_delete_users
        
        deleted, errors = await force_delete_users(pending)
        
        # Clear the stored list
        context.user_data.pop("pending_deletions", None)
        
        error_text = ""
        if errors:
            error_text = "\n\n<b>Errors:</b>\n" + "\n".join(f"• {e}" for e in errors[:5])
            if len(errors) > 5:
                error_text += f"\n... and {len(errors) - 5} more errors"
        
        await query.edit_message_text(
            text=f"✅ <b>Force Delete Complete</b>\n\n"
                 f"Deleted: <code>{deleted}</code> users\n"
                 f"Failed: <code>{len(errors)}</code>"
                 f"{error_text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check Again", callback_data=CallbackData.USER_SYNC_PENDING)],
                [InlineKeyboardButton("« Back", callback_data=CallbackData.USER_SYNC_MENU)]
            ]),
            parse_mode="HTML"
        )
        
    except Exception as e:
        await query.edit_message_text(
            text=f"❌ Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=CallbackData.USER_SYNC_MENU)]
            ]),
            parse_mode="HTML"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SUBNET IP GROUPING (RELAXED MODE)
# ═══════════════════════════════════════════════════════════════════════════════


async def subnet_ip_grouping_toggle_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle subnet IP grouping toggle callback."""
    config_data = await read_config()
    current_status = config_data.get("subnet_ip_grouping", False)
    
    # Toggle the status
    new_status = not current_status
    await save_config_value("subnet_ip_grouping", str(new_status).lower())
    
    status_emoji = "✅" if new_status else "❌"
    status_text = "enabled" if new_status else "disabled"
    
    await query.answer(f"Subnet IP Grouping {status_text}")
    
    await query.edit_message_text(
        text=(
            f"🌐 <b>Subnet IP Grouping</b>\n\n"
            f"<b>Status:</b> {status_emoji} {status_text.title()}\n\n"
            "<b>What it does:</b>\n"
            "When enabled, IPs in the same <b>/24 subnet</b> that use the <b>same node</b> "
            "AND <b>same inbound protocol</b> are counted as <b>one device</b>.\n\n"
            "<b>Example:</b>\n"
            "If user connects with these IPs:\n"
            "• <code>192.168.1.5</code> → Node1 | VLESS\n"
            "• <code>192.168.1.15</code> → Node1 | VLESS\n"
            "• <code>192.168.1.100</code> → Node1 | VLESS\n\n"
            "With grouping <b>enabled</b>: counts as <b>1 device</b>\n"
            "With grouping <b>disabled</b>: counts as <b>3 devices</b>\n\n"
            "<i>💡 Use this for ISPs that frequently change user IPs within the same subnet.</i>"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"{'❌ Disable' if new_status else '✅ Enable'} Subnet Grouping",
                callback_data=CallbackData.SUBNET_IP_GROUPING_TOGGLE
            )],
            [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)]
        ]),
        parse_mode="HTML"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# HIGH TRUST IP GROUPING
# ═══════════════════════════════════════════════════════════════════════════════


async def high_trust_ip_grouping_toggle_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle high trust IP grouping toggle callback."""
    config_data = await read_config()
    current_status = config_data.get("high_trust_ip_grouping", False)
    threshold = config_data.get("high_trust_threshold", 20)
    
    # Toggle the status
    new_status = not current_status
    await save_config_value("high_trust_ip_grouping", str(new_status).lower())
    
    status_emoji = "✅" if new_status else "❌"
    status_text = "enabled" if new_status else "disabled"
    
    await query.answer(f"High Trust IP Grouping {status_text}")
    
    await query.edit_message_text(
        text=(
            f"⭐ <b>High Trust IP Grouping</b>\n\n"
            f"<b>Status:</b> {status_emoji} {status_text.title()}\n"
            f"<b>Trust Threshold:</b> ≥{threshold}\n\n"
            "<b>What it does:</b>\n"
            "For users with <b>high trust score</b>, if multiple IPs use <b>exactly</b> "
            "the <b>same node</b> AND <b>same inbound protocol</b>, they are counted as "
            "<b>one device</b>.\n\n"
            "<b>Use case:</b>\n"
            "When a user switches between WiFi and Mobile data on the <b>same phone</b>, "
            "they get different IPs but connect through the same node and inbound. "
            "This mode detects such patterns for trusted users and doesn't penalize them.\n\n"
            "<b>Example:</b>\n"
            "• <code>192.168.1.5</code> → Node1 | VLESS (WiFi)\n"
            "• <code>85.12.45.120</code> → Node1 | VLESS (Mobile)\n\n"
            f"With this mode <b>enabled</b> + trust ≥{threshold}: <b>1 device</b>\n"
            "With this mode <b>disabled</b>: <b>2 devices</b>\n\n"
            "<i>💡 This only applies to users who have built up trust through consistent behavior.</i>"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"{'❌ Disable' if new_status else '✅ Enable'} High Trust Mode",
                callback_data=CallbackData.HIGH_TRUST_IP_GROUPING_TOGGLE
            )],
            [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)]
        ]),
        parse_mode="HTML"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TRUST DATA RESET
# ═══════════════════════════════════════════════════════════════════════════════


async def trust_reset_menu_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle trust reset menu callback."""
    from utils.warning_system import warning_system
    
    warnings_count = len(warning_system.warnings)
    history_count = len(warning_system.warning_history)
    
    await query.edit_message_text(
        text=(
            "🗑️ <b>Reset Trust Data</b>\n\n"
            f"<b>Active Warnings:</b> {warnings_count} users\n"
            f"<b>Warning History:</b> {history_count} users\n\n"
            "<b>What this does:</b>\n"
            "• Clears all active monitoring warnings\n"
            "• Clears trust score history (12h/24h counters)\n"
            "• Users will start fresh with default trust score\n\n"
            "⚠️ <b>Warning:</b> This will reset ALL trust data for ALL users. "
            "Users who were flagged as suspicious will get a clean slate."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Reset ALL Trust Data", callback_data=CallbackData.TRUST_RESET_ALL)],
            [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)]
        ]),
        parse_mode="HTML"
    )


async def trust_reset_all_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle reset all trust data callback."""
    from utils.warning_system import warning_system
    
    try:
        warnings_cleared, history_cleared = await warning_system.clear_all_trust_data()
        
        await query.answer("✅ All trust data cleared")
        
        await query.edit_message_text(
            text=(
                "✅ <b>Trust Data Cleared</b>\n\n"
                f"<b>Warnings cleared:</b> {warnings_cleared}\n"
                f"<b>History entries cleared:</b> {history_cleared}\n\n"
                "All users now start with a fresh trust score."
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)]
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        await query.answer("❌ Error clearing trust data")
        await query.edit_message_text(
            text=f"❌ Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=CallbackData.TRUST_RESET_MENU)]
            ]),
            parse_mode="HTML"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CDN MODE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════


def create_cdn_mode_keyboard(use_xff: bool = True, provider: str = "cloudflare"):
    """Create CDN mode settings keyboard."""
    xff_status = "✅" if use_xff else "❌"
    keyboard = [
        [InlineKeyboardButton("➕ Add Inbound", callback_data=CallbackData.CDN_MODE_ADD)],
        [InlineKeyboardButton("➖ Remove Inbound", callback_data=CallbackData.CDN_MODE_REMOVE)],
        [InlineKeyboardButton(f"{xff_status} Use X-Forwarded-For", callback_data=CallbackData.CDN_USE_XFF_TOGGLE)],
        [InlineKeyboardButton(f"📡 Provider: {provider.title()}", callback_data=CallbackData.CDN_PROVIDER_MENU)],
        [InlineKeyboardButton("🗑️ Clear All", callback_data=CallbackData.CDN_MODE_CLEAR)],
        [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


async def cdn_mode_menu_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle CDN mode menu callback."""
    config_data = await read_config()
    cdn_inbounds = config_data.get("cdn_inbounds", [])
    use_xff = config_data.get("cdn_use_xff", True)
    provider = config_data.get("cdn_provider", "cloudflare")
    
    if cdn_inbounds:
        inbounds_list = "\n".join(f"  • <code>{inbound}</code>" for inbound in cdn_inbounds)
        status_text = f"<b>CDN Inbounds ({len(cdn_inbounds)}):</b>\n{inbounds_list}"
    else:
        status_text = "<i>No inbounds in CDN mode</i>"
    
    xff_status = "✅ Enabled" if use_xff else "❌ Disabled"
    
    await query.edit_message_text(
        text=(
            "☁️ <b>CDN Mode Settings</b>\n\n"
            f"{status_text}\n\n"
            f"<b>Provider:</b> {provider.title()}\n"
            f"<b>X-Forwarded-For:</b> {xff_status}\n\n"
            "<b>How it works:</b>\n"
            "When an inbound is in CDN mode and X-Forwarded-For is enabled, "
            "the system will extract the <b>real user IP</b> from the "
            "X-Forwarded-For header instead of using the CDN edge IP.\n\n"
            "This allows accurate IP counting for users behind CDN."
        ),
        reply_markup=create_cdn_mode_keyboard(use_xff, provider),
        parse_mode="HTML"
    )


async def cdn_mode_add_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle adding an inbound to CDN mode."""
    from telegram_bot.constants import SET_CDN_INBOUND
    
    await query.edit_message_text(
        text=(
            "➕ <b>Add Inbound to CDN Mode</b>\n\n"
            "Send the <b>exact</b> inbound protocol name to add.\n\n"
            "Examples:\n"
            "• <code>VLESS XHTTP TLS</code>\n"
            "• <code>Vmess CDN</code>\n"
            "• <code>Trojan WS TLS</code>\n\n"
            "💡 <i>You can find inbound names in the connection report or user logs.</i>\n\n"
            "Send /cancel to cancel."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Cancel", callback_data=CallbackData.CDN_MODE_MENU)]
        ]),
        parse_mode="HTML"
    )
    
    context.user_data["cdn_mode_action"] = "add"
    return SET_CDN_INBOUND


async def cdn_mode_remove_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle removing an inbound from CDN mode."""
    config_data = await read_config()
    cdn_inbounds = config_data.get("cdn_inbounds", [])
    use_xff = config_data.get("cdn_use_xff", True)
    provider = config_data.get("cdn_provider", "cloudflare")
    
    if not cdn_inbounds:
        await query.edit_message_text(
            text="❌ No inbounds are currently in CDN mode.",
            reply_markup=create_cdn_mode_keyboard(use_xff, provider),
            parse_mode="HTML"
        )
        return
    
    # Create buttons for each inbound
    keyboard = []
    for inbound in cdn_inbounds:
        callback_data = f"cdn_remove_{inbound[:50]}"  # Limit length
        keyboard.append([InlineKeyboardButton(f"❌ {inbound}", callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("« Back", callback_data=CallbackData.CDN_MODE_MENU)])
    
    await query.edit_message_text(
        text="➖ <b>Remove Inbound from CDN Mode</b>\n\nSelect an inbound to remove:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def cdn_mode_remove_inbound_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle removing a specific inbound from CDN mode."""
    callback_data = query.data
    inbound_name = callback_data.replace("cdn_remove_", "")
    
    config_data = await read_config()
    cdn_inbounds = config_data.get("cdn_inbounds", [])
    
    # Find and remove the inbound (handle truncated names)
    removed = None
    for inbound in cdn_inbounds:
        if inbound.startswith(inbound_name) or inbound == inbound_name:
            removed = inbound
            cdn_inbounds.remove(inbound)
            break
    
    if removed:
        # Save updated list
        await save_config_value("cdn_inbounds", ",".join(cdn_inbounds))
        
        await query.answer(f"✅ Removed: {removed}")
    else:
        await query.answer("❌ Inbound not found", show_alert=True)
    
    # Return to CDN mode menu
    await cdn_mode_menu_callback(query, context)


async def cdn_mode_clear_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle clearing all CDN inbounds."""
    await save_config_value("cdn_inbounds", "")
    await query.answer("✅ All CDN inbounds cleared")
    await cdn_mode_menu_callback(query, context)


async def cdn_use_xff_toggle_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle toggling X-Forwarded-For extraction."""
    config_data = await read_config()
    current_xff = config_data.get("cdn_use_xff", True)
    
    # Toggle the value
    new_xff = not current_xff
    await save_config_value("cdn_use_xff", "true" if new_xff else "false")
    
    status = "enabled" if new_xff else "disabled"
    await query.answer(f"✅ X-Forwarded-For extraction {status}")
    await cdn_mode_menu_callback(query, context)


async def cdn_provider_menu_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle CDN provider selection menu."""
    config_data = await read_config()
    current_provider = config_data.get("cdn_provider", "cloudflare")
    
    # Currently only Cloudflare is supported
    cf_prefix = "✅" if current_provider == "cloudflare" else "⬜"
    
    keyboard = [
        [InlineKeyboardButton(f"{cf_prefix} Cloudflare", callback_data=CallbackData.CDN_PROVIDER_CLOUDFLARE)],
        [InlineKeyboardButton("« Back", callback_data=CallbackData.CDN_MODE_MENU)],
    ]
    
    await query.edit_message_text(
        text=(
            "📡 <b>CDN Provider</b>\n\n"
            "Select the CDN provider for your inbounds:\n\n"
            f"Current: <b>{current_provider.title()}</b>\n\n"
            "<i>Currently only Cloudflare is supported.\n"
            "More providers may be added in the future.</i>"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def cdn_provider_cloudflare_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle setting CDN provider to Cloudflare."""
    await save_config_value("cdn_provider", "cloudflare")
    await query.answer("✅ CDN provider set to Cloudflare")
    await cdn_mode_menu_callback(query, context)


async def cdn_mode_add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for adding CDN inbound."""
    from telegram.ext import ConversationHandler
    from telegram_bot.constants import SET_CDN_INBOUND
    
    text = update.message.text.strip()
    
    # Load current CDN inbounds for keyboard
    config_data = await read_config()
    use_xff = config_data.get("cdn_use_xff", True)
    provider = config_data.get("cdn_provider", "cloudflare")
    cdn_inbounds = config_data.get("cdn_inbounds", [])
    
    if text.lower() == "/cancel":
        await update.message.reply_html(
            "❌ Cancelled.",
            reply_markup=create_cdn_mode_keyboard(use_xff, provider)
        )
        return ConversationHandler.END
    
    if not text:
        await update.message.reply_html(
            "❌ Please send a valid inbound name.\n\nSend /cancel to cancel."
        )
        return SET_CDN_INBOUND
    
    # Check if already exists
    if text in cdn_inbounds:
        await update.message.reply_html(
            f"⚠️ <code>{text}</code> is already in CDN mode.",
            reply_markup=create_cdn_mode_keyboard(use_xff, provider)
        )
        return ConversationHandler.END
    
    # Add new inbound
    cdn_inbounds.append(text)
    await save_config_value("cdn_inbounds", ",".join(cdn_inbounds))
    
    await update.message.reply_html(
        f"✅ Added <code>{text}</code> to CDN mode.\n\n"
        "Real user IPs will be extracted from X-Forwarded-For header.",
        reply_markup=create_cdn_mode_keyboard(use_xff, provider)
    )
    
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
# NODE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════


def create_node_settings_keyboard():
    """Create node settings menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("☁️ CDN Nodes", callback_data=CallbackData.NODE_CDN_MENU)],
        [InlineKeyboardButton("🚫 Disabled Nodes", callback_data=CallbackData.NODE_DISABLED_MENU)],
        [InlineKeyboardButton("🔄 Refresh Nodes", callback_data=CallbackData.NODE_SETTINGS_REFRESH)],
        [InlineKeyboardButton("« Back to Settings", callback_data=CallbackData.SETTINGS_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


async def _get_nodes_list():
    """Helper to get nodes list from panel."""
    config_data = await read_config()
    panel_config = config_data.get("panel", {})
    
    if not panel_config.get("domain") or not panel_config.get("password"):
        return None, "Panel not configured"
    
    from utils.types import PanelType
    from utils.panel_api.nodes import get_nodes
    
    panel_data = PanelType(
        panel_config.get("username", "admin"),
        panel_config.get("password", ""),
        panel_config.get("domain", "")
    )
    
    try:
        nodes = await get_nodes(panel_data, enabled_only=False)
        if isinstance(nodes, ValueError):
            return None, str(nodes)
        return nodes, None
    except Exception as e:
        return None, str(e)


async def node_settings_menu_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle node settings menu callback."""
    config_data = await read_config()
    cdn_nodes = config_data.get("cdn_nodes", [])
    disabled_nodes = config_data.get("disabled_nodes", [])
    
    status_text = (
        f"<b>CDN Nodes:</b> {len(cdn_nodes)} configured\n"
        f"<b>Disabled Nodes:</b> {len(disabled_nodes)} configured"
    )
    
    await query.edit_message_text(
        text=(
            "🖥️ <b>Node Settings</b>\n\n"
            f"{status_text}\n\n"
            "<b>CDN Nodes:</b>\n"
            "All IPs from CDN nodes count as <b>1 device</b>.\n"
            "Use for nodes behind CDN (Cloudflare, etc.)\n\n"
            "<b>Disabled Nodes:</b>\n"
            "Connections from disabled nodes are <b>ignored</b>.\n"
            "Use for nodes you don't want to monitor."
        ),
        reply_markup=create_node_settings_keyboard(),
        parse_mode="HTML"
    )


async def node_settings_refresh_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Refresh nodes list from panel."""
    from utils.panel_api.nodes import invalidate_nodes_cache
    
    await invalidate_nodes_cache()
    await query.answer("✅ Nodes cache refreshed")
    await node_settings_menu_callback(query, context)


async def node_cdn_menu_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Show CDN nodes menu with toggle buttons."""
    config_data = await read_config()
    cdn_nodes = config_data.get("cdn_nodes", [])
    
    nodes, error = await _get_nodes_list()
    
    if error:
        await query.edit_message_text(
            text=f"❌ Failed to get nodes: {error}",
            reply_markup=create_node_settings_keyboard(),
            parse_mode="HTML"
        )
        return
    
    if not nodes:
        await query.edit_message_text(
            text="❌ No nodes found in panel.",
            reply_markup=create_node_settings_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Build node buttons
    keyboard = []
    for node in nodes:
        is_cdn = node.node_id in cdn_nodes
        status = "☁️" if is_cdn else "⬜"
        btn_text = f"{status} {node.node_name} (#{node.node_id})"
        callback_data = f"node_cdn_toggle:{node.node_id}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
    
    # Add clear all and back buttons
    if cdn_nodes:
        keyboard.append([InlineKeyboardButton("🗑️ Clear All CDN", callback_data=CallbackData.NODE_CDN_CLEAR)])
    keyboard.append([InlineKeyboardButton("« Back", callback_data=CallbackData.NODE_SETTINGS_MENU)])
    
    await query.edit_message_text(
        text=(
            "☁️ <b>CDN Nodes</b>\n\n"
            "Select nodes that are behind CDN.\n"
            "All IPs from these nodes will count as <b>1 device</b>.\n\n"
            f"<b>Currently enabled:</b> {len(cdn_nodes)} nodes\n\n"
            "<i>Click a node to toggle CDN mode:</i>"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def node_cdn_toggle_callback(query, context: ContextTypes.DEFAULT_TYPE, node_id: int):
    """Toggle CDN mode for a node."""
    config_data = await read_config()
    cdn_nodes = config_data.get("cdn_nodes", [])
    
    if node_id in cdn_nodes:
        cdn_nodes.remove(node_id)
        await query.answer(f"❌ Node #{node_id} removed from CDN mode")
    else:
        cdn_nodes.append(node_id)
        await query.answer(f"✅ Node #{node_id} added to CDN mode")
    
    # Save updated list
    await save_config_value("cdn_nodes", ",".join(str(n) for n in cdn_nodes))
    
    # Refresh menu
    await node_cdn_menu_callback(query, context)


async def node_cdn_clear_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Clear all CDN nodes."""
    await save_config_value("cdn_nodes", "")
    await query.answer("✅ All CDN nodes cleared")
    await node_cdn_menu_callback(query, context)


async def node_disabled_menu_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Show disabled nodes menu with toggle buttons."""
    config_data = await read_config()
    disabled_nodes = config_data.get("disabled_nodes", [])
    
    nodes, error = await _get_nodes_list()
    
    if error:
        await query.edit_message_text(
            text=f"❌ Failed to get nodes: {error}",
            reply_markup=create_node_settings_keyboard(),
            parse_mode="HTML"
        )
        return
    
    if not nodes:
        await query.edit_message_text(
            text="❌ No nodes found in panel.",
            reply_markup=create_node_settings_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Build node buttons
    keyboard = []
    for node in nodes:
        is_disabled = node.node_id in disabled_nodes
        status = "🚫" if is_disabled else "✅"
        btn_text = f"{status} {node.node_name} (#{node.node_id})"
        callback_data = f"node_disabled_toggle:{node.node_id}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
    
    # Add clear all and back buttons
    if disabled_nodes:
        keyboard.append([InlineKeyboardButton("🗑️ Clear All Disabled", callback_data=CallbackData.NODE_DISABLED_CLEAR)])
    keyboard.append([InlineKeyboardButton("« Back", callback_data=CallbackData.NODE_SETTINGS_MENU)])
    
    await query.edit_message_text(
        text=(
            "🚫 <b>Disabled Nodes</b>\n\n"
            "Select nodes to exclude from monitoring.\n"
            "Connections from these nodes will be <b>ignored</b>.\n\n"
            f"<b>Currently disabled:</b> {len(disabled_nodes)} nodes\n\n"
            "<i>Click a node to toggle:</i>\n"
            "✅ = Monitored | 🚫 = Disabled"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def node_disabled_toggle_callback(query, context: ContextTypes.DEFAULT_TYPE, node_id: int):
    """Toggle disabled state for a node."""
    config_data = await read_config()
    disabled_nodes = config_data.get("disabled_nodes", [])
    
    if node_id in disabled_nodes:
        disabled_nodes.remove(node_id)
        await query.answer(f"✅ Node #{node_id} is now monitored")
    else:
        disabled_nodes.append(node_id)
        await query.answer(f"🚫 Node #{node_id} is now disabled")
    
    # Save updated list
    await save_config_value("disabled_nodes", ",".join(str(n) for n in disabled_nodes))
    
    # Refresh menu
    await node_disabled_menu_callback(query, context)


async def node_disabled_clear_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Clear all disabled nodes."""
    await save_config_value("disabled_nodes", "")
    await query.answer("✅ All nodes are now monitored")
    await node_disabled_menu_callback(query, context)
