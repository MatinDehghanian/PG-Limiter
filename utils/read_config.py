"""
Read config file and return data.
Auto-converts old flat format to new structured format.
"""
# pylint: disable=global-statement

import json
import os
import sys
import time

CONFIG_DATA = None
LAST_READ_TIME = 0

# Mapping from old flat keys to new nested paths
OLD_TO_NEW_MAP = {
    # Panel settings
    "PANEL_DOMAIN": ("panel", "domain"),
    "PANEL_USERNAME": ("panel", "username"),
    "PANEL_PASSWORD": ("panel", "password"),
    # Telegram settings
    "BOT_TOKEN": ("telegram", "bot_token"),
    "ADMINS": ("telegram", "admins"),
    # Limits settings
    "GENERAL_LIMIT": ("limits", "general"),
    "SPECIAL_LIMIT": ("limits", "special"),
    "SPECIAL_LIMITS": ("limits", "special"),  # Alternative spelling
    "EXCEPT_USERS": ("limits", "except_users"),
    # Monitoring settings
    "CHECK_INTERVAL": ("monitoring", "check_interval"),
    "TIME_TO_ACTIVE_USERS": ("monitoring", "time_to_active_users"),
    "IP_LOCATION": ("monitoring", "ip_location"),
    # Display settings (SHOW_SINGLE_DEVICE_USERS removed)
    "SHOW_ENHANCED_DETAILS": ("display", "show_enhanced_details"),
    # API settings
    "IPINFO_TOKEN": ("api", "ipinfo_token"),
    "USE_FALLBACK_ISP_API": ("api", "use_fallback_isp_api"),
}


def is_old_format(data: dict) -> bool:
    """Check if config uses old flat format."""
    # Old format has flat keys like PANEL_DOMAIN at root level
    return "PANEL_DOMAIN" in data or "BOT_TOKEN" in data or "GENERAL_LIMIT" in data


def convert_old_to_new(old_data: dict) -> dict:
    """Convert old flat config format to new nested format."""
    new_data = {
        "panel": {},
        "telegram": {},
        "limits": {},
        "monitoring": {},
        "display": {},
        "api": {}
    }
    
    for old_key, path in OLD_TO_NEW_MAP.items():
        if old_key in old_data:
            section, key = path
            new_data[section][key] = old_data[old_key]
    
    # Set defaults for missing values
    if "general" not in new_data["limits"]:
        new_data["limits"]["general"] = 2
    if "special" not in new_data["limits"]:
        new_data["limits"]["special"] = {}
    if "except_users" not in new_data["limits"]:
        new_data["limits"]["except_users"] = []
    if "check_interval" not in new_data["monitoring"]:
        new_data["monitoring"]["check_interval"] = 60
    if "time_to_active_users" not in new_data["monitoring"]:
        new_data["monitoring"]["time_to_active_users"] = 1800
    if "ip_location" not in new_data["monitoring"]:
        new_data["monitoring"]["ip_location"] = "IR"
    if "show_enhanced_details" not in new_data["display"]:
        new_data["display"]["show_enhanced_details"] = True
    if "ipinfo_token" not in new_data["api"]:
        new_data["api"]["ipinfo_token"] = ""
    if "use_fallback_isp_api" not in new_data["api"]:
        new_data["api"]["use_fallback_isp_api"] = False
    
    return new_data


def save_config(data: dict, config_file: str = "config.json"):
    """Save config to file."""
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


async def read_config(check_required_elements=None) -> dict:
    """
    Read and return data from config.json file.
    Auto-converts old format to new format if detected.
    """
    global CONFIG_DATA
    global LAST_READ_TIME
    config_file = "config.json"

    if not os.path.exists(config_file):
        print("Config file not found.")
        sys.exit()
    
    file_mod_time = os.path.getmtime(config_file)
    
    if CONFIG_DATA is None or file_mod_time > LAST_READ_TIME:
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except json.JSONDecodeError as error:
            print(
                "Error decoding the config.json file. Please check its syntax.", error
            )
            sys.exit()
        
        # Auto-convert old format to new format
        if is_old_format(raw_data):
            print("🔄 Converting old config format to new format...")
            raw_data = convert_old_to_new(raw_data)
            save_config(raw_data, config_file)
            print("✓ Config converted and saved!")
        
        CONFIG_DATA = raw_data
        
        # Validate required keys
        if not CONFIG_DATA.get("telegram", {}).get("bot_token"):
            print("BOT_TOKEN is not set in the config.json file.")
            sys.exit()
        if not CONFIG_DATA.get("telegram", {}).get("admins"):
            print("ADMINS is not set in the config.json file.")
            sys.exit()
        
        LAST_READ_TIME = time.time()
    
    if check_required_elements:
        required_checks = [
            ("panel", "domain", "PANEL_DOMAIN"),
            ("panel", "username", "PANEL_USERNAME"),
            ("panel", "password", "PANEL_PASSWORD"),
            ("monitoring", "check_interval", "CHECK_INTERVAL"),
            ("monitoring", "time_to_active_users", "TIME_TO_ACTIVE_USERS"),
            ("monitoring", "ip_location", "IP_LOCATION"),
            ("limits", "general", "GENERAL_LIMIT"),
        ]
        for section, key, old_name in required_checks:
            if not CONFIG_DATA.get(section, {}).get(key):
                raise ValueError(
                    f"Missing required element '{old_name}' in the config file."
                )
    
    return CONFIG_DATA


def get_config_value(config: dict, key: str, default=None):
    """
    Get config value using new nested format.
    Helper function for easy access.
    """
    key_map = {
        "PANEL_DOMAIN": ("panel", "domain"),
        "PANEL_USERNAME": ("panel", "username"),
        "PANEL_PASSWORD": ("panel", "password"),
        "BOT_TOKEN": ("telegram", "bot_token"),
        "ADMINS": ("telegram", "admins"),
        "GENERAL_LIMIT": ("limits", "general"),
        "SPECIAL_LIMIT": ("limits", "special"),
        "EXCEPT_USERS": ("limits", "except_users"),
        "CHECK_INTERVAL": ("monitoring", "check_interval"),
        "TIME_TO_ACTIVE_USERS": ("monitoring", "time_to_active_users"),
        "IP_LOCATION": ("monitoring", "ip_location"),
        "SHOW_ENHANCED_DETAILS": ("display", "show_enhanced_details"),
        "IPINFO_TOKEN": ("api", "ipinfo_token"),
        "USE_FALLBACK_ISP_API": ("api", "use_fallback_isp_api"),
    }
    
    if key in key_map:
        section, nested_key = key_map[key]
        return config.get(section, {}).get(nested_key, default)
    return config.get(key, default)
