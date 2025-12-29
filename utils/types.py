"""
This module contains the data classes used in the application.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


@dataclass
class PanelType:
    """
    A class used to represent the credentials for a panel.

    Attributes:
        panel_username (str): The username for the panel.
        panel_password (str): The password for the panel.
        panel_domain (str): The domain for the panel.
        panel_token (Optional[str]): The token for the panel. None if no token is provided.
    """

    panel_username: str
    panel_password: str
    panel_domain: str
    panel_token: str | None = None


@dataclass
class NodeType:
    """
    A class used to represent the data for a node.

    Attributes:
        node_id (int): The ID of the node.
        node_name (str): The name of the node.
        node_ip (str): The IP address of the node.
        status (str): The status of the node.
        message (str): The message of the node.
    """

    node_id: int
    node_name: str
    node_ip: str
    status: str
    message: str | None = None


class UserStatus(Enum):
    """
    Enum representing the type of UserStatus.

    Attributes:
        ACTIVE (str)
        DISABLE (str)
    """

    ACTIVE = "ACTIVE"
    DISABLE = "DISABLE"


@dataclass
class ConnectionInfo:
    """
    Represents connection information for a specific IP address.
    
    Attributes:
        ip (str): The IP address
        node_id (int): The node ID where this IP was seen
        node_name (str): The node name where this IP was seen
        inbound_protocol (str): The inbound protocol used (e.g., "Vless Direct", "Vmess", etc.)
        last_seen (float): Timestamp of last activity
        connection_count (int): Number of connections seen
    """
    ip: str
    node_id: int
    node_name: str
    inbound_protocol: str
    last_seen: float
    connection_count: int = 1


@dataclass
class DeviceInfo:
    """
    Represents device information based on IP and connection patterns.
    
    Attributes:
        connections (List[ConnectionInfo]): List of connection information
        is_multi_device (bool): Whether this user appears to use multiple devices
        unique_ips (set): Set of unique IP addresses
        unique_nodes (set): Set of unique node IDs
        inbound_protocols (set): Set of inbound protocols used
    """
    connections: List[ConnectionInfo] = field(default_factory=list)
    is_multi_device: bool = False
    unique_ips: set = field(default_factory=set)
    unique_nodes: set = field(default_factory=set)
    inbound_protocols: set = field(default_factory=set)


@dataclass
class UserType:
    """
    Represents a user type.

    Attributes:
        name (str): The name of the user.
        status (str | None): The status of the user. None if no status is provided.
        ip (list[str] | list): List of IP address of the user.
        isp_info (dict | None): ISP information for the user's IPs.
        device_info (DeviceInfo): Device and connection information for the user.
    """

    name: str
    status: UserStatus | None = None
    ip: list[str] | list = field(default_factory=list)
    isp_info: dict | None = None
    device_info: DeviceInfo = field(default_factory=DeviceInfo)


@dataclass
class EnhancedUserInfo:
    """
    Enhanced user information with ISP details and warning status.

    Attributes:
        user (UserType): Basic user information
        formatted_ips (list[str]): List of IPs formatted with ISP info
        is_being_monitored (bool): Whether user is currently being monitored
        warning_time_remaining (int): Remaining monitoring time in seconds
    """

    user: UserType
    formatted_ips: list[str] = field(default_factory=list)
    is_being_monitored: bool = False
    warning_time_remaining: int = 0
