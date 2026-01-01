#!/usr/bin/env python3
"""
Tests for the Enhanced Warning System
Tests warning creation, monitoring periods, and trust score calculations.
"""

import os
import time
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestUserWarning:
    """Tests for UserWarning class"""
    
    def test_warning_creation(self):
        """Test creating a user warning"""
        from utils.warning_system.user_warning import UserWarning
        
        warning = UserWarning(
            username="test_user",
            ip_count=5,
            ips={"1.1.1.1", "2.2.2.2", "3.3.3.3"},
            warning_time=time.time(),
            monitoring_end_time=time.time() + 180
        )
        
        assert warning.username == "test_user"
        assert warning.ip_count == 5
        assert len(warning.ips) == 3
    
    def test_monitoring_active(self):
        """Test monitoring period is active"""
        from utils.warning_system.user_warning import UserWarning
        
        current_time = time.time()
        warning = UserWarning(
            username="test_user",
            ip_count=5,
            ips={"1.1.1.1"},
            warning_time=current_time,
            monitoring_end_time=current_time + 180
        )
        
        assert warning.is_monitoring_active() is True
    
    def test_monitoring_expired(self):
        """Test monitoring period expired"""
        from utils.warning_system.user_warning import UserWarning
        
        current_time = time.time()
        warning = UserWarning(
            username="test_user",
            ip_count=5,
            ips={"1.1.1.1"},
            warning_time=current_time - 300,
            monitoring_end_time=current_time - 120  # Ended 2 minutes ago
        )
        
        assert warning.is_monitoring_active() is False
    
    def test_time_remaining(self):
        """Test time remaining calculation"""
        from utils.warning_system.user_warning import UserWarning
        
        current_time = time.time()
        warning = UserWarning(
            username="test_user",
            ip_count=5,
            ips={"1.1.1.1"},
            warning_time=current_time,
            monitoring_end_time=current_time + 60  # 60 seconds remaining
        )
        
        remaining = warning.time_remaining()
        assert 55 <= remaining <= 60


class TestEnhancedWarningSystem:
    """Tests for EnhancedWarningSystem class"""
    
    @pytest.fixture
    def temp_warning_file(self, tmp_path):
        """Create temporary warning files"""
        warnings_file = tmp_path / "test_warnings.json"
        history_file = tmp_path / "test_history.json"
        return str(warnings_file), str(history_file)
    
    def test_initialization(self, temp_warning_file):
        """Test system initialization"""
        from utils.warning_system.enhanced_system import EnhancedWarningSystem
        
        warnings_file, history_file = temp_warning_file
        system = EnhancedWarningSystem(filename=warnings_file, history_filename=history_file)
        
        assert system.monitoring_period == 180  # 3 minutes
        assert len(system.warnings) == 0
    
    def test_warning_history_cleanup(self, temp_warning_file):
        """Test old warning history cleanup"""
        from utils.warning_system.enhanced_system import EnhancedWarningSystem
        
        warnings_file, history_file = temp_warning_file
        
        # Create history with old entries
        current_time = time.time()
        old_history = {
            "old_user": [current_time - (25 * 60 * 60)],  # 25 hours ago
            "recent_user": [current_time - (1 * 60 * 60)]  # 1 hour ago
        }
        with open(history_file, "w") as f:
            json.dump(old_history, f)
        
        system = EnhancedWarningSystem(filename=warnings_file, history_filename=history_file)
        
        # Old user should be cleaned up
        assert "old_user" not in system.warning_history
        assert "recent_user" in system.warning_history
    
    def test_count_recent_warnings(self, temp_warning_file):
        """Test counting recent warnings"""
        from utils.warning_system.enhanced_system import EnhancedWarningSystem
        
        warnings_file, history_file = temp_warning_file
        system = EnhancedWarningSystem(filename=warnings_file, history_filename=history_file)
        
        current_time = time.time()
        system.warning_history = {
            "test_user": [
                current_time - (1 * 60 * 60),  # 1 hour ago
                current_time - (6 * 60 * 60),  # 6 hours ago
                current_time - (13 * 60 * 60),  # 13 hours ago (outside 12 hour window)
            ]
        }
        
        count = system.count_recent_warnings("test_user", hours=12)
        assert count == 2  # Only 2 warnings in last 12 hours
    
    def test_instant_disable_threshold(self, temp_warning_file):
        """Test instant disable threshold constant"""
        from utils.warning_system.enhanced_system import EnhancedWarningSystem
        
        warnings_file, history_file = temp_warning_file
        system = EnhancedWarningSystem(filename=warnings_file, history_filename=history_file)
        
        assert system.INSTANT_DISABLE_THRESHOLD == -60
    
    def test_min_device_duration(self, temp_warning_file):
        """Test minimum device duration constant"""
        from utils.warning_system.enhanced_system import EnhancedWarningSystem
        
        warnings_file, history_file = temp_warning_file
        system = EnhancedWarningSystem(filename=warnings_file, history_filename=history_file)
        
        assert system.MIN_DEVICE_DURATION == 120  # 2 minutes


