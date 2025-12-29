"""
This module contains functions to get logs from the nodes using SSE (Server-Sent Events).
"""

import asyncio
import sys
from asyncio import Task
from datetime import datetime

from utils.parse_logs import INVALID_IPS

try:
    import httpx
except ImportError:
    print(
        "Module 'httpx' is not installed use: 'pip install httpx' to install it"
    )
    sys.exit()
from telegram_bot.send_message import send_logs, edit_message
from utils.logs import logger  # pylint: disable=ungrouped-imports
from utils.panel_api import get_nodes, get_token
from utils.parse_logs import parse_logs, set_current_node_info
from utils.types import NodeType, PanelType

TASKS = []

task_node_mapping = {}

# Track the status message for node connections
_node_status_message_id = None
_node_connection_status = {}  # node_id -> {"name": str, "status": str}


async def _build_node_status_message() -> str:
    """Build a formatted message showing all node connection statuses."""
    global _node_connection_status
    
    if not _node_connection_status:
        return "🔄 <b>SSE Node Connections</b>\n\nNo nodes to connect."
    
    time_str = datetime.now().strftime("%H:%M:%S")
    lines = [f"🔄 <b>SSE Node Connections</b> - {time_str}\n"]
    
    for node_id in sorted(_node_connection_status.keys()):
        info = _node_connection_status[node_id]
        lines.append(f"  {info['status']} Node {node_id}: <code>{info['name']}</code>")
    
    # Count statuses
    connected = sum(1 for info in _node_connection_status.values() if "✅" in info['status'])
    connecting = sum(1 for info in _node_connection_status.values() if "⏳" in info['status'])
    failed = sum(1 for info in _node_connection_status.values() if "❌" in info['status'])
    
    lines.append(f"\n📊 Connected: {connected} | Connecting: {connecting} | Failed: {failed}")
    
    return "\n".join(lines)


async def _update_node_status(node_id: int, node_name: str, status: str) -> None:
    """Update the status of a node and refresh the message."""
    global _node_connection_status, _node_status_message_id
    
    _node_connection_status[node_id] = {"name": node_name, "status": status}
    
    message = await _build_node_status_message()
    
    if _node_status_message_id:
        # Try to edit the existing message
        result = await edit_message(_node_status_message_id, message)
        if not result:
            # If edit fails, send a new message
            _node_status_message_id = await send_logs(message, return_message_id=True)
    else:
        # Send initial message
        _node_status_message_id = await send_logs(message, return_message_id=True)


async def init_node_status_message(nodes: list) -> None:
    """Initialize the status message with all nodes showing as connecting."""
    global _node_connection_status, _node_status_message_id
    
    _node_connection_status = {}
    _node_status_message_id = None
    
    for node in nodes:
        if node.status == "connected":
            _node_connection_status[node.node_id] = {
                "name": node.node_name,
                "status": "⏳ Connecting..."
            }
    
    if _node_connection_status:
        message = await _build_node_status_message()
        _node_status_message_id = await send_logs(message, return_message_id=True)


async def get_nodes_logs(panel_data: PanelType, node: NodeType) -> None:
    """
    This function establishes an SSE connection to a specific node and retrieves logs.

    Args:
        panel_data (PanelType): The credentials for the panel.
        node (NodeType): The specific node to connect to.

    Raises:
        ValueError: If there is an issue with getting the panel token.
    """
    global _node_connection_status
    
    # Set current node information for log parsing
    await set_current_node_info(node.node_id, node.node_name)
    
    while True:
        get_panel_token = await get_token(panel_data)
        if isinstance(get_panel_token, ValueError):
            raise get_panel_token
        token = get_panel_token.panel_token
        
        # Determine the scheme based on the domain
        scheme = "https" if panel_data.panel_domain.startswith("https://") else "https"
        base_url = panel_data.panel_domain.replace("https://", "").replace("http://", "")
        
        try:
            url = f"{scheme}://{base_url}/api/node/{node.node_id}/logs"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache",
            }
            
            async with httpx.AsyncClient(verify=False, timeout=None) as client:
                logger.info(f"Establishing SSE connection for node {node.node_id}: {node.node_name}")
                
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code != 200:
                        raise httpx.HTTPStatusError(
                            f"HTTP {response.status_code}", 
                            request=response.request, 
                            response=response
                        )
                    
                    # Update status to connected
                    await _update_node_status(node.node_id, node.node_name, "✅ Connected")
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            log_data = line[6:]  # Remove "data: " prefix
                            if log_data.strip():  # Only process non-empty log data
                                await parse_logs(log_data, node.node_id, node.node_name)
                                
        except httpx.HTTPStatusError as error:
            await _update_node_status(node.node_id, node.node_name, "❌ HTTP Error")
            logger.error(f"HTTP error connecting to node {node.node_id}: {error}")
            await asyncio.sleep(10)
            await _update_node_status(node.node_id, node.node_name, "⏳ Reconnecting...")
            continue
            
        except Exception as error:  # pylint: disable=broad-except
            await _update_node_status(node.node_id, node.node_name, "❌ Failed")
            logger.error(f"Failed to connect to node {node.node_id}: {error}")
            await asyncio.sleep(10)
            await _update_node_status(node.node_id, node.node_name, "⏳ Reconnecting...")
            continue


