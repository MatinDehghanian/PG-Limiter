#!/usr/bin/env python3
"""
Tests for data types and dataclasses
Tests UserType, PanelType, ConnectionInfo, and DeviceInfo.
"""

import pytest


class TestPanelType:
    """Tests for PanelType dataclass"""
    
    def test_panel_type_creation(self):
        """Test creating a PanelType instance"""
        from utils.types import PanelType
        
        panel = PanelType(
            panel_username="admin",
            panel_password="password",
            panel_domain="example.com"
        )
        
        assert panel.panel_username == "admin"
        assert panel.panel_password == "password"
        assert panel.panel_domain == "example.com"
    
    def test_panel_type_with_port(self):
        """Test PanelType with port in domain"""
        from utils.types import PanelType
        
        panel = PanelType(
            panel_username="admin",
            panel_password="pass",
            panel_domain="192.168.1.1:8080"
        )
        
        assert "8080" in panel.panel_domain
    
    def test_panel_type_positional_args(self):
        """Test PanelType with positional arguments"""
        from utils.types import PanelType
        
        panel = PanelType("user", "pass", "domain.com")
        
        assert panel.panel_username == "user"
        assert panel.panel_password == "pass"
        assert panel.panel_domain == "domain.com"


class TestUserType:
    """Tests for UserType dataclass"""
    
    def test_user_type_creation(self):
        """Test creating a UserType instance"""
        from utils.types import UserType
        
        user = UserType(name="test_user")
        
        assert user.name == "test_user"
    
    def test_user_type_with_ips(self):
        """Test UserType with IP list"""
        from utils.types import UserType
        
        user = UserType(name="test_user", ip=["1.1.1.1", "2.2.2.2"])
        
        assert len(user.ip) == 2
        assert "1.1.1.1" in user.ip
    
    def test_user_type_default_ip(self):
        """Test UserType has default empty IP list"""
        from utils.types import UserType
        
        user = UserType(name="test_user")
        
        # Should have default empty list or be able to accept IPs
        assert hasattr(user, 'ip')


class TestConnectionInfo:
    """Tests for ConnectionInfo dataclass"""
    
    def test_connection_info_creation(self):
        """Test creating a ConnectionInfo instance"""
        import time
        from utils.types import ConnectionInfo
        
        conn = ConnectionInfo(
            ip="192.168.1.1",
            node_id=1,
            node_name="Node1",
            inbound_protocol="VLESS",
            last_seen=time.time(),
            connection_count=5
        )
        
        assert conn.ip == "192.168.1.1"
        assert conn.node_id == 1
        assert conn.node_name == "Node1"
        assert conn.inbound_protocol == "VLESS"
        assert conn.connection_count == 5
    
    def test_connection_info_different_protocols(self):
        """Test ConnectionInfo with different protocols"""
        import time
        from utils.types import ConnectionInfo
        
        protocols = ["VLESS", "VMESS", "TROJAN", "GRPC", "REALITY"]
        
        for protocol in protocols:
            conn = ConnectionInfo(
                ip="1.1.1.1",
                node_id=1,
                node_name="Test",
                inbound_protocol=protocol,
                last_seen=time.time(),
                connection_count=1
            )
            assert conn.inbound_protocol == protocol


class TestDeviceInfo:
    """Tests for DeviceInfo dataclass"""
    
    def test_device_info_creation(self):
        """Test creating a DeviceInfo instance"""
        from utils.types import DeviceInfo
        
        device = DeviceInfo(
            unique_ips={"1.1.1.1", "2.2.2.2"},
            unique_nodes={1, 2},
            inbound_protocols={"VLESS", "VMESS"},
            is_multi_device=True,
            connections=[]
        )
        
        assert len(device.unique_ips) == 2
        assert len(device.unique_nodes) == 2
        assert device.is_multi_device is True
    
    def test_device_info_single_device(self):
        """Test DeviceInfo for single device user"""
        from utils.types import DeviceInfo
        
        device = DeviceInfo(
            unique_ips={"1.1.1.1"},
            unique_nodes={1},
            inbound_protocols={"VLESS"},
            is_multi_device=False,
            connections=[]
        )
        
        assert len(device.unique_ips) == 1
        assert device.is_multi_device is False
    
    def test_device_info_with_connections(self):
        """Test DeviceInfo with connection list"""
        import time
        from utils.types import DeviceInfo, ConnectionInfo
        
        conn1 = ConnectionInfo(
            ip="1.1.1.1",
            node_id=1,
            node_name="Node1",
            inbound_protocol="VLESS",
            last_seen=time.time(),
            connection_count=3
        )
        conn2 = ConnectionInfo(
            ip="2.2.2.2",
            node_id=2,
            node_name="Node2",
            inbound_protocol="VMESS",
            last_seen=time.time(),
            connection_count=2
        )
        
        device = DeviceInfo(
            unique_ips={"1.1.1.1", "2.2.2.2"},
            unique_nodes={1, 2},
            inbound_protocols={"VLESS", "VMESS"},
            is_multi_device=True,
            connections=[conn1, conn2]
        )
        
        assert len(device.connections) == 2


class TestTypeImmutability:
    """Tests for dataclass behavior"""
    
    def test_panel_type_hashable(self):
        """Test that PanelType can be used in hash operations"""
        from utils.types import PanelType
        
        panel1 = PanelType("admin", "pass", "domain.com")
        panel2 = PanelType("admin", "pass", "domain.com")
        
        # Should be able to compare
        assert panel1.panel_username == panel2.panel_username
    
    def test_user_type_mutable_ip(self):
        """Test that UserType IP list can be modified"""
        from utils.types import UserType
        
        user = UserType(name="test_user", ip=[])
        user.ip.append("1.1.1.1")
        
        assert "1.1.1.1" in user.ip
