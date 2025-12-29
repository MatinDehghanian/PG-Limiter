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


class DisabledUsers:
    """
    A class used to represent the Disabled Users.
    Now tracks the timestamp when each user was disabled.
    """

    def __init__(self, filename=".disable_users.json"):
        self.filename = filename
        self.disabled_users = {}  # Changed to dict: {username: disabled_timestamp}
        self.load_disabled_users()

    def load_disabled_users(self):
        """
        Loads the disabled users from the JSON file.
        Now loads timestamps as well.
        """
        global DISABLED_USERS, DISABLED_USERS_TIMESTAMPS
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
                    
                    # Update globals
                    DISABLED_USERS = set(self.disabled_users.keys())
                    DISABLED_USERS_TIMESTAMPS = self.disabled_users.copy()
            else:
                self.disabled_users = {}
                DISABLED_USERS = set()
                DISABLED_USERS_TIMESTAMPS = {}
        except Exception as error:  # pylint: disable=broad-except
            logger.error(error)
            print("Check the error or delete the file :", error)
            print("Delete the .disable_users.json file? (y/n)")
            if input().lower() == "y":
                print("Deleting ...")
                logger.info("remove .disable_users.json file")
                os.remove(".disable_users.json")
            self.disabled_users = {}
            DISABLED_USERS = set()
            DISABLED_USERS_TIMESTAMPS = {}

    async def save_disabled_users(self):
        """
        Saves the disabled users with timestamps to the JSON file.
        """
        with open(self.filename, "w", encoding="utf-8") as file:
            json.dump({"disabled_users": self.disabled_users}, file, indent=2)
        logger.info(f"Saved {len(self.disabled_users)} disabled users to {self.filename}")

    async def add_user(self, username: str):
        """
        Adds a user to the set of disabled users with current timestamp
        and saves the updated data to the JSON file.
        """
        global DISABLED_USERS, DISABLED_USERS_TIMESTAMPS
        current_time = time.time()
        DISABLED_USERS.add(username)
        DISABLED_USERS_TIMESTAMPS[username] = current_time
        self.disabled_users[username] = current_time
        await self.save_disabled_users()
        enable_time = time.strftime('%H:%M:%S', time.localtime(current_time + 1800))  # 30 min later
        logger.info(f"User {username} disabled at {time.strftime('%H:%M:%S', time.localtime(current_time))}, will be enabled around {enable_time}")

    async def remove_user(self, username: str):
        """
        Removes a user from the disabled users set.
        """
        global DISABLED_USERS, DISABLED_USERS_TIMESTAMPS
        if username in self.disabled_users:
            del self.disabled_users[username]
        if username in DISABLED_USERS:
            DISABLED_USERS.remove(username)
        if username in DISABLED_USERS_TIMESTAMPS:
            del DISABLED_USERS_TIMESTAMPS[username]
        await self.save_disabled_users()

    async def get_users_to_enable(self, time_to_active: int) -> list:
        """
        Returns a list of users who have been disabled for longer than time_to_active seconds.
        """
        # Reload from file to get latest data
        self.load_disabled_users()
        
        current_time = time.time()
        users_to_enable = []
        
        if self.disabled_users:
            logger.info(f"Checking {len(self.disabled_users)} disabled users (time_to_active={time_to_active}s)")
        
        for username, disabled_time in list(self.disabled_users.items()):
            elapsed = current_time - disabled_time
            remaining = time_to_active - elapsed
            if elapsed >= time_to_active:
                users_to_enable.append(username)
                logger.info(f"User {username} ready to enable (disabled {int(elapsed)}s ago)")
            else:
                logger.debug(f"User {username} needs {int(remaining)}s more before enable")
        
        return users_to_enable

    async def read_and_clear_users(self):
        """
        Returns a list of all disabled users, clears the set
        and saves the empty data to the JSON file.
        """
        global DISABLED_USERS, DISABLED_USERS_TIMESTAMPS
        disabled_users = list(self.disabled_users.keys())
        self.disabled_users.clear()
        DISABLED_USERS.clear()
        DISABLED_USERS_TIMESTAMPS.clear()
        await self.save_disabled_users()
        return set(disabled_users)
