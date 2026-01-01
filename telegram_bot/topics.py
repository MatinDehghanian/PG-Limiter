"""
Telegram Topics Management for PG-Limiter.
Manages forum topics in private chats for organizing bot messages.

Topics:
- General: Settings, actions, and general messages
- Warnings: User warning notifications
- Disable/Enable: User disable/enable notifications
- Active Users: Active users log and reports
- Backups: Automatic backup notifications
- No Limit Found: Users without special limits
"""

import json
import os
from enum import Enum
from typing import Optional
from utils.logs import get_logger

topics_logger = get_logger("topics")

# Topics data file
TOPICS_FILE = "data/topics.json"


class TopicType(Enum):
    """Topic types for message categorization."""
    GENERAL = "general"
    WARNINGS = "warnings"
    DISABLE_ENABLE = "disable_enable"
    ACTIVE_USERS = "active_users"
    BACKUPS = "backups"
    NO_LIMIT = "no_limit"


# Topic display configuration
TOPIC_CONFIG = {
    TopicType.GENERAL: {
        "name": "⚙️ General",
        "icon_color": 0x6FB9F0,  # Blue
        "description": "Settings, actions, and general messages"
    },
    TopicType.WARNINGS: {
        "name": "⚠️ Warnings",
        "icon_color": 0xFFD67E,  # Yellow
        "description": "User warning notifications"
    },
    TopicType.DISABLE_ENABLE: {
        "name": "🔒 Disable/Enable",
        "icon_color": 0xCB86DB,  # Purple
        "description": "User disable and enable notifications"
    },
    TopicType.ACTIVE_USERS: {
        "name": "👥 Active Users",
        "icon_color": 0x8EEE98,  # Green
        "description": "Active users log and reports"
    },
    TopicType.BACKUPS: {
        "name": "💾 Backups",
        "icon_color": 0xE0A4A4,  # Pink
        "description": "Automatic backup notifications"
    },
    TopicType.NO_LIMIT: {
        "name": "📱 No Limit Found",
        "icon_color": 0xF28C28,  # Orange
        "description": "Users without special limits"
    },
}


class TopicsManager:
    """Manages Telegram forum topics for the bot."""
    
    def __init__(self):
        self._topics: dict[str, dict[str, int]] = {}  # chat_id -> {topic_type: thread_id}
        self._enabled: bool = False
        self._load()
    
    def _load(self):
        """Load topics configuration from file."""
        try:
            if os.path.exists(TOPICS_FILE):
                with open(TOPICS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._topics = data.get("topics", {})
                    self._enabled = data.get("enabled", False)
                topics_logger.debug(f"📁 Loaded topics config: enabled={self._enabled}, chats={len(self._topics)}")
        except Exception as e:
            topics_logger.error(f"❌ Failed to load topics: {e}")
            self._topics = {}
            self._enabled = False
    
    async def _save(self):
        """Save topics configuration to file."""
        try:
            os.makedirs(os.path.dirname(TOPICS_FILE), exist_ok=True)
            with open(TOPICS_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "enabled": self._enabled,
                    "topics": self._topics
                }, f, indent=2)
            topics_logger.debug("💾 Topics config saved")
        except Exception as e:
            topics_logger.error(f"❌ Failed to save topics: {e}")
    
    @property
    def enabled(self) -> bool:
        """Check if topics feature is enabled."""
        return self._enabled
    
    async def set_enabled(self, enabled: bool):
        """Enable or disable topics feature."""
        self._enabled = enabled
        await self._save()
        topics_logger.info(f"📌 Topics {'enabled' if enabled else 'disabled'}")
    
    def get_topic_id(self, chat_id: int, topic_type: TopicType) -> Optional[int]:
        """Get the thread ID for a specific topic in a chat."""
        if not self._enabled:
            return None
        chat_topics = self._topics.get(str(chat_id), {})
        return chat_topics.get(topic_type.value)
    
    async def set_topic_id(self, chat_id: int, topic_type: TopicType, thread_id: int):
        """Set the thread ID for a specific topic in a chat."""
        chat_id_str = str(chat_id)
        if chat_id_str not in self._topics:
            self._topics[chat_id_str] = {}
        self._topics[chat_id_str][topic_type.value] = thread_id
        await self._save()
        topics_logger.info(f"📌 Set {topic_type.value} topic to thread {thread_id} for chat {chat_id}")
    
    async def remove_topic(self, chat_id: int, topic_type: TopicType):
        """Remove a topic mapping."""
        chat_id_str = str(chat_id)
        if chat_id_str in self._topics and topic_type.value in self._topics[chat_id_str]:
            del self._topics[chat_id_str][topic_type.value]
            await self._save()
    
    async def clear_chat_topics(self, chat_id: int):
        """Clear all topics for a chat."""
        chat_id_str = str(chat_id)
        if chat_id_str in self._topics:
            del self._topics[chat_id_str]
            await self._save()
    
    def get_all_topics(self, chat_id: int) -> dict[str, int]:
        """Get all topic thread IDs for a chat."""
        return self._topics.get(str(chat_id), {})
    
    async def create_topics_for_chat(self, chat_id: int, bot) -> dict[TopicType, int]:
        """
        Create all forum topics for a chat.
        Returns dict of TopicType -> thread_id.
        """
        created_topics = {}
        
        for topic_type, config in TOPIC_CONFIG.items():
            try:
                # Create forum topic
                forum_topic = await bot.create_forum_topic(
                    chat_id=chat_id,
                    name=config["name"],
                    icon_color=config["icon_color"]
                )
                thread_id = forum_topic.message_thread_id
                await self.set_topic_id(chat_id, topic_type, thread_id)
                created_topics[topic_type] = thread_id
                topics_logger.info(f"✅ Created topic '{config['name']}' (thread_id={thread_id})")
            except Exception as e:
                topics_logger.error(f"❌ Failed to create topic '{config['name']}': {e}")
        
        return created_topics