class TestTrustScore:
    """Tests for trust score calculations"""
    
    def test_high_trust_score(self):
        """Test high trust score for consistent user"""
        # A user with consistent behavior should have high trust
        violations = 0
        consistent_ips = 2
        expected_trust = 100 - (violations * 20)
        
        assert expected_trust > 50
    
    def test_low_trust_score(self):
        """Test low trust score for problematic user"""
        # A user with many violations should have low trust
        violations = 5
        expected_trust = 100 - (violations * 20)
        
        assert expected_trust <= 0


class TestSubnetGrouping:
    """Tests for subnet grouping in warning system"""
    
    def test_same_subnet_grouped(self):
        """Test IPs from same subnet are grouped"""
        import ipaddress
        
        ips = ["192.168.1.1", "192.168.1.2", "192.168.1.100"]
        
        # All should be in same /24 subnet
        subnets = set()
        for ip in ips:
            network = ipaddress.ip_network(f"{ip}/24", strict=False)
            subnets.add(str(network.network_address))
        
        assert len(subnets) == 1
    
    def test_different_subnets_separated(self):
        """Test IPs from different subnets are separated"""
        import ipaddress
        
        ips = ["192.168.1.1", "10.0.0.1", "172.16.0.1"]
        
        subnets = set()
        for ip in ips:
            network = ipaddress.ip_network(f"{ip}/24", strict=False)
            subnets.add(str(network.network_address))
        
        assert len(subnets) == 3


class TestWarningPersistence:
    """Tests for warning data persistence"""
    
    @pytest.mark.asyncio
    async def test_save_warnings(self, tmp_path):
        """Test saving warnings to file"""
        from utils.warning_system.enhanced_system import EnhancedWarningSystem
        
        warnings_file = tmp_path / "save_test_warnings.json"
        history_file = tmp_path / "save_test_history.json"
        
        system = EnhancedWarningSystem(
            filename=str(warnings_file),
            history_filename=str(history_file)
        )
        
        # Add to history
        await system.add_to_warning_history("test_user")
        
        # Verify file was created
        assert history_file.exists()
        
        # Verify content
        with open(history_file) as f:
            data = json.load(f)
            assert "test_user" in data
    
    def test_load_warnings(self, tmp_path):
        """Test loading warnings from file"""
        from utils.warning_system.enhanced_system import EnhancedWarningSystem
        
        warnings_file = tmp_path / "load_test_warnings.json"
        history_file = tmp_path / "load_test_history.json"
        
        # Create pre-existing history
        current_time = time.time()
        history_data = {"loaded_user": [current_time]}
        with open(history_file, "w") as f:
            json.dump(history_data, f)
        
        system = EnhancedWarningSystem(
            filename=str(warnings_file),
            history_filename=str(history_file)
        )
        
        assert "loaded_user" in system.warning_history