async def handle_cancel(panel_data: PanelType, tasks: list[Task]) -> None:
    """
    An asynchronous coroutine that cancels tasks for disconnected nodes.

    Args:
        panel_data (PanelType): The credentials for the panel.
        tasks (list[Task]): The list of tasks to be cancelled.
    """
    global _node_connection_status
    
    deactivate_nodes = {}  # task_name -> node_id
    while True:
        nodes_list = await get_nodes(panel_data)
        for node in nodes_list:
            if node.status != "connected":
                task_name = f"Task-{node.node_id}-{node.node_name}"
                deactivate_nodes[task_name] = node.node_id

        for task in list(tasks):
            task_name = task.get_name()
            if task_name in deactivate_nodes:
                node_id = deactivate_nodes[task_name]
                logger.info(f"Cancelling disconnected node task: {task_name}")
                
                # Update status to show disconnected
                if node_id in _node_connection_status:
                    await _update_node_status(node_id, _node_connection_status[node_id]["name"], "⚫ Disconnected")
                
                del deactivate_nodes[task_name]
                task.cancel()
                tasks.remove(task)
                if task in task_node_mapping:
                    task_node_mapping.pop(task)
        # Check for disconnected nodes every minute
        await asyncio.sleep(60)


async def handle_cancel_one(tasks: list[Task]) -> None:
    """
    *This is used for tests*
    An asynchronous coroutine that cancels just one task in the given list.

    Args:
        tasks (list[Task]): The list of tasks to be cancelled.
    """
    # Since panel no longer provides logs, we cancel the first available task
    if tasks:
        task = tasks[0]
        print(f"Cancelling {task.get_name()}...")
        task.cancel()
        tasks.remove(task)


async def handle_cancel_all(tasks: list[Task], panel_data: PanelType, tg: asyncio.TaskGroup) -> None:
    """
    An asynchronous coroutine that periodically restarts all SSE connections every 2 hours.
    This ensures fresh connections and re-fetches the node list.

    Args:
        tasks (list[Task]): The list of tasks to be cancelled and restarted.
        panel_data (PanelType): The credentials for the panel.
        tg (asyncio.TaskGroup): The TaskGroup to create new tasks in.
    """
    global _node_status_message_id, _node_connection_status
    
    while True:
        # Wait for 2 hours before restarting all SSE connections
        await asyncio.sleep(2 * 60 * 60)  # 2 hours
        
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[{time_str}] Restarting all SSE connections (2-hour refresh)")
        await send_logs(f"🔄 <b>SSE Refresh</b> - {time_str}\n\nRestarting all node connections...")
        
        # Cancel all existing node tasks
        for task in list(tasks):
            if task.get_name().startswith("Task-"):
                task.cancel()
                tasks.remove(task)
                if task in task_node_mapping:
                    task_node_mapping.pop(task)
        
        # Reset status tracking
        _node_status_message_id = None
        _node_connection_status = {}
        
        # Small delay to let tasks clean up
        await asyncio.sleep(2)
        
        # Fetch fresh node list
        nodes_list = await get_nodes(panel_data)
        if nodes_list and not isinstance(nodes_list, ValueError):
            # Initialize status message for all nodes
            await init_node_status_message(nodes_list)
            
            # Create new tasks for all connected nodes
            for node in nodes_list:
                if node.status == "connected":
                    await create_node_task(panel_data, tg, node)
                    await asyncio.sleep(1)  # Small delay between node connections
        
        logger.info(f"SSE connections restarted. Active tasks: {len(tasks)}")


async def check_and_add_new_nodes(panel_data: PanelType, tg: asyncio.TaskGroup) -> None:
    """
    An asynchronous coroutine that checks for new nodes and creates tasks for them.

    Args:
        panel_data (PanelType): The credentials for the panel.
        tg (asyncio.TaskGroup): The TaskGroup to which the new task will be added.
    """
    global _node_connection_status
    
    while True:
        all_nodes = await get_nodes(panel_data)
        if all_nodes and not isinstance(all_nodes, ValueError):
            for node in all_nodes:
                if (
                    node not in task_node_mapping.values()
                    and node.status == "connected"
                ):
                    # Add to status tracking
                    _node_connection_status[node.node_id] = {
                        "name": node.node_name,
                        "status": "⏳ Connecting..."
                    }
                    
                    logger.info(f"Add a new node. id: {node.node_id} name: {node.node_name}")
                    await _update_node_status(node.node_id, node.node_name, "⏳ Connecting...")
                    await create_node_task(panel_data, tg, node)
        # Check for new nodes every 2 minutes instead of 25 seconds to reduce API calls
        await asyncio.sleep(120)


async def create_node_task(
    panel_data: PanelType, tg: asyncio.TaskGroup, node: NodeType
) -> None:
    """
    An asynchronous coroutine that creates a new task for a node and adds it to the TASKS list.

    Args:
        panel_data (PanelType): The credentials for the panel.
        tg (asyncio.TaskGroup): The TaskGroup to which the new task will be added.
        node (NodeType): The node for which the new task will be created.
    """
    INVALID_IPS.add(node.node_ip)
    task = tg.create_task(
        get_nodes_logs(panel_data, node), name=f"Task-{node.node_id}-{node.node_name}"
    )
    TASKS.append(task)
    task_node_mapping[task] = node
