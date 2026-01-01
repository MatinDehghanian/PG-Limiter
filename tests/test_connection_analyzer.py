#!/usr/bin/env python3
"""
Tests for Connection Analyzer functionality
Tests IP-Node-Inbound relationship tracking and reporting.
"""

import time
import pytest
from unittest.mock import patch, MagicMock


class TestConnectionInfo:
    """Tests for ConnectionInfo tracking"""
    
    def test_connection_creation(self):
        """Test creating connection info"""
        from utils.types import ConnectionInfo
        
        conn = ConnectionInfo(
            ip="192.168.1.1",
            node_id=1,
            node_name="Germany-Node",
            inbound_protocol="VLESS",
            last_seen=time.time(),
            connection_count=5
        )
        
        assert conn.ip == "192.168.1.1"
        assert conn.node_id == 1
        assert conn.node_name == "Germany-Node"
        assert conn.inbound_protocol == "VLESS"
        assert conn.connection_count == 5


class TestDeviceInfo:
    """Tests for DeviceInfo aggregation"""
    
    def test_multi_device_detection(self):
        """Test multi-device detection"""
        from utils.types import DeviceInfo, ConnectionInfo
        
        # User with multiple IPs from different subnets
        connections = [
            ConnectionInfo("1.1.1.1", 1, "Node1", "VLESS", time.time(), 3),
            ConnectionInfo("2.2.2.2", 1, "Node1", "VLESS", time.time(), 2),
            ConnectionInfo("3.3.3.3", 2, "Node2", "VMESS", time.time(), 1)
        ]
        
        device = DeviceInfo(
            unique_ips={"1.1.1.1", "2.2.2.2", "3.3.3.3"},
            unique_nodes={1, 2},
            inbound_protocols={"VLESS", "VMESS"},
            is_multi_device=True,
            connections=connections
        )
        
        assert device.is_multi_device is True
        assert len(device.unique_ips) == 3
        assert len(device.unique_nodes) == 2
    
    def test_single_device(self):
        """Test single device user"""
        from utils.types import DeviceInfo, ConnectionInfo
        
        connections = [
            ConnectionInfo("192.168.1.1", 1, "Node1", "VLESS", time.time(), 10)
        ]
        
        device = DeviceInfo(
            unique_ips={"192.168.1.1"},
            unique_nodes={1},
            inbound_protocols={"VLESS"},
            is_multi_device=False,
            connections=connections
        )
        
        assert device.is_multi_device is False
        assert len(device.unique_ips) == 1


class TestConnectionReport:
    """Tests for connection report generation"""
    
    @pytest.mark.asyncio
    async def test_empty_report(self):
        """Test report with no active users"""
        from utils.connection_analyzer import generate_connection_report
        
        report = await generate_connection_report({})
        
        assert "No active user connections" in report
    
    @pytest.mark.asyncio
    async def test_report_contains_user(self):
        """Test report contains user information"""
        from utils.connection_analyzer import generate_connection_report
        from utils.types import UserType, DeviceInfo, ConnectionInfo
        
        conn = ConnectionInfo("1.1.1.1", 1, "TestNode", "VLESS", 5)
        device = DeviceInfo(
            unique_ips={"1.1.1.1"},
            unique_nodes={1},
            inbound_protocols={"VLESS"},
            is_multi_device=False,
            connections=[conn]
        )
        
        user = UserType(name="test_user", ip=["1.1.1.1"])
        user.device_info = device
        
        report = await generate_connection_report({"test_user": user})
        
        assert "test_user" in report
        assert "1.1.1.1" in report


