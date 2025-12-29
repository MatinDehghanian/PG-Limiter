"""
Telegram bot runner module.
This module provides the function to run the Telegram bot in the background.
"""

import os
import json
from telegram.ext import ApplicationBuilder


async def run_telegram_bot():
    """
    Run the Telegram bot in polling mode.
    This function starts the bot and keeps it running to receive updates.
    """
    # Import telegram bot main module first
    from telegram_bot import main as bot_main
    
    # Debug: Print token state
    print(f"DEBUG: bot_token type = {type(bot_main.bot_token)}")
    print(f"DEBUG: bot_token value = {repr(bot_main.bot_token[:20] if bot_main.bot_token else bot_main.bot_token)}")
    print(f"DEBUG: bot_token truthy = {bool(bot_main.bot_token)}")
    print(f"DEBUG: is not dummy = {bot_main.bot_token != '0000000000:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX' if bot_main.bot_token else 'N/A'}")
    
    # Check if application was already created with valid token at module import
    if bot_main.bot_token and bot_main.bot_token != "0000000000:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX":
        # Token was loaded successfully at import time
        application = bot_main.application
        print(f"✓ Bot token loaded successfully: {bot_main.bot_token[:10]}...")
    else:
        # This shouldn't happen if config file exists, but handle it anyway
        print("✗ Bot token not found in config/config.json")
        print("Please set BOT_TOKEN in your config file")
        return
    
    # Initialize the application
    try:
        # Check if already running
        if application.running:
            print("✓ Telegram bot is already running!")
            return
        
        await application.initialize()
        await application.start()
        
        # Start polling for updates
        await application.updater.start_polling(
            allowed_updates=["message", "callback_query"]
        )
        
        print("✓ Telegram bot started successfully!")
        print(f"✓ Bot is now polling for updates...")
    except RuntimeError as e:
        if "already running" in str(e).lower():
            print("✓ Telegram bot is already running!")
        else:
            print(f"✗ Failed to start Telegram bot: {e}")
            import traceback
            traceback.print_exc()
    except Exception as e:
        print(f"✗ Failed to start Telegram bot: {e}")
        print(f"✗ Please verify your BOT_TOKEN is correct")
        import traceback
        traceback.print_exc()
