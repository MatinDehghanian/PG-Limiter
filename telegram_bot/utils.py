"""
This module contains utility functions for managing admin IDs,
handling special limits for users, and interacting with the database.
"""

import json
import os
import sys

from utils.types import PanelType
from utils.read_config import invalidate_config_cache

try:
    import httpx
except ImportError:
    print("Module 'httpx' is not installed use: 'pip install httpx' to install it")
    sys.exit()

# Import database utilities
try:
    from db import get_db, UserLimitCRUD, ExceptUserCRUD, ConfigCRUD
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


async def get_token(panel_data: PanelType) -> PanelType | ValueError:
    """
    Duplicate function to handel 'circular import' error
    """
    # pylint: disable=duplicate-code
    payload = {
        "username": f"{panel_data.panel_username}",
        "password": f"{panel_data.panel_password}",
    }
    for scheme in ["https", "http"]:
        url = f"{scheme}://{panel_data.panel_domain}/api/admin/token"
        try:
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.post(url, data=payload, timeout=5)
                response.raise_for_status()
            json_obj = response.json()
            panel_data.panel_token = json_obj["access_token"]
            return panel_data
        except Exception:  # pylint: disable=broad-except
            continue
    message = (
        "Failed to get token. make sure the panel is running "
        + "and the username and password are correct."
    )
    raise ValueError(message)


async def read_json_file() -> dict:
    """
    Reads and returns the content of the config.json file.

    Returns:
        The content of the config.json file.
    """
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


async def write_json_file(data: dict):
    """
    Writes the given data to the config.json file.

    Args:
        data: The data to write to the file.
    """
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


async def add_admin_to_config(new_admin_id: int) -> int | None:
    """
    Adds a new admin ID to the config.json file.
    Note: For Docker deployment, admins should be set via ADMIN_IDS env variable.

    Args:
        new_admin_id: The ID of the new admin.

    Returns:
        The ID of the new admin if it was added, None otherwise.
    """
    # First check if admins are configured via environment variable
    admin_ids_env = os.environ.get("ADMIN_IDS", "")
    if admin_ids_env:
        # Admin IDs are managed via environment variable
        # Can't dynamically add to env var, but check if already in list
        try:
            admins = [int(id.strip()) for id in admin_ids_env.split(",") if id.strip()]
            if int(new_admin_id) in admins:
                return new_admin_id
        except ValueError:
            pass
        # Return None since we can't add to env var dynamically
        # User needs to update ADMIN_IDS env var
        return None
    
    # Fall back to config.json for non-Docker deployments
    if os.path.exists("config.json"):
        data = await read_json_file()
        if "telegram" not in data:
            data["telegram"] = {}
        admins = data.get("telegram", {}).get("admins", [])
        if int(new_admin_id) not in admins:
            admins.append(int(new_admin_id))
            data["telegram"]["admins"] = admins
            await write_json_file(data)
            return new_admin_id
    else:
        data = {"telegram": {"admins": [new_admin_id]}}
        await write_json_file(data)
        return new_admin_id
    return None


async def check_admin() -> list[int] | None:
    """
    Checks and returns the list of admins.
    First checks ADMIN_IDS environment variable, then falls back to config.json.

    Returns:
        The list of admins.
    """
    # First check environment variable (Docker deployment)
    admin_ids_env = os.environ.get("ADMIN_IDS", "")
    if admin_ids_env:
        try:
            return [int(id.strip()) for id in admin_ids_env.split(",") if id.strip()]
        except ValueError:
            pass
    
    # Fall back to config.json for non-Docker deployments
    if os.path.exists("config.json"):
        data = await read_json_file()
        return data.get("telegram", {}).get("admins", [])
    
    return []