class TestNodeFiltering:
    """Tests for filtering users by node"""
    
    @pytest.mark.asyncio
    async def test_users_by_node(self):
        """Test filtering users by node ID"""
        from utils.connection_analyzer import get_users_by_node
        from utils.types import UserType, DeviceInfo, ConnectionInfo
        
        # Create user on node 1
        conn1 = ConnectionInfo("1.1.1.1", 1, "Node1", "VLESS", time.time(), 3)
        device1 = DeviceInfo(
            unique_ips={"1.1.1.1"},
            unique_nodes={1},
            inbound_protocols={"VLESS"},
            is_multi_device=False,
            connections=[conn1]
        )
        user1 = UserType(name="user1", ip=["1.1.1.1"])
        user1.device_info = device1
        
        # Create user on node 2
        conn2 = ConnectionInfo("2.2.2.2", 2, "Node2", "VMESS", time.time(), 2)
        device2 = DeviceInfo(
            unique_ips={"2.2.2.2"},
            unique_nodes={2},
            inbound_protocols={"VMESS"},
            is_multi_device=False,
            connections=[conn2]
        )
        user2 = UserType(name="user2", ip=["2.2.2.2"])
        user2.device_info = device2
        
        active_users = {"user1": user1, "user2": user2}
        
        # Get users on node 1
        result = await get_users_by_node(1, active_users)
        
        assert len(result) == 1
        assert result[0][0] == "user1"


class TestProtocolFiltering:
    """Tests for filtering users by protocol"""
    
    @pytest.mark.asyncio
    async def test_users_by_protocol(self):
        """Test filtering users by inbound protocol"""
        from utils.connection_analyzer import get_users_by_inbound_protocol
        from utils.types import UserType, DeviceInfo, ConnectionInfo
        
        # VLESS user
        conn1 = ConnectionInfo("1.1.1.1", 1, "Node1", "VLESS", time.time(), 3)
        device1 = DeviceInfo(
            unique_ips={"1.1.1.1"},
            unique_nodes={1},
            inbound_protocols={"VLESS"},
            is_multi_device=False,
            connections=[conn1]
        )
        user1 = UserType(name="vless_user", ip=["1.1.1.1"])
        user1.device_info = device1
        
        # VMESS user
        conn2 = ConnectionInfo("2.2.2.2", 2, "Node2", "VMESS", time.time(), 2)
        device2 = DeviceInfo(
            unique_ips={"2.2.2.2"},
            unique_nodes={2},
            inbound_protocols={"VMESS"},
            is_multi_device=False,
            connections=[conn2]
        )
        user2 = UserType(name="vmess_user", ip=["2.2.2.2"])
        user2.device_info = device2
        
        active_users = {"vless_user": user1, "vmess_user": user2}
        
        # Get VLESS users
        result = await get_users_by_inbound_protocol("VLESS", active_users)
        
        assert len(result) == 1
        assert result[0][0] == "vless_user"


class TestMultiDeviceUsers:
    """Tests for identifying multi-device users"""
    
    @pytest.mark.asyncio
    async def test_get_multi_device_users(self):
        """Test getting users with multiple devices"""
        from utils.connection_analyzer import get_multi_device_users
        from utils.types import UserType, DeviceInfo, ConnectionInfo
        
        # Multi-device user
        conns = [
            ConnectionInfo("1.1.1.1", 1, "Node1", "VLESS", time.time(), 3),
            ConnectionInfo("2.2.2.2", 1, "Node1", "VLESS", time.time(), 2)
        ]
        device1 = DeviceInfo(
            unique_ips={"1.1.1.1", "2.2.2.2"},
            unique_nodes={1},
            inbound_protocols={"VLESS"},
            is_multi_device=True,
            connections=conns
        )
        user1 = UserType(name="multi_user", ip=["1.1.1.1", "2.2.2.2"])
        user1.device_info = device1
        
        # Single device user
        conn2 = ConnectionInfo("3.3.3.3", 2, "Node2", "VMESS", time.time(), 5)
        device2 = DeviceInfo(
            unique_ips={"3.3.3.3"},
            unique_nodes={2},
            inbound_protocols={"VMESS"},
            is_multi_device=False,
            connections=[conn2]
        )
        user2 = UserType(name="single_user", ip=["3.3.3.3"])
        user2.device_info = device2
        
        active_users = {"multi_user": user1, "single_user": user2}
        
        result = await get_multi_device_users(active_users)
        
        # Should only return multi-device users
        usernames = [r[0] for r in result]
        assert "multi_user" in usernames
        assert "single_user" not in usernames