# Global instance
_topics_manager: Optional[TopicsManager] = None


def get_topics_manager() -> TopicsManager:
    """Get or create the global topics manager instance."""
    global _topics_manager
    if _topics_manager is None:
        _topics_manager = TopicsManager()
    return _topics_manager


async def send_to_topic(
    bot,
    chat_id: int,
    text: str,
    topic_type: TopicType,
    parse_mode: str = "HTML",
    reply_markup=None,
    **kwargs
):
    """
    Send a message to a specific topic.
    Falls back to regular message if topics not enabled or topic not found.
    
    Args:
        bot: Telegram Bot instance
        chat_id: Chat ID to send to
        text: Message text
        topic_type: Type of topic to send to
        parse_mode: Message parse mode
        reply_markup: Optional keyboard markup
        **kwargs: Additional arguments for send_message
    
    Returns:
        Message object
    """
    manager = get_topics_manager()
    thread_id = manager.get_topic_id(chat_id, topic_type)
    
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            message_thread_id=thread_id,
            **kwargs
        )
    except Exception as e:
        topics_logger.warning(f"⚠️ Failed to send to topic {topic_type.value}: {e}")
        # Fallback to regular message without topic
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            **kwargs
        )


async def send_document_to_topic(
    bot,
    chat_id: int,
    document,
    topic_type: TopicType,
    **kwargs
):
    """
    Send a document to a specific topic.
    
    Args:
        bot: Telegram Bot instance
        chat_id: Chat ID to send to
        document: Document to send
        topic_type: Type of topic to send to
        **kwargs: Additional arguments for send_document
    
    Returns:
        Message object
    """
    manager = get_topics_manager()
    thread_id = manager.get_topic_id(chat_id, topic_type)
    
    try:
        return await bot.send_document(
            chat_id=chat_id,
            document=document,
            message_thread_id=thread_id,
            **kwargs
        )
    except Exception as e:
        topics_logger.warning(f"⚠️ Failed to send document to topic {topic_type.value}: {e}")
        # Fallback to regular message without topic
        return await bot.send_document(
            chat_id=chat_id,
            document=document,
            **kwargs
        )
