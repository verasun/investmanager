"""Conversation memory management."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from loguru import logger


@dataclass
class ConversationMessage:
    """A single conversation message."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: str
    intent: Optional[str] = None
    preferences_extracted: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "intent": self.intent,
            "preferences_extracted": self.preferences_extracted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationMessage":
        """Create from dictionary."""
        return cls(
            role=data.get("role", ""),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", ""),
            intent=data.get("intent"),
            preferences_extracted=data.get("preferences_extracted", {}),
        )


class ConversationMemory:
    """Manager for conversation history."""

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS conversation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        intent TEXT,
        preferences_extracted TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_conv_user_time
    ON conversation_history(user_id, timestamp);
    """

    # Maximum messages to keep in short-term memory
    MAX_SHORT_TERM_MEMORY = 20

    # Maximum days to keep history
    MAX_HISTORY_DAYS = 30

    def __init__(self, db_path: str = "./data/investmanager.db"):
        """Initialize conversation memory."""
        self._db_path = db_path
        self._cache: dict[str, list[ConversationMessage]] = {}
        self._initialized = False

    async def _ensure_table(self) -> None:
        """Ensure the table exists."""
        if self._initialized:
            return

        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(self.CREATE_TABLE_SQL)
            await db.commit()

        self._initialized = True
        logger.info("Conversation history table initialized")

    async def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        intent: Optional[str] = None,
        preferences_extracted: Optional[dict] = None,
    ) -> None:
        """Add a message to conversation history."""
        await self._ensure_table()

        import aiosqlite

        timestamp = datetime.now().isoformat()

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO conversation_history
                (user_id, role, content, timestamp, intent, preferences_extracted)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    role,
                    content,
                    timestamp,
                    intent,
                    json.dumps(preferences_extracted or {}),
                ),
            )
            await db.commit()

        # Update cache
        if user_id not in self._cache:
            self._cache[user_id] = []

        self._cache[user_id].append(
            ConversationMessage(
                role=role,
                content=content,
                timestamp=timestamp,
                intent=intent,
                preferences_extracted=preferences_extracted or {},
            )
        )

        # Trim cache to max size
        if len(self._cache[user_id]) > self.MAX_SHORT_TERM_MEMORY:
            self._cache[user_id] = self._cache[user_id][-self.MAX_SHORT_TERM_MEMORY:]

    async def get_recent_messages(
        self, user_id: str, limit: int = 10
    ) -> list[ConversationMessage]:
        """Get recent messages for a user."""
        # Check cache first
        if user_id in self._cache:
            return self._cache[user_id][-limit:]

        await self._ensure_table()

        import aiosqlite

        messages = []

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM conversation_history
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = await cursor.fetchall()

            for row in reversed(rows):
                messages.append(
                    ConversationMessage(
                        role=row["role"],
                        content=row["content"],
                        timestamp=row["timestamp"],
                        intent=row["intent"],
                        preferences_extracted=json.loads(
                            row["preferences_extracted"] or "{}"
                        ),
                    )
                )

        # Update cache
        self._cache[user_id] = messages[-self.MAX_SHORT_TERM_MEMORY:]

        return messages

    async def get_conversation_summary(
        self, user_id: str, max_messages: int = 10
    ) -> str:
        """Generate a summary of recent conversation."""
        messages = await self.get_recent_messages(user_id, max_messages)

        if not messages:
            return "无最近对话记录"

        # Build summary
        summary_parts = []

        # Group by topics/intents
        intents_seen = set()
        stocks_mentioned = set()

        for msg in messages:
            if msg.intent and msg.intent not in intents_seen:
                intents_seen.add(msg.intent)
            if msg.preferences_extracted.get("mentioned_stocks"):
                stocks_mentioned.update(
                    msg.preferences_extracted["mentioned_stocks"]
                )

        if intents_seen:
            intent_names = {
                "collect_data": "数据收集",
                "analyze": "股票分析",
                "backtest": "策略回测",
                "comprehensive": "综合分析",
                "mode_switch": "模式切换",
                "help": "帮助查询",
            }
            activities = [intent_names.get(i, i) for i in intents_seen]
            summary_parts.append(f"最近活动: {', '.join(activities)}")

        if stocks_mentioned:
            summary_parts.append(f"提及股票: {', '.join(stocks_mentioned)}")

        # Add last message preview
        if messages:
            last_user_msg = None
            for msg in reversed(messages):
                if msg.role == "user":
                    last_user_msg = msg.content[:50]
                    break
            if last_user_msg:
                summary_parts.append(f"最近问题: {last_user_msg}...")

        return " | ".join(summary_parts) if summary_parts else "新用户"

    async def clear_history(self, user_id: str) -> None:
        """Clear conversation history for a user."""
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "DELETE FROM conversation_history WHERE user_id = ?", (user_id,)
            )
            await db.commit()

        if user_id in self._cache:
            del self._cache[user_id]

        logger.info(f"Cleared conversation history for user {user_id}")

    async def cleanup_old_history(self, days: int = 30) -> int:
        """Clean up old conversation history."""
        import aiosqlite

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM conversation_history WHERE timestamp < ?",
                (cutoff,),
            )
            deleted = cursor.rowcount
            await db.commit()

        logger.info(f"Cleaned up {deleted} old conversation records")
        return deleted


# Global instance
_conversation_memory: Optional[ConversationMemory] = None


def get_conversation_memory() -> ConversationMemory:
    """Get or create the global conversation memory."""
    global _conversation_memory
    if _conversation_memory is None:
        from config.settings import settings
        db_path = settings.sqlite_db_path or "./data/investmanager.db"
        _conversation_memory = ConversationMemory(db_path)
    return _conversation_memory