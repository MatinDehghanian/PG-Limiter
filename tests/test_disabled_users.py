#!/usr/bin/env python3
"""
Tests for DisabledUsers management
Tests disable/enable functionality, timestamps, and persistence.
"""

import os
import json
import time
import pytest
from unittest.mock import patch, AsyncMock


class TestDisabledUsers:
    """Tests for DisabledUsers class"""
    
    @pytest.fixture
    def temp_disabled_file(self, tmp_path):
        """Create a temporary disabled users file"""
        filepath = tmp_path / "test_disabled.json"
        return str(filepath)
    
    @pytest.fixture
    def disabled_users_instance(self, temp_disabled_file):
        """Create a DisabledUsers instance with temp file"""
        from utils.handel_dis_users import DisabledUsers
        return DisabledUsers(filename=temp_disabled_file)
    
    def test_initialization_empty(self, temp_disabled_file):
        """Test initialization with no existing file"""
        from utils.handel_dis_users import DisabledUsers
        
        dus = DisabledUsers(filename=temp_disabled_file)
        assert len(dus.disabled_users) == 0
        assert len(dus.enable_at) == 0
    
    def test_initialization_existing_file(self, temp_disabled_file):
        """Test initialization with existing file"""
        from utils.handel_dis_users import DisabledUsers
        
        # Create existing file
        existing_data = {
            "disabled_users": {"user1": 1234567890.0},
            "enable_at": {"user1": 1234567900.0}
        }
        with open(temp_disabled_file, "w") as f:
            json.dump(existing_data, f)
        
        dus = DisabledUsers(filename=temp_disabled_file)
        assert "user1" in dus.disabled_users
        assert "user1" in dus.enable_at
    
    @pytest.mark.asyncio
    async def test_add_user(self, disabled_users_instance):
        """Test adding a user to disabled list"""
        await disabled_users_instance.add_user("test_user")
        
        assert "test_user" in disabled_users_instance.disabled_users
        assert disabled_users_instance.disabled_users["test_user"] > 0
    
    @pytest.mark.asyncio
    async def test_add_user_with_duration(self, disabled_users_instance):
        """Test adding a user with custom disable duration"""
        duration = 3600  # 1 hour
        current_time = time.time()
        
        await disabled_users_instance.add_user("timed_user", duration_seconds=duration)
        
        assert "timed_user" in disabled_users_instance.disabled_users
        assert "timed_user" in disabled_users_instance.enable_at
        
        enable_time = disabled_users_instance.enable_at["timed_user"]
        # Should be within 5 seconds of expected time
        assert abs(enable_time - (current_time + duration)) < 5
    
    @pytest.mark.asyncio
    async def test_remove_user(self, disabled_users_instance):
        """Test removing a user from disabled list"""
        await disabled_users_instance.add_user("to_remove")
        assert "to_remove" in disabled_users_instance.disabled_users
        
        await disabled_users_instance.remove_user("to_remove")
        assert "to_remove" not in disabled_users_instance.disabled_users
    
    def test_is_disabled(self, disabled_users_instance):
        """Test checking if user is disabled"""
        # Not disabled - should not be in disabled_users dict
        assert "unknown_user" not in disabled_users_instance.disabled_users
    
    @pytest.mark.asyncio
    async def test_save_and_load(self, temp_disabled_file):
        """Test saving and loading disabled users"""
        from utils.handel_dis_users import DisabledUsers
        
        # Create and add user
        dus1 = DisabledUsers(filename=temp_disabled_file)
        await dus1.add_user("persistent_user", duration_seconds=1800)
        await dus1.save_disabled_users()
        
        # Load in new instance
        dus2 = DisabledUsers(filename=temp_disabled_file)
        assert "persistent_user" in dus2.disabled_users
        assert "persistent_user" in dus2.enable_at
    
    def test_legacy_format_migration(self, temp_disabled_file):
        """Test migration from old list format to new dict format"""
        from utils.handel_dis_users import DisabledUsers
        
        # Create old format file
        old_format = {"disable_user": ["user1", "user2"]}
        with open(temp_disabled_file, "w") as f:
            json.dump(old_format, f)
        
        # Load should migrate to new format
        dus = DisabledUsers(filename=temp_disabled_file)
        
        assert "user1" in dus.disabled_users
        assert "user2" in dus.disabled_users
        # Timestamps should be set
        assert isinstance(dus.disabled_users["user1"], float)
    
    @pytest.mark.asyncio
    async def test_get_users_to_enable(self, disabled_users_instance):
        """Test finding users ready to be re-enabled"""
        current_time = time.time()
        
        # Add user with expired disable time
        disabled_users_instance.disabled_users["expired_user"] = current_time - 100
        disabled_users_instance.enable_at["expired_user"] = current_time - 50
        
        # Add user still disabled
        disabled_users_instance.disabled_users["active_user"] = current_time
        disabled_users_instance.enable_at["active_user"] = current_time + 3600
        
        # Save state first
        await disabled_users_instance.save_disabled_users()
        
        ready = await disabled_users_instance.get_users_to_enable(60)
        
        assert "expired_user" in ready
        assert "active_user" not in ready
    
    @pytest.mark.asyncio
    async def test_remove_users(self, disabled_users_instance):
        """Test removing disabled users"""
        await disabled_users_instance.add_user("user1")
        await disabled_users_instance.add_user("user2")
        
        assert len(disabled_users_instance.disabled_users) >= 2
        
        await disabled_users_instance.remove_user("user1")
        await disabled_users_instance.remove_user("user2")
        
        assert "user1" not in disabled_users_instance.disabled_users
        assert "user2" not in disabled_users_instance.disabled_users


class TestDisabledUsersGlobals:
    """Tests for global disabled users state"""
    
    @pytest.mark.asyncio
    async def test_globals_updated_on_add(self, tmp_path):
        """Test that disabled users dict is updated when adding"""
        from utils.handel_dis_users import DisabledUsers
        
        temp_file = tmp_path / "globals_test.json"
        dus = DisabledUsers(filename=str(temp_file))
        
        await dus.add_user("global_test_user")
        
        # Local instance dict should be updated
        assert "global_test_user" in dus.disabled_users
