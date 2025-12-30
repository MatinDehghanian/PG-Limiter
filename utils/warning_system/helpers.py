"""
Helper functions for warning system.
Provides safe wrappers for external calls.
"""

from utils.logs import logger
from utils.types import PanelType, UserType


async def safe_send_logs(message: str):
    """Safely send logs, handling import errors gracefully"""
    try:
        from telegram_bot.send_message import send_logs
        await send_logs(message)
    except ImportError as e:
        logger.warning(f"Telegram not configured: {e}")
    except Exception as e:
        logger.error(f"Failed to send telegram message: {e}")


async def safe_send_disable_notification(message: str, username: str):
    """Safely send disable notification with enable button"""
    try:
        from telegram_bot.send_message import send_disable_notification
        await send_disable_notification(message, username)
    except ImportError as e:
        logger.warning(f"Telegram not configured: {e}")
        await safe_send_logs(message)
    except Exception as e:
        logger.error(f"Failed to send disable notification: {e}")
        await safe_send_logs(message)


async def safe_disable_user(panel_data: PanelType, user: UserType):
    """Safely disable user, handling import errors gracefully"""
    try:
        from utils.panel_api import disable_user
        await disable_user(panel_data, user)
    except ImportError as e:
        logger.error(f"Failed to import disable_user: {e}")
    except Exception as e:
        logger.error(f"Failed to disable user {user.name}: {e}")


async def safe_disable_user_with_punishment(panel_data: PanelType, user: UserType) -> dict:
    """
    Safely disable user with smart punishment system.
    Returns punishment result dict or error dict.
    """
    try:
        from utils.panel_api import disable_user_with_punishment
        return await disable_user_with_punishment(panel_data, user)
    except ImportError as e:
        logger.error(f"Failed to import disable_user_with_punishment: {e}")
        return {"action": "error", "message": str(e), "step_index": 0, "violation_count": 0, "duration_minutes": 0}
    except Exception as e:
        logger.error(f"Failed to disable user {user.name} with punishment: {e}")
        return {"action": "error", "message": str(e), "step_index": 0, "violation_count": 0, "duration_minutes": 0}
