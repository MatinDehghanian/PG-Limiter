"""
Panel API module for interacting with the Marzban panel.

This module provides functions to interact with the panel API including:
- Authentication and token management
- User operations (list, enable, disable, etc.)
- Node operations
- Group operations
- Admin operations
"""

# Auth functions
from utils.panel_api.auth import (
    get_token,
    invalidate_token_cache,
    safe_send_logs_panel,
)

# User operations
from utils.panel_api.users import (
    all_user,
    get_all_panel_users,
    check_user_exists,
    get_user_details,
    get_user_admin,
    update_user_groups,
    enable_all_user,
    enable_user_by_status,
    enable_user_by_group,
    enable_selected_users,
    disable_user_by_status,
    disable_user_by_group,
    disable_user,
    disable_user_with_punishment,
    enable_dis_user,
    cleanup_deleted_users,
)

# Node operations
from utils.panel_api.nodes import (
    get_nodes,
    invalidate_nodes_cache,
)

# Group operations
from utils.panel_api.groups import (
    get_groups,
)

# Admin operations
from utils.panel_api.admins import (
    get_admins,
)

__all__ = [
    # Auth
    "get_token",
    "invalidate_token_cache",
    "safe_send_logs_panel",
    # Users
    "all_user",
    "get_all_panel_users",
    "check_user_exists",
    "get_user_details",
    "get_user_admin",
    "update_user_groups",
    "enable_all_user",
    "enable_user_by_status",
    "enable_user_by_group",
    "enable_selected_users",
    "disable_user_by_status",
    "disable_user_by_group",
    "disable_user",
    "disable_user_with_punishment",
    "enable_dis_user",
    "cleanup_deleted_users",
    # Nodes
    "get_nodes",
    "invalidate_nodes_cache",
    # Groups
    "get_groups",
    # Admins
    "get_admins",
]