async def handel_special_limit(username: str, limit: int) -> list:
    """
    Handles the special limit for a given username using database.

    Args:
        username: The username to handle the special limit for.
        limit: The limit to set.

    Returns:
        A list where the first element is a flag indicating whether the limit was set before,
        and the second element is the new limit.
    """
    if DB_AVAILABLE:
        async with get_db() as db:
            # Check if limit was set before
            existing_limit = await UserLimitCRUD.get_limit(db, username)
            set_before = 1 if existing_limit is not None else 0
            
            # Set the new limit
            await UserLimitCRUD.set_limit(db, username, limit)
            await db.commit()
            return [set_before, limit]
    
    # Fallback to config.json
    set_before = 0
    if os.path.exists("config.json"):
        data = await read_json_file()
        if "limits" not in data:
            data["limits"] = {}
        special_limit = data.get("limits", {}).get("special", {})
        if special_limit.get(username):
            set_before = 1
        special_limit[username] = limit
        data["limits"]["special"] = special_limit
        await write_json_file(data)
        return [set_before, special_limit[username]]
    data = {"limits": {"special": {username: limit}}}
    await write_json_file(data)
    return [0, limit]


async def remove_admin_from_config(admin_id: int) -> bool:
    """
    Removes an admin from the configuration.
    Note: In Docker deployment, admins are managed via ADMIN_IDS env var.

    Args:
        admin_id (int): The ID of the admin to be removed.

    Returns:
        bool: True if the admin was successfully removed, False otherwise.
    """
    data = await read_json_file()
    admins = data.get("telegram", {}).get("admins", [])
    if admin_id in admins:
        admins.remove(admin_id)
        data["telegram"]["admins"] = admins
        await write_json_file(data)
        return True
    return False


async def add_base_information(domain: str, password: str, username: str):
    """
    Adds base information including domain, password, and username.

    Args:
        domain (str): The domain for the panel.
        password (str): The password for the panel.
        username (str): The username for the panel.

    Returns:
        None
    """
    await get_token(
        PanelType(panel_domain=domain, panel_password=password, panel_username=username)
    )
    if os.path.exists("config.json"):
        data = await read_json_file()
    else:
        data = {}
    if "panel" not in data:
        data["panel"] = {}
    data["panel"]["domain"] = domain
    data["panel"]["username"] = username
    data["panel"]["password"] = password
    await write_json_file(data)


async def get_special_limits_dict() -> dict:
    """
    This function retrieves the special limits from database as a dictionary.

    Returns:
        dict: Dictionary of username -> limit
    """
    if DB_AVAILABLE:
        async with get_db() as db:
            special_limits = await UserLimitCRUD.get_all(db)
            return special_limits or {}
    
    # Fallback to config.json
    if os.path.exists("config.json"):
        data = await read_json_file()
        return data.get("limits", {}).get("special", {})
    return {}


async def get_special_limit_list() -> list | None:
    """
    This function retrieves the list of special limits from database,
    and returns this list in a format suitable for messaging (split into shorter messages).

    Returns:
        list
    """
    if DB_AVAILABLE:
        async with get_db() as db:
            special_limits = await UserLimitCRUD.get_all(db)
            if not special_limits:
                return None
            special_list = "\n".join(
                [f"{key} : {value}" for key, value in special_limits.items()]
            )
            messages = special_list.split("\n")
            shorter_messages = [
                "\n".join(messages[i : i + 100]) for i in range(0, len(messages), 100)
            ]
            return shorter_messages
    
    # Fallback to config.json
    if os.path.exists("config.json"):
        data = await read_json_file()
        special_list = data.get("limits", {}).get("special", None)
        if not special_list:
            return None
        special_list = "\n".join(
            [f"{key} : {value}" for key, value in special_list.items()]
        )
        messages = special_list.split("\n")
        shorter_messages = [
            "\n".join(messages[i : i + 100]) for i in range(0, len(messages), 100)
        ]
        return shorter_messages
    return None


async def write_country_code_json(country_code: str) -> None:
    """
    Saves the country code to the database.
    Falls back to config.json if database is not available.

    Args:
        country_code: The country code to write.
    """
    if DB_AVAILABLE:
        async with get_db() as db:
            await ConfigCRUD.set(db, "country_code", country_code)
            await db.commit()
            await invalidate_config_cache()
            return
    
    # Fallback to config.json
    if os.path.exists("config.json"):
        data = await read_json_file()
    else:
        data = {}
    if "monitoring" not in data:
        data["monitoring"] = {}
    data["monitoring"]["ip_location"] = country_code
    await write_json_file(data)
    await invalidate_config_cache()


