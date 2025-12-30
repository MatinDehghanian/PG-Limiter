"""
Limiter - IP connection limiter for PasarGuard panel.
Monitors active connections and limits users based on their IP count.
"""

import argparse
import asyncio
import time

from run_telegram import run_telegram_bot
from telegram_bot.send_message import send_logs
from utils.check_usage import run_check_users_usage
from utils.get_logs import (
    TASKS,
    check_and_add_new_nodes,
    create_node_task,
    handle_cancel,
    handle_cancel_all,
    init_node_status_message,
)
from utils.handel_dis_users import DisabledUsers
from utils.logs import logger
from utils.panel_api import (
    enable_dis_user,
    enable_selected_users,
    get_nodes,
)
from utils.read_config import read_config
from utils.types import PanelType

VERSION = "0.4.2"

parser = argparse.ArgumentParser(
    description="Limiter - IP connection limiter for PasarGuard panel"
)
parser.add_argument("--version", action="version", version=f"Limiter v{VERSION}")
args = parser.parse_args()

dis_obj = DisabledUsers()


async def main():
    """Main function to run the limiter."""
    logger.info("Starting Limiter v%s", VERSION)
    asyncio.create_task(run_telegram_bot())
    await asyncio.sleep(2)
    
    while True:
        try:
            config_file = await read_config(check_required_elements=True)
            break
        except ValueError as error:
            logger.error("Configuration error: %s", error)
            await send_logs(f"<code>{error}</code>")
            await send_logs(
                "Please configure the required settings:\n"
                "/create_config - Panel credentials\n"
                "/set_general_limit_number - Default IP limit\n"
                "/set_check_interval - Check interval\n"
                "/set_time_to_active_users - Re-enable timeout\n\n"
                "Retrying in <b>60 seconds</b>..."
            )
            await asyncio.sleep(60)
    
    panel_data = PanelType(
        config_file["panel"]["username"],
        config_file["panel"]["password"],
        config_file["panel"]["domain"],
    )
    
    # Re-enable previously disabled users
    dis_users = await dis_obj.read_and_clear_users()
    await enable_selected_users(panel_data, dis_users)
    
    # Get available nodes
    await get_nodes(panel_data)
    
    async with asyncio.TaskGroup() as tg:
        await asyncio.sleep(5)
        nodes_list = await get_nodes(panel_data)
        
        if nodes_list and not isinstance(nodes_list, ValueError):
            await init_node_status_message(nodes_list)
            
            logger.info("Connecting to %d nodes", len(nodes_list))
            for node in nodes_list:
                if node.status == "connected":
                    await create_node_task(panel_data, tg, node)
                    await asyncio.sleep(1)
        
        # Start background tasks
        tg.create_task(check_and_add_new_nodes(panel_data, tg), name="add_new_nodes")
        tg.create_task(handle_cancel(panel_data, TASKS), name="cancel_disable_nodes")
        tg.create_task(handle_cancel_all(TASKS, panel_data, tg), name="cancel_all")
        tg.create_task(enable_dis_user(panel_data), name="enable_dis_user")
        
        await run_check_users_usage(panel_data)


if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except Exception as er:  # pylint: disable=broad-except
            logger.error(er)
            time.sleep(10)
