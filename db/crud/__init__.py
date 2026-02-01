"""
CRUD Operations for Database

Provides high-level async operations for all database models.
Each CRUD class is organized in its own module for better maintainability.
"""

# User operations
from db.crud.users import UserCRUD

# User limit operations
from db.crud.limits import UserLimitCRUD

# Except user operations (whitelist)
from db.crud.except_users import ExceptUserCRUD

# Disabled user operations
from db.crud.disabled_users import DisabledUserCRUD

# Subnet ISP cache operations
from db.crud.subnet_isp import SubnetISPCRUD

# Violation history operations
from db.crud.violations import ViolationHistoryCRUD

# Config operations
from db.crud.config import ConfigCRUD

# IP history operations
from db.crud.ip_history import IPHistoryCRUD

# Admin patterns (prefix/postfix) operations
from db.crud.admin_patterns import AdminPatternCRUD

# Limit patterns (prefix/postfix with IP limits) operations
from db.crud.limit_patterns import LimitPatternCRUD

__all__ = [
    "UserCRUD",
    "UserLimitCRUD",
    "ExceptUserCRUD",
    "DisabledUserCRUD",
    "SubnetISPCRUD",
    "ViolationHistoryCRUD",
    "ConfigCRUD",
    "IPHistoryCRUD",
    "AdminPatternCRUD",
    "LimitPatternCRUD",
]
