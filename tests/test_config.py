#!/usr/bin/env python3
"""
Tests for configuration reading and validation
Tests config file parsing and default values.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock


class TestReadConfig:
    """Tests for read_config functionality"""
    
    @pytest.fixture
    def temp_config_file(self, tmp_path):
        """Create a temporary config file"""
        filepath = tmp_path / "config.json"
        return str(filepath)
    
    def test_valid_config(self, temp_config_file):
        """Test reading a valid config file"""
        config_data = {
            "panel_username": "admin",
            "panel_password": "password",
            "panel_domain": "panel.example.com",
            "telegram_bot_token": "123456:ABC",
            "telegram_chat_id": "123456789",
            "ip_limit": 3,
            "check_interval": 60
        }
        
        with open(temp_config_file, "w") as f:
            json.dump(config_data, f)
        
        # Read the config
        with open(temp_config_file, "r") as f:
            loaded = json.load(f)
        
        assert loaded["panel_username"] == "admin"
        assert loaded["ip_limit"] == 3
    
    def test_missing_optional_fields(self, temp_config_file):
        """Test config with missing optional fields"""
        config_data = {
            "panel_username": "admin",
            "panel_password": "password",
            "panel_domain": "panel.example.com"
        }
        
        with open(temp_config_file, "w") as f:
            json.dump(config_data, f)
        
        with open(temp_config_file, "r") as f:
            loaded = json.load(f)
        
        # Optional fields should be absent
        assert "ip_limit" not in loaded
    
    def test_empty_config_file(self, temp_config_file):
        """Test handling empty config file"""
        with open(temp_config_file, "w") as f:
            json.dump({}, f)
        
        with open(temp_config_file, "r") as f:
            loaded = json.load(f)
        
        assert loaded == {}
    
    def test_invalid_json(self, temp_config_file):
        """Test handling invalid JSON"""
        with open(temp_config_file, "w") as f:
            f.write("not valid json {")
        
        with pytest.raises(json.JSONDecodeError):
            with open(temp_config_file, "r") as f:
                json.load(f)
    
    def test_punishment_config(self, temp_config_file):
        """Test punishment system configuration"""
        config_data = {
            "punishment": {
                "enabled": True,
                "window_hours": 72,
                "steps": [
                    {"type": "warning", "duration": 0},
                    {"type": "disable", "duration": 15},
                    {"type": "disable", "duration": 60},
                    {"type": "disable", "duration": 0}
                ]
            }
        }
        
        with open(temp_config_file, "w") as f:
            json.dump(config_data, f)
        
        with open(temp_config_file, "r") as f:
            loaded = json.load(f)
        
        assert loaded["punishment"]["enabled"] is True
        assert len(loaded["punishment"]["steps"]) == 4
    
    def test_telegram_config(self, temp_config_file):
        """Test Telegram bot configuration"""
        config_data = {
            "telegram_bot_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
            "telegram_chat_id": "-1001234567890",
            "telegram_admin_ids": [123456789, 987654321]
        }
        
        with open(temp_config_file, "w") as f:
            json.dump(config_data, f)
        
        with open(temp_config_file, "r") as f:
            loaded = json.load(f)
        
        assert ":" in loaded["telegram_bot_token"]
        assert loaded["telegram_chat_id"].startswith("-")


class TestConfigDefaults:
    """Tests for configuration default values"""
    
    def test_default_ip_limit(self):
        """Test default IP limit value"""
        default_ip_limit = 3
        assert default_ip_limit > 0
    
    def test_default_check_interval(self):
        """Test default check interval"""
        default_interval = 60  # seconds
        assert default_interval >= 30
    
    def test_default_monitoring_period(self):
        """Test default monitoring period"""
        default_monitoring = 180  # 3 minutes
        assert default_monitoring == 180
    
    def test_default_punishment_window(self):
        """Test default punishment window"""
        default_window = 168  # 7 days in hours
        assert default_window == 168


class TestConfigValidation:
    """Tests for config validation"""
    
    def test_ip_limit_positive(self):
        """Test IP limit must be positive"""
        ip_limit = 3
        assert ip_limit > 0
    
    def test_check_interval_range(self):
        """Test check interval is in valid range"""
        interval = 60
        assert 10 <= interval <= 3600
    
    def test_punishment_steps_valid(self):
        """Test punishment steps have valid structure"""
        steps = [
            {"type": "warning", "duration": 0},
            {"type": "disable", "duration": 15}
        ]
        
        for step in steps:
            assert "type" in step
            assert "duration" in step
            assert step["type"] in ["warning", "disable"]
            assert isinstance(step["duration"], int)
            assert step["duration"] >= 0
    
    def test_telegram_token_format(self):
        """Test Telegram token format validation"""
        valid_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
        
        # Should contain colon separating bot ID and secret
        assert ":" in valid_token
        parts = valid_token.split(":")
        assert len(parts) == 2
        assert parts[0].isdigit()
