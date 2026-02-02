"""
This module contains the DisabledUsers class
which provides methods for managing disabled users
"""

import json
import os
import time

from utils.logs import logger

DISABLED_USERS = set()
# Track when each user was disabled: {username: timestamp}
DISABLED_USERS_TIMESTAMPS = {}
# Track custom enable times: {username: enable_at_timestamp}
DISABLED_USERS_ENABLE_AT = {}


class DisabledUsers:
    """
    A class used to represent the Disabled Users.
    Now tracks the timestamp when each user was disabled and optional custom enable times.
    """

    def __init__(self, filename=".disable_users.json"):
        self.filename = filename
        self.disabled_users = {}  # {username: disabled_timestamp}
        self.enable_at = {}  # {username: enable_at_timestamp} - custom enable time
        self.load_disabled_users()

    def load_disabled_users(self):
        """
        Loads the disabled users from the JSON file.
        Now loads timestamps and custom enable times as well.
        """
        global DISABLED_USERS, DISABLED_USERS_TIMESTAMPS, DISABLED_USERS_ENABLE_AT
        try:
            if os.path.exists(self.filename):
                with open(self.filename, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    # Support both old format (list) and new format (dict with timestamps)
                    if "disable_user" in data:
                        old_users = data.get("disable_user", [])
                        if isinstance(old_users, list):
                            # Old format: convert to new format with current timestamp
                            current_time = time.time()
                            self.disabled_users = {user: current_time for user in old_users}
                        elif isinstance(old_users, dict):
                            # New format: dict with timestamps
                            self.disabled_users = old_users
                    elif "disabled_users" in data:
                        # New format key
                        self.disabled_users = data.get("disabled_users", {})
                    
                    # Load custom enable times
                    self.enable_at = data.get("enable_at", {})
                    
                    # Update globals
                    DISABLED_USERS = set(self.disabled_users.keys())
                    DISABLED_USERS_TIMESTAMPS = self.disabled_users.copy()
                    DISABLED_USERS_ENABLE_AT = self.enable_at.copy()
            else:
                self.disabled_users = {}
                self.enable_at = {}
                DISABLED_USERS = set()
                DISABLED_USERS_TIMESTAMPS = {}
                DISABLED_USERS_ENABLE_AT = {}
        except Exception as error:  # pylint: disable=broad-except
            logger.error(error)
            print("Check the error or delete the file :", error)
            print("Delete the .disable_users.json file? (y/n)")
            if input().lower() == "y":
                print("Deleting ...")
                logger.info("remove .disable_users.json file")
                os.remove(".disable_users.json")
            self.disabled_users = {}
            self.enable_at = {}
            DISABLED_USERS = set()
            DISABLED_USERS_TIMESTAMPS = {}
            DISABLED_USERS_ENABLE_AT = {}

    async def save_disabled_users(self):
        """
        Saves the disabled users with timestamps to the JSON file.
        """
        with open(self.filename, "w", encoding="utf-8") as file:
            json.dump({
                "disabled_users": self.disabled_users,
                "enable_at": self.enable_at
            }, file, indent=2)
        logger.info(f"Saved {len(self.disabled_users)} disabled users to {self.filename}")

    async def add_user(self, username: str, duration_seconds: int = 0, permanent: bool = False):
        """
        Adds a user to the set of disabled users with current timestamp
        and saves the updated data to the JSON file.
        
        Args:
            username: The username to disable
            duration_seconds: Optional custom duration in seconds. 
                              0 means use default time_to_active_users from config.
                              Ignored if permanent=True.
            permanent: If True, user will never be auto-enabled (until manual enable).
        """
        global DISABLED_USERS, DISABLED_USERS_TIMESTAMPS, DISABLED_USERS_ENABLE_AT
        current_time = time.time()
        DISABLED_USERS.add(username)
        DISABLED_USERS_TIMESTAMPS[username] = current_time
        self.disabled_users[username] = current_time
        
        if permanent:
            # Use -1 as sentinel value for permanent disable (never auto-enable)
            self.enable_at[username] = -1
            DISABLED_USERS_ENABLE_AT[username] = -1
            logger.info(f"User {username} disabled permanently at {time.strftime('%H:%M:%S', time.localtime(current_time))}, "
                       f"will NOT be auto-enabled (manual only)")
        elif duration_seconds > 0:
            # Set custom enable time if duration specified
            enable_at = current_time + duration_seconds
            self.enable_at[username] = enable_at
            DISABLED_USERS_ENABLE_AT[username] = enable_at
            enable_time = time.strftime('%H:%M:%S', time.localtime(enable_at))
            logger.info(f"User {username} disabled at {time.strftime('%H:%M:%S', time.localtime(current_time))}, "
                       f"will be enabled at {enable_time} ({duration_seconds}s)")
        else:
            # Remove any existing custom enable time
            if username in self.enable_at:
                del self.enable_at[username]
            if username in DISABLED_USERS_ENABLE_AT:
                del DISABLED_USERS_ENABLE_AT[username]
            # Log with default time
            enable_time = time.strftime('%H:%M:%S', time.localtime(current_time + 1800))  # 30 min default
            logger.info(f"User {username} disabled at {time.strftime('%H:%M:%S', time.localtime(current_time))}, "
                       f"will be enabled around {enable_time} (default)")
        
        await self.save_disabled_users()

    async def remove_user(self, username: str):
        """
        Removes a user from the disabled users set.
        """
        global DISABLED_USERS, DISABLED_USERS_TIMESTAMPS, DISABLED_USERS_ENABLE_AT
        if username in self.disabled_users:
            del self.disabled_users[username]
        if username in self.enable_at:
            del self.enable_at[username]
        if username in DISABLED_USERS:
            DISABLED_USERS.remove(username)
        if username in DISABLED_USERS_TIMESTAMPS:
            del DISABLED_USERS_TIMESTAMPS[username]
        if username in DISABLED_USERS_ENABLE_AT:
            del DISABLED_USERS_ENABLE_AT[username]
        await self.save_disabled_users()

    async def get_users_to_enable(self, default_time_to_active: int) -> list:
        """
        Returns a list of users who should be enabled now.
        Uses custom enable_at time if set, otherwise uses default_time_to_active.
        
        Args:
            default_time_to_active: Default time in seconds to wait before enabling
            
        Returns:
            List of usernames ready to be enabled
        """
        # Reload from file to get latest data
        self.load_disabled_users()
        
        current_time = time.time()
        users_to_enable = []
        
        if self.disabled_users:
            logger.info(f"Checking {len(self.disabled_users)} disabled users (default={default_time_to_active}s)")
        
        for username, disabled_time in list(self.disabled_users.items()):
            # Check if user has custom enable time
            if username in self.enable_at:
                enable_at = self.enable_at[username]
                # -1 means permanent disable - never auto-enable
                if enable_at == -1:
                    logger.debug(f"User {username} is permanently disabled (manual enable only)")
                    continue
                if current_time >= enable_at:
                    users_to_enable.append(username)
                    logger.info(f"User {username} ready to enable (custom timer expired)")
                else:
                    remaining = int(enable_at - current_time)
                    logger.debug(f"User {username} has {remaining}s remaining on custom timer")
            else:
                # Use default time_to_active
                elapsed = current_time - disabled_time
                remaining = default_time_to_active - elapsed
                if elapsed >= default_time_to_active:
                    users_to_enable.append(username)
                    logger.info(f"User {username} ready to enable (disabled {int(elapsed)}s ago)")
                else:
                    logger.debug(f"User {username} needs {int(remaining)}s more before enable")
        
        return users_to_enable

    def get_user_remaining_time(self, username: str, default_time_to_active: int) -> int:
        """
        Get remaining disable time for a user in seconds.
        
        Args:
            username: The username to check
            default_time_to_active: Default time in seconds
            
        Returns:
            Remaining seconds, 0 if ready to enable, -1 if not disabled, -2 if permanent
        """
        if username not in self.disabled_users:
            return -1
        
        current_time = time.time()
        disabled_time = self.disabled_users[username]
        
        if username in self.enable_at:
            enable_at = self.enable_at[username]
            # -1 means permanent disable
            if enable_at == -1:
                return -2  # Special code for permanent
            remaining = enable_at - current_time
        else:
            elapsed = current_time - disabled_time
            remaining = default_time_to_active - elapsed
        
        return max(0, int(remaining))

    async def read_and_clear_users(self):
        """
        Returns a list of all disabled users, clears the set
        and saves the empty data to the JSON file.
        """
        global DISABLED_USERS, DISABLED_USERS_TIMESTAMPS, DISABLED_USERS_ENABLE_AT
        disabled_users = list(self.disabled_users.keys())
        self.disabled_users.clear()
        self.enable_at.clear()
        DISABLED_USERS.clear()
        DISABLED_USERS_TIMESTAMPS.clear()
        DISABLED_USERS_ENABLE_AT.clear()
        await self.save_disabled_users()
        return set(disabled_users)
