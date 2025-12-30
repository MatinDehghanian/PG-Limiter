"""
Telegram bot handlers module.
Contains all command and callback handlers organized by functionality.
"""

from telegram_bot.handlers.admin import (
    add_admin,
    admins_list,
    check_admin_privilege,
    get_chat_id,
    get_chat_id_to_remove,
    remove_admin,
)

from telegram_bot.handlers.limits import (
    set_special_limit,
    get_special_limit,
    get_limit_number,
    show_special_limit_function,
    get_general_limit_number,
    get_general_limit_number_handler,
    handle_show_special_limit_callback,
    handle_special_limits_page_callback,
    handle_edit_special_limit_callback,
    handle_special_limit_info_callback,
    handle_remove_special_limit_callback,
)

from telegram_bot.handlers.users import (
    set_except_users,
    set_except_users_handler,
    remove_except_user,
    remove_except_user_handler,
    show_except_users,
    show_disabled_users_menu,
    enable_single_user,
    enable_all_disabled_users,
    show_user_info,
    cleanup_deleted_users_handler,
)

from telegram_bot.handlers.settings import (
    set_panel_domain,
    get_domain,
    get_username,
    get_password,
    set_check_interval,
    check_interval_handler,
    set_time_to_active,
    time_to_active_handler,
    set_country_code,
    country_code_handler,
    set_ipinfo_token,
    ipinfo_token_handler,
)

from telegram_bot.handlers.monitoring import (
    monitoring_status,
    monitoring_details,
    clear_monitoring,
)

from telegram_bot.handlers.reports import (
    connection_report_command,
    node_usage_report_command,
    multi_device_users_command,
    users_by_node_command,
    users_by_protocol_command,
    ip_history_12h_command,
    ip_history_48h_command,
)

from telegram_bot.handlers.backup import (
    send_backup,
    restore_config,
    restore_config_handler,
)

from telegram_bot.handlers.punishment import (
    punishment_status,
    punishment_toggle,
    punishment_set_window,
    punishment_set_steps,
    user_violations,
    clear_user_violations,
)

from telegram_bot.handlers.group_filter import (
    group_filter_status,
    group_filter_toggle,
    group_filter_mode,
    group_filter_set,
    group_filter_add,
    group_filter_remove,
)

from telegram_bot.handlers.admin_filter import (
    admin_filter_status,
    admin_filter_toggle,
    admin_filter_mode,
    admin_filter_set,
    admin_filter_add,
    admin_filter_remove,
)

__all__ = [
    # Admin handlers
    "add_admin",
    "admins_list",
    "check_admin_privilege",
    "get_chat_id",
    "get_chat_id_to_remove",
    "remove_admin",
    # Limits handlers
    "set_special_limit",
    "get_special_limit",
    "get_limit_number",
    "show_special_limit_function",
    "get_general_limit_number",
    "get_general_limit_number_handler",
    "handle_show_special_limit_callback",
    "handle_special_limits_page_callback",
    "handle_edit_special_limit_callback",
    "handle_special_limit_info_callback",
    "handle_remove_special_limit_callback",
    # Users handlers
    "set_except_users",
    "set_except_users_handler",
    "remove_except_user",
    "remove_except_user_handler",
    "show_except_users",
    "show_disabled_users_menu",
    "enable_single_user",
    "enable_all_disabled_users",
    "show_user_info",
    "cleanup_deleted_users_handler",
    # Settings handlers
    "set_panel_domain",
    "get_domain",
    "get_username",
    "get_password",
    "set_check_interval",
    "check_interval_handler",
    "set_time_to_active",
    "time_to_active_handler",
    "set_country_code",
    "country_code_handler",
    "set_ipinfo_token",
    "ipinfo_token_handler",
    # Monitoring handlers
    "monitoring_status",
    "monitoring_details",
    "clear_monitoring",
    # Reports handlers
    "connection_report_command",
    "node_usage_report_command",
    "multi_device_users_command",
    "users_by_node_command",
    "users_by_protocol_command",
    "ip_history_12h_command",
    "ip_history_48h_command",
    # Backup handlers
    "send_backup",
    "restore_config",
    "restore_config_handler",
    # Punishment handlers
    "punishment_status",
    "punishment_toggle",
    "punishment_set_window",
    "punishment_set_steps",
    "user_violations",
    "clear_user_violations",
    # Group filter handlers
    "group_filter_status",
    "group_filter_toggle",
    "group_filter_mode",
    "group_filter_set",
    "group_filter_add",
    "group_filter_remove",
    # Admin filter handlers
    "admin_filter_status",
    "admin_filter_toggle",
    "admin_filter_mode",
    "admin_filter_set",
    "admin_filter_add",
    "admin_filter_remove",
]
