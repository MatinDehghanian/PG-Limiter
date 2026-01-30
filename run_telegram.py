"""
Telegram bot runner module.
This module provides the function to run the Telegram bot in the background.
"""

import os
import json
from telegram.ext import ApplicationBuilder
from utils.logs import get_logger

# Module logger
telegram_runner_logger = get_logger("telegram.runner")


async def run_telegram_bot():
    """
    Run the Telegram bot in polling mode.
    This function starts the bot and keeps it running to receive updates.
    """
    # Import telegram bot main module first
    from telegram_bot import main as bot_main
    
    telegram_runner_logger.info("🤖 Initializing Telegram bot...")
    
    # Debug: Print token state
    telegram_runner_logger.debug(f"Bot token type: {type(bot_main.bot_token)}")
    telegram_runner_logger.debug(f"Bot token value: {repr(bot_main.bot_token[:20] if bot_main.bot_token else 'None')}")
    telegram_runner_logger.debug(f"Bot token truthy: {bool(bot_main.bot_token)}")
    
    # Check if application was already created with valid token at module import
    if bot_main.bot_token and bot_main.bot_token != "0000000000:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX":
        # Token was loaded successfully at import time
        application = bot_main.application
        telegram_runner_logger.info(f"✓ Bot token loaded: {bot_main.bot_token[:15]}...")
    else:
        # This shouldn't happen if config file exists, but handle it anyway
        telegram_runner_logger.error("✗ Bot token not found!")
        telegram_runner_logger.error("Please set BOT_TOKEN in your environment or config")
        return
    
    # Initialize the application
    try:
        # Check if already running
        if application.running:
            telegram_runner_logger.info("✓ Telegram bot is already running!")
            return
        
        telegram_runner_logger.debug("Initializing application...")
        await application.initialize()
        
        telegram_runner_logger.debug("Starting application...")
        await application.start()
        
        # Start polling for updates
        telegram_runner_logger.info("🔄 Starting polling for updates...")
        await application.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,  # Ignore old updates
        )
        
        telegram_runner_logger.info("✓ Telegram bot started successfully!")
        telegram_runner_logger.info("✓ Bot is now polling for updates")
        
        # Get bot info to confirm connection
        try:
            bot_info = await application.bot.get_me()
            telegram_runner_logger.info(f"✓ Connected as @{bot_info.username} (ID: {bot_info.id})")
        except Exception as e:
            telegram_runner_logger.warning(f"Could not get bot info: {e}")
        
        # Schedule automatic backup based on config
        try:
            from telegram_bot.handlers.backup import (
                send_automatic_backup,
                get_auto_backup_config,
            )
            
            job_queue = application.job_queue
            if job_queue:
                config = get_auto_backup_config()
                if config.get("enabled", True):
                    interval_hours = config.get("interval_hours", 1)
                    interval_seconds = interval_hours * 3600
                    
                    job_queue.run_repeating(
                        lambda context: send_automatic_backup(),
                        interval=interval_seconds,
                        first=interval_seconds,
                        name="automatic_backup"
                    )
                    telegram_runner_logger.info(f"✓ Automatic backup scheduled (every {interval_hours} hour(s))")
                else:
                    telegram_runner_logger.info("✓ Automatic backup is disabled")
            else:
                telegram_runner_logger.warning("⚠️ Job queue not available, automatic backup disabled")
        except Exception as e:
            telegram_runner_logger.warning(f"⚠️ Could not schedule automatic backup: {e}")
            
    except RuntimeError as e:
        if "already running" in str(e).lower():
            telegram_runner_logger.info("✓ Telegram bot is already running!")
        else:
            telegram_runner_logger.error(f"✗ Failed to start Telegram bot: {e}")
            import traceback
            telegram_runner_logger.debug(f"Traceback:\n{traceback.format_exc()}")
    except Exception as e:
        telegram_runner_logger.error(f"✗ Failed to start Telegram bot: {e}")
        telegram_runner_logger.error("Please verify your BOT_TOKEN is correct")
        import traceback
        telegram_runner_logger.debug(f"Traceback:\n{traceback.format_exc()}")
