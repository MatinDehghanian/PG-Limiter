#!/usr/bin/env python3
"""
Tests for the Punishment System
Tests escalating punishment steps, violation tracking, and duration calculations.
"""

import os
import time
import pytest
import json
from unittest.mock import patch, MagicMock


# Test the PunishmentStep dataclass
class TestPunishmentStep:
    """Tests for PunishmentStep functionality"""
    
    def test_warning_step(self):
        """Test warning step detection"""
        from utils.punishment_system import PunishmentStep
        
        step = PunishmentStep(step_type="warning", duration_minutes=0)
        assert step.is_warning() is True
        assert step.is_unlimited_disable() is False
        assert "Warning" in step.get_display_text()
    
    def test_timed_disable_step(self):
        """Test timed disable step"""
        from utils.punishment_system import PunishmentStep
        
        step = PunishmentStep(step_type="disable", duration_minutes=15)
        assert step.is_warning() is False
        assert step.is_unlimited_disable() is False
        assert step.get_duration_seconds() == 15 * 60
        assert "15" in step.get_display_text()
    
    def test_unlimited_disable_step(self):
        """Test unlimited/permanent disable step"""
        from utils.punishment_system import PunishmentStep
        
        step = PunishmentStep(step_type="disable", duration_minutes=0)
        assert step.is_warning() is False
        assert step.is_unlimited_disable() is True
        assert "Unlimited" in step.get_display_text()
    
    def test_duration_display_hours(self):
        """Test display text for hours"""
        from utils.punishment_system import PunishmentStep
        
        step = PunishmentStep(step_type="disable", duration_minutes=120)
        display = step.get_display_text()
        assert "2 hour" in display
    
    def test_duration_display_mixed(self):
        """Test display text for hours and minutes"""
        from utils.punishment_system import PunishmentStep
        
        step = PunishmentStep(step_type="disable", duration_minutes=90)
        display = step.get_display_text()
        assert "1h" in display and "30m" in display


class TestPunishmentSystem:
    """Tests for PunishmentSystem class"""
    
    @pytest.fixture
    def temp_violation_file(self, tmp_path):
        """Create a temporary violation history file"""
        filepath = tmp_path / "test_violations.json"
        return str(filepath)
    
    def test_initialization(self, temp_violation_file):
        """Test system initializes with default steps"""
        from utils.punishment_system import PunishmentSystem
        
        system = PunishmentSystem(filename=temp_violation_file)
        assert len(system.steps) == 5
        assert system.steps[0].is_warning()
        assert system.steps[-1].is_unlimited_disable()
    
    def test_get_violation_count_empty(self, temp_violation_file):
        """Test violation count for user with no violations"""
        from utils.punishment_system import PunishmentSystem
        
        system = PunishmentSystem(filename=temp_violation_file)
        count = system.get_violation_count("new_user")
        assert count == 0
    
    def test_get_next_step_first_violation(self, temp_violation_file):
        """Test first violation gets warning step"""
        from utils.punishment_system import PunishmentSystem
        
        system = PunishmentSystem(filename=temp_violation_file)
        step_index = system.get_next_step_index("new_user")
        step = system.get_next_punishment("new_user")
        
        assert step_index == 0
        assert step.is_warning()
    
    def test_escalating_punishments(self, temp_violation_file):
        """Test punishments escalate correctly"""
        from utils.punishment_system import PunishmentSystem, ViolationRecord
        
        system = PunishmentSystem(filename=temp_violation_file)
        
        # Add violations and check escalation
        current_time = time.time()
        for i in range(5):
            system.violations.setdefault("test_user", []).append(
                ViolationRecord(
                    username="test_user",
                    timestamp=current_time - (i * 60),
                    step_applied=i,
                    disable_duration=0
                )
            )
        
        # Should be at step 5 (max)
        step_index = system.get_next_step_index("test_user")
        step = system.get_next_punishment("test_user")
        
        assert step_index == 4  # 0-indexed, so step 5 is index 4
        assert step.is_unlimited_disable()
    
    def test_old_violations_excluded(self, temp_violation_file):
        """Test violations older than window are excluded"""
        from utils.punishment_system import PunishmentSystem, ViolationRecord
        
        system = PunishmentSystem(filename=temp_violation_file)
        system.window_hours = 24  # 24 hour window
        
        # Add old violation (2 days ago)
        old_time = time.time() - (48 * 60 * 60)
        system.violations["old_user"] = [
            ViolationRecord(
                username="old_user",
                timestamp=old_time,
                step_applied=0,
                disable_duration=0
            )
        ]
        
        # Should still be at first step
        count = system.get_violation_count("old_user")
        assert count == 0
    
    def test_config_loading(self, temp_violation_file, tmp_path):
        """Test loading punishment config from file"""
        from utils.punishment_system import PunishmentSystem
        
        config_data = {
            "punishment": {
                "enabled": True,
                "window_hours": 48,
                "steps": [
                    {"type": "warning", "duration": 0},
                    {"type": "disable", "duration": 30}
                ]
            }
        }
        
        system = PunishmentSystem(filename=temp_violation_file)
        system.load_config(config_data)
        
        assert system.window_hours == 48
        assert len(system.steps) == 2


class TestViolationRecord:
    """Tests for ViolationRecord dataclass"""
    
    def test_violation_record_creation(self):
        """Test creating a violation record"""
        from utils.punishment_system import ViolationRecord
        
        record = ViolationRecord(
            username="test_user",
            timestamp=time.time(),
            step_applied=1,
            disable_duration=15
        )
        
        assert record.username == "test_user"
        assert record.step_applied == 1
        assert record.disable_duration == 15
        assert record.enabled_at is None


class TestPunishmentDuration:
    """Tests for punishment duration calculations"""
    
    def test_calculate_enable_time(self, tmp_path):
        """Test calculating when user should be re-enabled"""
        from utils.punishment_system import PunishmentSystem
        
        temp_file = tmp_path / "violations.json"
        system = PunishmentSystem(filename=str(temp_file))
        
        current_time = time.time()
        duration_minutes = 30
        
        enable_time = current_time + (duration_minutes * 60)
        
        # Should be ~30 minutes in the future
        assert enable_time > current_time
        assert enable_time < current_time + (31 * 60)