async def add_except_user(except_user: str) -> str | None:
    """
    Add a user to the exception list using database.
    Falls back to config.json if database is not available.
    """
    if DB_AVAILABLE:
        async with get_db() as db:
            await ExceptUserCRUD.add(db, except_user)
            await db.commit()
            return except_user
    
    # Fallback to config.json
    if os.path.exists("config.json"):
        data = await read_json_file()
        if "limits" not in data:
            data["limits"] = {}
        users = data.get("limits", {}).get("except_users", [])
        if except_user not in users:
            users.append(except_user)
            data["limits"]["except_users"] = users
            await write_json_file(data)
            return except_user
    else:
        data = {"limits": {"except_users": [except_user]}}
        await write_json_file(data)
        return except_user
    return None


async def show_except_users_handler() -> list | None:
    """
    Retrieve the list of exception users from the database.
    If the list is too long, it splits the list into shorter messages.
    """
    if DB_AVAILABLE:
        async with get_db() as db:
            except_users = await ExceptUserCRUD.get_all(db)
            if not except_users:
                return None
            except_users_str = "\n".join([f"{user}" for user in except_users])
            messages = except_users_str.split("\n")
            shorter_messages = [
                "\n".join(messages[i : i + 100]) for i in range(0, len(messages), 100)
            ]
            return shorter_messages
    
    # Fallback to config.json
    if os.path.exists("config.json"):
        data = await read_json_file()
        except_users = data.get("limits", {}).get("except_users", None)
        if not except_users:
            return None
        except_users = "\n".join([f"{key}" for key in except_users])
        messages = except_users.split("\n")
        shorter_messages = [
            "\n".join(messages[i : i + 100]) for i in range(0, len(messages), 100)
        ]
        return shorter_messages
    return None


async def remove_except_user_from_config(user: str) -> str | None:
    """
    Remove a user from the exception list using database.
    """
    if DB_AVAILABLE:
        async with get_db() as db:
            removed = await ExceptUserCRUD.remove(db, user)
            await db.commit()
            return user if removed else None
    
    # Fallback to config.json
    if not os.path.exists("config.json"):
        return None
    data = await read_json_file()
    except_users = data.get("limits", {}).get("except_users", [])
    if user in except_users:
        except_users.remove(user)
        data["limits"]["except_users"] = except_users
        await write_json_file(data)
        return user
    return None


async def save_general_limit(limit: int) -> int:
    """
    Save the general limit to the database.
    Falls back to config.json if database is not available.
    """
    if DB_AVAILABLE:
        async with get_db() as db:
            await ConfigCRUD.set(db, "general_limit", limit)
            await db.commit()
            return limit
    
    # Fallback to config.json
    if os.path.exists("config.json"):
        data = await read_json_file()
        if "limits" not in data:
            data["limits"] = {}
        data["limits"]["general"] = limit
        await write_json_file(data)
        return limit
    data = {"limits": {"general": limit}}
    await write_json_file(data)
    return limit


async def save_check_interval(interval: int) -> int:
    """
    Save the check interval to the database.
    Falls back to config.json if database is not available.
    """
    if DB_AVAILABLE:
        async with get_db() as db:
            await ConfigCRUD.set(db, "check_interval", interval)
            await db.commit()
            await invalidate_config_cache()
            return interval
    
    # Fallback to config.json
    if os.path.exists("config.json"):
        data = await read_json_file()
        if "monitoring" not in data:
            data["monitoring"] = {}
        data["monitoring"]["check_interval"] = interval
        await write_json_file(data)
        await invalidate_config_cache()
        return interval
    data = {"monitoring": {"check_interval": interval}}
    await write_json_file(data)
    await invalidate_config_cache()
    return interval


async def save_time_to_active_users(time_val: int) -> int:
    """
    Save the time to active users to the database.
    Falls back to config.json if database is not available.
    """
    if DB_AVAILABLE:
        async with get_db() as db:
            await ConfigCRUD.set(db, "time_to_active_users", time_val)
            await db.commit()
            await invalidate_config_cache()
            return time_val
    
    # Fallback to config.json
    if os.path.exists("config.json"):
        data = await read_json_file()
        if "monitoring" not in data:
            data["monitoring"] = {}
        data["monitoring"]["time_to_active_users"] = time_val
        await write_json_file(data)
        await invalidate_config_cache()
        return time_val
    data = {"monitoring": {"time_to_active_users": time_val}}
    await write_json_file(data)
    await invalidate_config_cache()
    return time_val
