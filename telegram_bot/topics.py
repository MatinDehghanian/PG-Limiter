"""
Telegram Topics Management for PG-Limiter.
Manages forum topics in a forum supergroup for organizing bot messages.

Note: Telegram Bot API requires forum topics to be created in supergroups
with topics enabled (is_forum=True), not in private chats.

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
import time
from enum import Enum
from typing import Optional
from utils.logs import get_logger

topics_logger = get_logger("topics")

# Topics data file
TOPICS_FILE = "data/topics.json"

# Message cache file for deduplication
MESSAGE_CACHE_FILE = "data/topic_message_cache.json"

# Cache expiry in seconds (24 hours)
MESSAGE_CACHE_EXPIRY = 86400


class TopicType(Enum):
    """Topic types for message categorization."""
    GENERAL = "general"
    WARNINGS = "warnings"
    DISABLE_ENABLE = "disable_enable"
    ACTIVE_USERS = "active_users"
    BACKUPS = "backups"
    NO_LIMIT = "no_limit"
    MONITORING = "monitoring"


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
        "icon_color": 0xFF93B2,  # Pink
        "description": "Automatic backup notifications"
    },
    TopicType.NO_LIMIT: {
        "name": "📱 No Limit Found",
        "icon_color": 0xFB6F5F,  # Orange-red
        "description": "Users without special limits"
    },
    TopicType.MONITORING: {
        "name": "📊 Monitoring",
        "icon_color": 0x6FB9F0,  # Blue
        "description": "Monitoring status and analytics"
    },
}


class TopicsManager:
    """Manages Telegram forum topics in a supergroup for the bot."""
    
    def __init__(self):
        self._topics: dict[str, int] = {}  # topic_type -> thread_id
        self._group_id: Optional[int] = None  # Forum group ID
        self._enabled: bool = False
        self._message_cache: dict[str, dict] = {}  # {topic_type: {message_key: timestamp}}
        self._load()
        self._load_message_cache()
    
    def _load(self):
        """Load topics configuration from file."""
        try:
            if os.path.exists(TOPICS_FILE):
                with open(TOPICS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._topics = data.get("topics", {})
                    self._enabled = data.get("enabled", False)
                    self._group_id = data.get("group_id")
                topics_logger.debug(f"📁 Loaded topics config: enabled={self._enabled}, group={self._group_id}")
        except Exception as e:
            topics_logger.error(f"❌ Failed to load topics: {e}")
            self._topics = {}
            self._enabled = False
            self._group_id = None
    
    def _load_message_cache(self):
        """Load message cache for deduplication."""
        try:
            if os.path.exists(MESSAGE_CACHE_FILE):
                with open(MESSAGE_CACHE_FILE, 'r', encoding='utf-8') as f:
                    self._message_cache = json.load(f)
                # Clean expired entries
                self._clean_expired_cache()
        except Exception as e:
            topics_logger.error(f"❌ Failed to load message cache: {e}")
            self._message_cache = {}
    
    def _clean_expired_cache(self):
        """Remove expired entries from message cache."""
        current_time = time.time()
        for topic_type in list(self._message_cache.keys()):
            topic_cache = self._message_cache.get(topic_type, {})
            expired_keys = [
                key for key, timestamp in topic_cache.items()
                if current_time - timestamp > MESSAGE_CACHE_EXPIRY
            ]
            for key in expired_keys:
                del topic_cache[key]
            if not topic_cache:
                del self._message_cache[topic_type]
    
    async def _save_message_cache(self):
        """Save message cache to file."""
        try:
            os.makedirs(os.path.dirname(MESSAGE_CACHE_FILE), exist_ok=True)
            with open(MESSAGE_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._message_cache, f, indent=2)
        except Exception as e:
            topics_logger.error(f"❌ Failed to save message cache: {e}")
    
    def is_message_sent(self, topic_type: TopicType, message_key: str) -> bool:
        """Check if a message with this key was already sent to the topic."""
        if not self._enabled:
            return False
        topic_cache = self._message_cache.get(topic_type.value, {})
        if message_key in topic_cache:
            # Check if not expired
            if time.time() - topic_cache[message_key] < MESSAGE_CACHE_EXPIRY:
                return True
        return False
    
    async def mark_message_sent(self, topic_type: TopicType, message_key: str):
        """Mark a message as sent to a topic."""
        if topic_type.value not in self._message_cache:
            self._message_cache[topic_type.value] = {}
        self._message_cache[topic_type.value][message_key] = time.time()
        await self._save_message_cache()
    
    async def clear_message_cache(self, topic_type: Optional[TopicType] = None):
        """Clear message cache for a topic or all topics."""
        if topic_type:
            if topic_type.value in self._message_cache:
                del self._message_cache[topic_type.value]
        else:
            self._message_cache = {}
        await self._save_message_cache()
    
    async def _save(self):
        """Save topics configuration to file."""
        try:
            os.makedirs(os.path.dirname(TOPICS_FILE), exist_ok=True)
            with open(TOPICS_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "enabled": self._enabled,
                    "group_id": self._group_id,
                    "topics": self._topics
                }, f, indent=2)
            topics_logger.debug("💾 Topics config saved")
        except Exception as e:
            topics_logger.error(f"❌ Failed to save topics: {e}")
    
    @property
    def enabled(self) -> bool:
        """Check if topics feature is enabled."""
        return self._enabled
    
    @property
    def group_id(self) -> Optional[int]:
        """Get the configured forum group ID."""
        return self._group_id
    
    async def set_group_id(self, group_id: int):
        """Set the forum group ID."""
        self._group_id = group_id
        await self._save()
        topics_logger.info(f"📌 Forum group set to {group_id}")
    
    async def set_enabled(self, enabled: bool):
        """Enable or disable topics feature."""
        self._enabled = enabled
        await self._save()
        topics_logger.info(f"📌 Topics {'enabled' if enabled else 'disabled'}")
    
    def get_topic_id(self, topic_type: TopicType) -> Optional[int]:
        """Get the thread ID for a specific topic."""
        if not self._enabled or not self._group_id:
            return None
        return self._topics.get(topic_type.value)
    
    async def set_topic_id(self, topic_type: TopicType, thread_id: int):
        """Set the thread ID for a specific topic."""
        self._topics[topic_type.value] = thread_id
        await self._save()
        topics_logger.info(f"📌 Set {topic_type.value} topic to thread {thread_id}")
    
    async def remove_topic(self, topic_type: TopicType):
        """Remove a topic mapping."""
        if topic_type.value in self._topics:
            del self._topics[topic_type.value]
            await self._save()
    
    async def clear_all_topics(self):
        """Clear all topics."""
        self._topics = {}
        await self._save()
    
    def get_all_topics(self) -> dict[str, int]:
        """Get all topic thread IDs."""
        return self._topics.copy()
    
    async def check_bot_permissions(self, bot) -> tuple[bool, str]:
        """
        Check if the bot is admin in the forum group with can_manage_topics permission.
        Returns (success, message).
        """
        if not self._group_id:
            return False, "No forum group configured. Please set a group ID first."
        
        try:
            # Get chat info
            chat = await bot.get_chat(self._group_id)
            
            # Check if it's a forum supergroup
            if not getattr(chat, 'is_forum', False):
                return False, (
                    "The specified chat is not a forum supergroup.\n"
                    "Please enable Topics in the group settings first."
                )
            
            # Get bot's member info
            bot_member = await bot.get_chat_member(self._group_id, bot.id)
            
            # Check if bot is admin
            if bot_member.status not in ['administrator', 'creator']:
                return False, (
                    "The bot is not an administrator in the group.\n"
                    "Please make the bot an admin with 'Manage Topics' permission."
                )
            
            # Check can_manage_topics permission
            if bot_member.status == 'administrator':
                if not getattr(bot_member, 'can_manage_topics', False):
                    return False, (
                        "The bot doesn't have 'Manage Topics' permission.\n"
                        "Please enable this permission for the bot."
                    )
            
            return True, f"✅ Bot has required permissions in group: {chat.title}"
            
        except Exception as e:
            return False, f"Failed to check permissions: {str(e)}"
    
    async def create_topics_for_group(self, bot) -> dict[TopicType, int]:
        """
        Create all forum topics in the configured group.
        Returns dict of TopicType -> thread_id.
        """
        if not self._group_id:
            topics_logger.error("❌ No forum group configured")
            return {}
        
        # Check permissions first
        success, message = await self.check_bot_permissions(bot)
        if not success:
            topics_logger.error(f"❌ Permission check failed: {message}")
            return {}
        
        created_topics = {}
        
        for topic_type, config in TOPIC_CONFIG.items():
            try:
                # Create forum topic in the group
                forum_topic = await bot.create_forum_topic(
                    chat_id=self._group_id,
                    name=config["name"],
                    icon_color=config["icon_color"]
                )
                thread_id = forum_topic.message_thread_id
                await self.set_topic_id(topic_type, thread_id)
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
    text: str,
    topic_type: TopicType,
    parse_mode: str = "HTML",
    reply_markup=None,
    message_key: Optional[str] = None,
    **kwargs
):
    """
    Send a message to a specific topic in the forum group.
    Falls back to None if topics not enabled or topic not found.
    
    Args:
        bot: Telegram Bot instance
        text: Message text
        topic_type: Type of topic to send to
        parse_mode: Message parse mode
        reply_markup: Optional keyboard markup
        message_key: Optional key for deduplication (if provided, message won't be sent if already sent with same key)
        **kwargs: Additional arguments for send_message
    
    Returns:
        Message object or None
    """
    manager = get_topics_manager()
    
    if not manager.enabled or not manager.group_id:
        return None
    
    # Check for duplicate message if message_key provided
    if message_key and manager.is_message_sent(topic_type, message_key):
        topics_logger.debug(f"⏭️ Skipping duplicate message: {message_key[:50]}...")
        return None
    
    thread_id = manager.get_topic_id(topic_type)
    
    try:
        message = await bot.send_message(
            chat_id=manager.group_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            message_thread_id=thread_id,
            **kwargs
        )
        
        # Mark message as sent if key provided
        if message_key:
            await manager.mark_message_sent(topic_type, message_key)
        
        return message
    except Exception as e:
        topics_logger.warning(f"⚠️ Failed to send to topic {topic_type.value}: {e}")
        return None


async def send_document_to_topic(
    bot,
    document,
    topic_type: TopicType,
    **kwargs
):
    """
    Send a document to a specific topic in the forum group.
    
    Args:
        bot: Telegram Bot instance
        document: Document to send
        topic_type: Type of topic to send to
        **kwargs: Additional arguments for send_document
    
    Returns:
        Message object or None
    """
    manager = get_topics_manager()
    
    if not manager.enabled or not manager.group_id:
        return None
    
    thread_id = manager.get_topic_id(topic_type)
    
    try:
        return await bot.send_document(
            chat_id=manager.group_id,
            document=document,
            message_thread_id=thread_id,
            **kwargs
        )
    except Exception as e:
        topics_logger.warning(f"⚠️ Failed to send document to topic {topic_type.value}: {e}")
        return None
