"""
Connection analyzer utility for tracking IP-Node-Inbound relationships.
"""

from typing import Dict, List, Tuple
from utils.types import UserType, ConnectionInfo


async def generate_connection_report(active_users: Dict[str, UserType] = None) -> str:
    """
    Generate a comprehensive report of IP-Node-Inbound connections.
    
    Args:
        active_users: Dictionary of active users, if None will import from check_usage
    
    Returns:
        str: Formatted report string
    """
    if active_users is None:
        from utils.check_usage import ACTIVE_USERS
        active_users = ACTIVE_USERS
    
    if not active_users:
        return "No active user connections found."
    
    report_lines = []
    report_lines.append("=== CONNECTION ANALYSIS REPORT ===\n")
    
    for username, user in active_users.items():
        report_lines.append(f"User: {username}")
        report_lines.append(f"Total IPs: {len(user.device_info.unique_ips)}")
        report_lines.append(f"Total Nodes: {len(user.device_info.unique_nodes)}")
        report_lines.append(f"Inbound Protocols: {', '.join(user.device_info.inbound_protocols)}")
        report_lines.append(f"Multi-device: {'Yes' if user.device_info.is_multi_device else 'No'}")
        report_lines.append("")
        
        if user.device_info.connections:
            report_lines.append("  Connections:")
            for conn in user.device_info.connections:
                report_lines.append(
                    f"    IP: {conn.ip} | Node: {conn.node_name} (ID: {conn.node_id}) | "
                    f"Protocol: {conn.inbound_protocol} | Count: {conn.connection_count}"
                )
        
        report_lines.append("-" * 60)
    
    return "\n".join(report_lines)


async def get_users_by_node(node_id: int, active_users: Dict[str, UserType] = None) -> List[Tuple[str, str, str]]:
    """
    Get all users connected to a specific node.
    
    Args:
        node_id (int): The node ID to filter by
        active_users: Dictionary of active users, if None will import from check_usage
        
    Returns:
        List[Tuple[str, str, str]]: List of (username, ip, inbound_protocol) tuples
    """
    if active_users is None:
        from utils.check_usage import ACTIVE_USERS
        active_users = ACTIVE_USERS
    
    users_on_node = []
    
    for username, user in active_users.items():
        for conn in user.device_info.connections:
            if conn.node_id == node_id:
                users_on_node.append((username, conn.ip, conn.inbound_protocol))
    
    return users_on_node


async def get_users_by_inbound_protocol(protocol: str, active_users: Dict[str, UserType] = None) -> List[Tuple[str, str, str]]:
    """
    Get all users using a specific inbound protocol.
    
    Args:
        protocol (str): The inbound protocol to filter by
        active_users: Dictionary of active users, if None will import from check_usage
        
    Returns:
        List[Tuple[str, str, str]]: List of (username, ip, node_name) tuples
    """
    if active_users is None:
        from utils.check_usage import ACTIVE_USERS
        active_users = ACTIVE_USERS
    
    users_with_protocol = []
    
    for username, user in active_users.items():
        for conn in user.device_info.connections:
            if conn.inbound_protocol == protocol:
                users_with_protocol.append((username, conn.ip, conn.node_name))
    
    return users_with_protocol


async def get_multi_device_users(active_users: Dict[str, UserType] = None) -> List[Tuple[str, int, int, List[str]]]:
    """
    Get all users identified as using multiple devices.
    
    Args:
        active_users: Dictionary of active users, if None will import from check_usage
    
    Returns:
        List[Tuple[str, int, int, List[str]]]: List of (username, ip_count, node_count, protocols) tuples
    """
    if active_users is None:
        from utils.check_usage import ACTIVE_USERS
        active_users = ACTIVE_USERS
    
    multi_device_users = []
    
    for username, user in active_users.items():
        if user.device_info.is_multi_device:
            multi_device_users.append((
                username,
                len(user.device_info.unique_ips),
                len(user.device_info.unique_nodes),
                list(user.device_info.inbound_protocols)
            ))
    
    return multi_device_users


async def get_node_usage_summary(active_users: Dict[str, UserType] = None) -> Dict[str, Dict[str, int]]:
    """
    Get a summary of node usage statistics.
    
    Args:
        active_users: Dictionary of active users, if None will import from check_usage
    
    Returns:
        Dict[str, Dict[str, int]]: Dictionary with node usage statistics
    """
    if active_users is None:
        from utils.check_usage import ACTIVE_USERS
        active_users = ACTIVE_USERS
    
    node_stats = {}
    
    for username, user in active_users.items():
        for conn in user.device_info.connections:
            node_key = f"{conn.node_name} (ID: {conn.node_id})"
            
            if node_key not in node_stats:
                node_stats[node_key] = {
                    "unique_users": set(),
                    "unique_ips": set(),
                    "protocols": set(),
                    "total_connections": 0
                }
            
            node_stats[node_key]["unique_users"].add(username)
            node_stats[node_key]["unique_ips"].add(conn.ip)
            node_stats[node_key]["protocols"].add(conn.inbound_protocol)
            node_stats[node_key]["total_connections"] += conn.connection_count
    
    # Convert sets to counts
    for node_key in node_stats:
        node_stats[node_key]["unique_users"] = len(node_stats[node_key]["unique_users"])
        node_stats[node_key]["unique_ips"] = len(node_stats[node_key]["unique_ips"])
        node_stats[node_key]["protocols"] = len(node_stats[node_key]["protocols"])
    
    return node_stats


async def generate_node_usage_report(active_users: Dict[str, UserType] = None) -> str:
    """
    Generate a report of node usage statistics.
    
    Args:
        active_users: Dictionary of active users, if None will import from check_usage
    
    Returns:
        str: Formatted node usage report
    """
    node_stats = await get_node_usage_summary(active_users)
    
    if not node_stats:
        return "No node usage data available."
    
    report_lines = []
    report_lines.append("=== NODE USAGE REPORT ===\n")
    
    for node_key, stats in node_stats.items():
        report_lines.append(f"Node: {node_key}")
        report_lines.append(f"  Unique Users: {stats['unique_users']}")
        report_lines.append(f"  Unique IPs: {stats['unique_ips']}")
        report_lines.append(f"  Protocol Types: {stats['protocols']}")
        report_lines.append(f"  Total Connections: {stats['total_connections']}")
        report_lines.append("")
    
    return "\n".join(report_lines)
