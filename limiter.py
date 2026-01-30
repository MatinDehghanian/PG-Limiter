"""
Limiter - IP connection limiter for PasarGuard panel.
Monitors active connections and limits users based on their IP count.
"""

import argparse
import asyncio
import sys
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
from utils.logs import get_logger, log_startup_info, log_shutdown_info, log_crash_info
from utils.panel_api import enable_selected_users, get_nodes
from utils.read_config import read_config
from utils.types import PanelType

# Import Redis cache utilities
try:
    from utils.redis_cache import get_cache, close_cache
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

VERSION = "0.8.6"

# Main logger
main_logger = get_logger("limiter.main")

parser = argparse.ArgumentParser(
    description="Limiter - IP connection limiter for PasarGuard panel"
)
parser.add_argument("--version", action="version", version=f"Limiter v{VERSION}")
args = parser.parse_args()

dis_obj = DisabledUsers()


async def main():
    """Main function to run the limiter."""
    log_startup_info("Limiter", f"v{VERSION}")
    main_logger.info(f"🚀 Starting Limiter v{VERSION}")
    main_logger.info("=" * 50)
    
    # Initialize Redis cache
    if REDIS_AVAILABLE:
        try:
            cache = await get_cache()
            if cache.is_connected:
                main_logger.info("✓ Redis cache connected")
            else:
                main_logger.info("⚠ Redis not available, using in-memory cache fallback")
        except Exception as e:
            main_logger.warning(f"Redis initialization failed: {e}, using in-memory fallback")
    else:
        main_logger.info("ℹ Redis cache module not available, using in-memory cache")
    
    # Start Telegram bot
    main_logger.debug("Starting Telegram bot task...")
    asyncio.create_task(run_telegram_bot())
    await asyncio.sleep(2)
    main_logger.info("✓ Telegram bot started")
    
    # Load configuration
    main_logger.debug("Loading configuration...")
    while True:
        try:
            config_file = await read_config(check_required_elements=True)
            main_logger.info("✓ Configuration loaded successfully")
            break
        except ValueError as error:
            main_logger.error(f"Configuration error: {error}")
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
    
    # Initialize panel connection
    panel_data = PanelType(
        config_file["panel"]["username"],
        config_file["panel"]["password"],
        config_file["panel"]["domain"],
    )
    main_logger.info(f"✓ Panel configured: {config_file['panel']['domain']}")
    
    # Re-enable previously disabled users
    main_logger.debug("Checking for previously disabled users...")
    dis_users = await dis_obj.read_and_clear_users()
    if dis_users:
        main_logger.info(f"📋 Re-enabling {len(dis_users)} previously disabled users...")
        result = await enable_selected_users(panel_data, dis_users)
        enabled = result.get("enabled", [])
        failed = result.get("failed", [])
        not_found = result.get("not_found", [])
        if enabled:
            main_logger.info(f"✓ Re-enabled {len(enabled)} previously disabled users")
        if not_found:
            main_logger.info(f"🗑️ {len(not_found)} users were deleted from panel")
        if failed:
            main_logger.warning(f"⚠️ Failed to re-enable {len(failed)} users: {failed}")
    else:
        main_logger.debug("No previously disabled users to re-enable")
    
    # Get available nodes
    main_logger.debug("Fetching available nodes...")
    await get_nodes(panel_data)
    
    async with asyncio.TaskGroup() as tg:
        await asyncio.sleep(5)
        nodes_list = await get_nodes(panel_data)
        
        if nodes_list and not isinstance(nodes_list, ValueError):
            await init_node_status_message(nodes_list)
            
            connected_nodes = [n for n in nodes_list if n.status == "connected"]
            main_logger.info(f"🖥️ Found {len(nodes_list)} nodes ({len(connected_nodes)} connected)")
            
            for node in nodes_list:
                if node.status == "connected":
                    main_logger.debug(f"Connecting to node: {node.node_name} (id={node.node_id})")
                    await create_node_task(panel_data, tg, node)
                    await asyncio.sleep(1)
            
            main_logger.info(f"✓ Connected to {len(connected_nodes)} nodes")
        else:
            main_logger.warning("No nodes available or error fetching nodes")
        
        # Start background tasks
        main_logger.info("🔄 Starting background tasks...")
        tg.create_task(check_and_add_new_nodes(panel_data, tg), name="add_new_nodes")
        main_logger.debug("  └─ Started: check_and_add_new_nodes")
        tg.create_task(handle_cancel(panel_data, TASKS), name="cancel_disable_nodes")
        main_logger.debug("  └─ Started: handle_cancel")
        tg.create_task(handle_cancel_all(TASKS, panel_data, tg), name="cancel_all")
        main_logger.debug("  └─ Started: handle_cancel_all")
        
        # Enable disabled user task is now part of check_usage.py punishment system
        # Start the enable_dis_user loop to auto-enable users after punishment time passes
        from utils.panel_api import enable_dis_user
        tg.create_task(enable_dis_user(panel_data), name="enable_disabled_users")
        main_logger.debug("  └─ Started: enable_disabled_users")
        
        # Start user sync loop for filter caching
        from utils.user_sync import run_user_sync_loop
        tg.create_task(run_user_sync_loop(panel_data), name="user_sync")
        main_logger.debug("  └─ Started: user_sync")
        
        main_logger.info("✓ All background tasks started")
        
        main_logger.info("=" * 50)
        main_logger.info("🟢 Limiter is now running and monitoring connections")
        main_logger.info("=" * 50)
        
        await run_check_users_usage(panel_data)


if __name__ == "__main__":
    restart_count = 0
    max_restarts = 5
    
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            main_logger.info("🛑 Received keyboard interrupt, shutting down...")
            # Close Redis connection
            if REDIS_AVAILABLE:
                try:
                    asyncio.run(close_cache())
                    main_logger.info("✓ Redis cache closed")
                except Exception:
                    pass
            log_shutdown_info("Limiter", "Keyboard interrupt")
            break
        except SystemExit as e:
            if e.code != 0 and e.code is not None:
                main_logger.error(f"System exit with code: {e.code}")
            break
        except Exception as er:  # pylint: disable=broad-except
            restart_count += 1
            exc_type, exc_value, exc_tb = sys.exc_info()
            
            # Use centralized crash logging
            log_crash_info(exc_type, exc_value, exc_tb, component="Limiter")
            log_shutdown_info("Limiter", f"Error: {er}")
            
            if restart_count >= max_restarts:
                main_logger.error(f"Maximum restart attempts ({max_restarts}) reached")
                main_logger.error("Please check the logs and fix the issue")
                break
            
            # Exponential backoff for restarts
            delay = min(10 * (2 ** (restart_count - 1)), 120)
            main_logger.info(f"⏳ Restart #{restart_count}/{max_restarts} in {delay} seconds...")
            time.sleep(delay)
