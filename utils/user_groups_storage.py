"""
This module handles storing and retrieving user's original groups
before they were moved to the disabled group.
"""

import json
import os
import time

from utils.logs import logger

# In-memory cache
USER_ORIGINAL_GROUPS = {}


class UserGroupsStorage:
    """
    A class to manage storing and retrieving user's original groups.
    When a user is disabled (moved to disabled group), we save their
    original groups so we can restore them when re-enabling.
    """

    def __init__(self, filename=".user_groups_backup.json"):
        self.filename = filename
        self.user_groups = {}  # {username: {"groups": [group_ids], "saved_at": timestamp}}
        self.load_data()

    def load_data(self):
        """Load user groups data from the JSON file."""
        global USER_ORIGINAL_GROUPS
        try:
            if os.path.exists(self.filename):
                with open(self.filename, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    self.user_groups = data.get("user_groups", {})
                    USER_ORIGINAL_GROUPS = self.user_groups.copy()
                    logger.info(f"Loaded {len(self.user_groups)} user groups from {self.filename}")
            else:
                self.user_groups = {}
                USER_ORIGINAL_GROUPS = {}
        except Exception as error:
            logger.error(f"Error loading user groups: {error}")
            self.user_groups = {}
            USER_ORIGINAL_GROUPS = {}

    async def save_data(self):
        """Save user groups data to the JSON file."""
        try:
            with open(self.filename, "w", encoding="utf-8") as file:
                json.dump({"user_groups": self.user_groups}, file, indent=2)
            logger.info(f"Saved {len(self.user_groups)} user groups to {self.filename}")
        except Exception as error:
            logger.error(f"Error saving user groups: {error}")

    async def save_user_groups(self, username: str, group_ids: list[int]):
        """
        Save user's original groups before moving to disabled group.
        
        Args:
            username: The username
            group_ids: List of group IDs the user had before being disabled
        """
        global USER_ORIGINAL_GROUPS
        current_time = time.time()
        self.user_groups[username] = {
            "groups": group_ids,
            "saved_at": current_time
        }
        USER_ORIGINAL_GROUPS = self.user_groups.copy()
        await self.save_data()
        logger.info(f"Saved original groups for {username}: {group_ids}")

    async def get_user_groups(self, username: str) -> list[int] | None:
        """
        Get user's original groups that were saved.
        
        Args:
            username: The username
            
        Returns:
            List of group IDs or None if not found
        """
        # Reload from file to get latest data
        self.load_data()
        
        if username in self.user_groups:
            return self.user_groups[username].get("groups", None)
        return None

    async def remove_user(self, username: str):
        """
        Remove user's saved groups after re-enabling.
        
        Args:
            username: The username
        """
        global USER_ORIGINAL_GROUPS
        if username in self.user_groups:
            del self.user_groups[username]
            USER_ORIGINAL_GROUPS = self.user_groups.copy()
            await self.save_data()
            logger.info(f"Removed saved groups for {username}")

    async def has_saved_groups(self, username: str) -> bool:
        """
        Check if user has saved groups.
        
        Args:
            username: The username
            
        Returns:
            True if user has saved groups
        """
        self.load_data()
        return username in self.user_groups

    async def get_all_users_with_saved_groups(self) -> list[str]:
        """
        Get list of all usernames that have saved groups.
        
        Returns:
            List of usernames
        """
        self.load_data()
        return list(self.user_groups.keys())

    async def clear_all(self):
        """Clear all saved user groups."""
        global USER_ORIGINAL_GROUPS
        self.user_groups.clear()
        USER_ORIGINAL_GROUPS = {}
        await self.save_data()
        logger.info("Cleared all saved user groups")
