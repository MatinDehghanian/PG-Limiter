"""
Telegram Bot Keyboards
Contains all inline keyboard builders.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram_bot.constants import CallbackData


def create_main_menu_keyboard():
    """Create the main menu inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("⚙️ Settings", callback_data=CallbackData.SETTINGS_MENU),
            InlineKeyboardButton("📊 Reports", callback_data=CallbackData.REPORTS_MENU),
        ],
        [
            InlineKeyboardButton("🎯 Limits", callback_data=CallbackData.LIMITS_MENU),
            InlineKeyboardButton("👥 Users", callback_data=CallbackData.USERS_MENU),
        ],
        [
            InlineKeyboardButton("📡 Monitoring", callback_data=CallbackData.MONITORING_MENU),
            InlineKeyboardButton("👑 Admins", callback_data=CallbackData.ADMIN_MENU),
        ],
        [
            InlineKeyboardButton("💾 Backup", callback_data=CallbackData.BACKUP),
            InlineKeyboardButton("📥 Restore", callback_data=CallbackData.RESTORE),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_settings_menu_keyboard():
    """Create the settings menu inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🔑 IPInfo Token", callback_data=CallbackData.SET_IPINFO),
            InlineKeyboardButton("🚫 Disable Method", callback_data=CallbackData.DISABLE_METHOD_MENU),
        ],
        [
            InlineKeyboardButton("🌍 Country Code", callback_data=CallbackData.COUNTRY_NONE),
            InlineKeyboardButton("⏱️ Check Interval", callback_data=CallbackData.INTERVAL_CUSTOM),
        ],
        [
            InlineKeyboardButton("⏰ Active Time", callback_data=CallbackData.TIME_CUSTOM),
            InlineKeyboardButton("📋 Enhanced Details", callback_data=CallbackData.ENHANCED_ON),
        ],
        [
            InlineKeyboardButton("⚖️ Punishment", callback_data=CallbackData.PUNISHMENT_MENU),
        ],
        [
            InlineKeyboardButton("🔍 Group Filter", callback_data=CallbackData.GROUP_FILTER_MENU),
            InlineKeyboardButton("👤 Admin Filter", callback_data=CallbackData.ADMIN_FILTER_MENU),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_MAIN),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_limits_menu_keyboard():
    """Create the limits menu inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🎯 Set Special Limit", callback_data=CallbackData.SET_SPECIAL_LIMIT),
        ],
        [
            InlineKeyboardButton("📋 Show Special Limits", callback_data=CallbackData.SHOW_SPECIAL_LIMIT),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_MAIN),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_users_menu_keyboard():
    """Create the users menu inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Whitelist (Except Users)", callback_data=CallbackData.WHITELIST_MENU),
        ],
        [
            InlineKeyboardButton("🚫 Disabled Users", callback_data=CallbackData.SHOW_DISABLED_USERS),
        ],
        [
            InlineKeyboardButton("🧹 Cleanup Deleted Users", callback_data=CallbackData.CLEANUP_DELETED_USERS),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_MAIN),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_whitelist_menu_keyboard():
    """Create the whitelist (except users) submenu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📋 Show Whitelist", callback_data=CallbackData.SHOW_EXCEPT_USERS),
        ],
        [
            InlineKeyboardButton("➕ Add User", callback_data=CallbackData.SET_EXCEPT_USER),
            InlineKeyboardButton("➖ Remove User", callback_data=CallbackData.REMOVE_EXCEPT_USER),
        ],
        [
            InlineKeyboardButton("🔙 Back to Users", callback_data=CallbackData.BACK_USERS),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_monitoring_menu_keyboard():
    """Create the monitoring menu inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Status", callback_data=CallbackData.MONITORING_STATUS),
            InlineKeyboardButton("📈 Details", callback_data=CallbackData.MONITORING_DETAILS),
        ],
        [
            InlineKeyboardButton("🗑️ Clear All", callback_data=CallbackData.MONITORING_CLEAR),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_MAIN),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_reports_menu_keyboard():
    """Create the reports menu inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Connection Report", callback_data=CallbackData.REPORT_CONNECTION),
            InlineKeyboardButton("🖥️ Node Usage", callback_data=CallbackData.REPORT_NODE_USAGE),
        ],
        [
            InlineKeyboardButton("📱 Multi-Device", callback_data=CallbackData.REPORT_MULTI_DEVICE),
        ],
        [
            InlineKeyboardButton("🕐 IP History 12h", callback_data=CallbackData.REPORT_IP_12H),
            InlineKeyboardButton("🕐 IP History 48h", callback_data=CallbackData.REPORT_IP_48H),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_MAIN),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_admin_menu_keyboard():
    """Create the admin management menu inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("➕ Add Admin", callback_data=CallbackData.ADD_ADMIN),
            InlineKeyboardButton("📋 List Admins", callback_data=CallbackData.LIST_ADMINS),
        ],
        [
            InlineKeyboardButton("➖ Remove Admin", callback_data=CallbackData.REMOVE_ADMIN),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_MAIN),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_country_keyboard():
    """Create country code selection keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🇮🇷 Iran (IR)", callback_data=CallbackData.COUNTRY_IR),
            InlineKeyboardButton("🇷🇺 Russia (RU)", callback_data=CallbackData.COUNTRY_RU),
        ],
        [
            InlineKeyboardButton("🇨🇳 China (CN)", callback_data=CallbackData.COUNTRY_CN),
            InlineKeyboardButton("🌍 All Countries", callback_data=CallbackData.COUNTRY_NONE),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_SETTINGS),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_interval_keyboard():
    """Create check interval selection keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("2 min", callback_data=CallbackData.INTERVAL_120),
            InlineKeyboardButton("3 min", callback_data=CallbackData.INTERVAL_180),
        ],
        [
            InlineKeyboardButton("4 min", callback_data=CallbackData.INTERVAL_240),
            InlineKeyboardButton("✏️ Custom", callback_data=CallbackData.INTERVAL_CUSTOM),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_SETTINGS),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_time_to_active_keyboard():
    """Create time to active selection keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("5 min", callback_data=CallbackData.TIME_300),
            InlineKeyboardButton("10 min", callback_data=CallbackData.TIME_600),
        ],
        [
            InlineKeyboardButton("15 min", callback_data=CallbackData.TIME_900),
            InlineKeyboardButton("✏️ Custom", callback_data=CallbackData.TIME_CUSTOM),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_SETTINGS),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_enhanced_details_keyboard():
    """Create enhanced details toggle keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Enable", callback_data=CallbackData.ENHANCED_ON),
            InlineKeyboardButton("❌ Disable", callback_data=CallbackData.ENHANCED_OFF),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_SETTINGS),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_disable_method_keyboard():
    """Create disable method selection keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🚫 By Status (disabled)", callback_data=CallbackData.DISABLE_BY_STATUS),
        ],
        [
            InlineKeyboardButton("📁 By Group", callback_data=CallbackData.DISABLE_BY_GROUP),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_SETTINGS),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_punishment_menu_keyboard(enabled: bool = False):
    """Create punishment system menu keyboard."""
    toggle_text = "🔴 Disable" if enabled else "🟢 Enable"
    keyboard = [
        [
            InlineKeyboardButton(toggle_text, callback_data=CallbackData.PUNISHMENT_TOGGLE),
        ],
        [
            InlineKeyboardButton("24h Window", callback_data=CallbackData.PUNISHMENT_WINDOW_24),
            InlineKeyboardButton("48h Window", callback_data=CallbackData.PUNISHMENT_WINDOW_48),
        ],
        [
            InlineKeyboardButton("72h Window", callback_data=CallbackData.PUNISHMENT_WINDOW_72),
            InlineKeyboardButton("✏️ Custom", callback_data=CallbackData.PUNISHMENT_WINDOW_CUSTOM),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=CallbackData.BACK_SETTINGS),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_back_keyboard(callback_data: str = CallbackData.BACK_MAIN):
    """Create a simple back button keyboard."""
    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data=callback_data)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_confirmation_keyboard(confirm_data: str, cancel_data: str = CallbackData.BACK_MAIN):
    """Create a confirmation keyboard with Yes/No buttons."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes", callback_data=confirm_data),
            InlineKeyboardButton("❌ No", callback_data=cancel_data),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_back_to_main_keyboard():
    """Create a simple back to main menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("« Back to Main Menu", callback_data=CallbackData.MAIN_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_special_limit_options_keyboard():
    """Create special limit options keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("1️⃣ 1 Device", callback_data=CallbackData.SPECIAL_LIMIT_1),
            InlineKeyboardButton("2️⃣ 2 Devices", callback_data=CallbackData.SPECIAL_LIMIT_2),
        ],
        [InlineKeyboardButton("✏️ Custom", callback_data=CallbackData.SPECIAL_LIMIT_CUSTOM)],
        [InlineKeyboardButton("« Back to Limits", callback_data=CallbackData.LIMITS_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_general_limit_keyboard():
    """Create general limit options keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("2️⃣", callback_data=CallbackData.GENERAL_LIMIT_2),
            InlineKeyboardButton("3️⃣", callback_data=CallbackData.GENERAL_LIMIT_3),
            InlineKeyboardButton("4️⃣", callback_data=CallbackData.GENERAL_LIMIT_4),
        ],
        [InlineKeyboardButton("✏️ Custom", callback_data=CallbackData.GENERAL_LIMIT_CUSTOM)],
        [InlineKeyboardButton("« Back to Limits", callback_data=CallbackData.LIMITS_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)
