"""Interactive learning for user personalization."""

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from loguru import logger

from src.memory.profile_manager import (
    UserProfile,
    UserProfileManager,
    get_profile_manager,
    LearningStage,
)


class TaskType(str, Enum):
    """Types of learning tasks."""
    STYLE_INQUIRE = "style_inquire"           # Ask about communication style
    TONE_INQUIRE = "tone_inquire"             # Ask about tone preference
    TECHNICAL_INQUIRE = "technical_inquire"   # Ask about technical level
    RISK_INQUIRE = "risk_inquire"             # Ask about risk preference
    STYLE_CONFIRM = "style_confirm"           # Confirm investment style
    STOCK_CONFIRM = "stock_confirm"           # Confirm stock interest
    TOPIC_CONFIRM = "topic_confirm"           # Confirm topic interest
    EXPERIENCE_INQUIRE = "experience_inquire" # Ask about experience


@dataclass
class LearningTask:
    """A learning task to gather user preference."""

    task_id: str
    user_id: str
    task_type: TaskType
    question: str
    options: list[str]
    preference_key: str
    priority: int = 5
    asked: bool = False
    answered: bool = False
    answer: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "task_type": self.task_type.value if isinstance(self.task_type, TaskType) else self.task_type,
            "question": self.question,
            "options": self.options,
            "preference_key": self.preference_key,
            "priority": self.priority,
            "asked": self.asked,
            "answered": self.answered,
            "answer": self.answer,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearningTask":
        """Create from dictionary."""
        return cls(
            task_id=data.get("task_id", ""),
            user_id=data.get("user_id", ""),
            task_type=TaskType(data.get("task_type", "style_inquire")),
            question=data.get("question", ""),
            options=data.get("options", []),
            preference_key=data.get("preference_key", ""),
            priority=data.get("priority", 5),
            asked=data.get("asked", False),
            answered=data.get("answered", False),
            answer=data.get("answer"),
            created_at=data.get("created_at"),
        )


class InteractiveLearningManager:
    """Manage interactive learning tasks."""

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS learning_tasks (
        task_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        task_type TEXT NOT NULL,
        question TEXT NOT NULL,
        options TEXT NOT NULL,
        preference_key TEXT NOT NULL,
        priority INTEGER DEFAULT 5,
        asked INTEGER DEFAULT 0,
        answered INTEGER DEFAULT 0,
        answer TEXT,
        created_at TEXT,
        answered_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_learning_user_pending
    ON learning_tasks(user_id, asked, answered);
    """

    # Task templates
    TASK_TEMPLATES = {
        TaskType.STYLE_INQUIRE: {
            "question": "您希望我用什么风格回答？",
            "options": ["简洁快速", "平衡适中", "详细分析"],
            "preference_key": "communication_style",
            "option_values": ["concise", "balanced", "detailed"],
        },
        TaskType.TONE_INQUIRE: {
            "question": "您更喜欢什么样的语气？",
            "options": ["正式专业", "友好亲切", "轻松随意"],
            "preference_key": "tone_preference",
            "option_values": ["formal", "friendly", "casual"],
        },
        TaskType.TECHNICAL_INQUIRE: {
            "question": "您的投资知识水平如何？",
            "options": ["入门新手", "有一定基础", "专业精通"],
            "preference_key": "technical_level",
            "option_values": ["beginner", "medium", "expert"],
        },
        TaskType.RISK_INQUIRE: {
            "question": "您的风险承受能力如何？",
            "options": ["激进型", "稳健型", "保守型"],
            "preference_key": "risk_preference",
            "option_values": ["aggressive", "moderate", "conservative"],
        },
        TaskType.STYLE_CONFIRM: {
            "question": "您更偏好哪种投资方式？",
            "options": ["长线价值投资", "成长投资", "指数定投", "短线交易"],
            "preference_key": "investment_style",
            "option_values": ["value", "growth", "index", "trading"],
        },
        TaskType.EXPERIENCE_INQUIRE: {
            "question": "您的投资经验如何？",
            "options": ["刚入门", "有一定经验", "多年经验"],
            "preference_key": "investment_experience",
            "option_values": ["beginner", "intermediate", "advanced"],
        },
    }

    def __init__(self, db_path: str = "./data/investmanager.db"):
        """Initialize learning manager."""
        self._db_path = db_path
        self._profile_manager: Optional[UserProfileManager] = None
        self._initialized = False

    @property
    def profile_manager(self) -> UserProfileManager:
        """Get profile manager instance."""
        if self._profile_manager is None:
            self._profile_manager = get_profile_manager()
        return self._profile_manager

    async def _ensure_table(self) -> None:
        """Ensure the table exists."""
        if self._initialized:
            return

        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(self.CREATE_TABLE_SQL)
            await db.commit()

        self._initialized = True
        logger.info("Learning tasks table initialized")

    async def get_next_task(self, user_id: str) -> Optional[LearningTask]:
        """Get the next pending learning task for a user."""
        await self._ensure_table()

        # Check if we should create new tasks
        profile = await self.profile_manager.get(user_id)

        # Determine which tasks to create based on stage and current profile
        if profile.learning_stage == LearningStage.ONBOARDING.value:
            await self._ensure_onboarding_tasks(user_id, profile)
        elif profile.learning_stage == LearningStage.LEARNING.value:
            await self._ensure_learning_tasks(user_id, profile)

        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM learning_tasks
                WHERE user_id = ? AND asked = 0 AND answered = 0
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (user_id,),
            )
            row = await cursor.fetchone()

            if row:
                return LearningTask(
                    task_id=row["task_id"],
                    user_id=row["user_id"],
                    task_type=TaskType(row["task_type"]),
                    question=row["question"],
                    options=json.loads(row["options"]),
                    preference_key=row["preference_key"],
                    priority=row["priority"],
                    asked=bool(row["asked"]),
                    answered=bool(row["answered"]),
                    answer=row["answer"],
                    created_at=row["created_at"],
                )

        return None

    async def _ensure_onboarding_tasks(
        self, user_id: str, profile: UserProfile
    ) -> None:
        """Ensure onboarding tasks exist."""
        # Create style task if not set
        if profile.total_interactions == 0:
            await self._create_task_if_not_exists(
                user_id, TaskType.STYLE_INQUIRE, priority=10
            )
        elif profile.total_interactions == 2 and not profile.technical_level:
            await self._create_task_if_not_exists(
                user_id, TaskType.TECHNICAL_INQUIRE, priority=8
            )

    async def _ensure_learning_tasks(
        self, user_id: str, profile: UserProfile
    ) -> None:
        """Ensure learning stage tasks exist."""
        # Create risk preference task if not set and enough interactions
        if profile.total_interactions >= 5 and not profile.risk_preference:
            await self._create_task_if_not_exists(
                user_id, TaskType.RISK_INQUIRE, priority=7
            )

        # Create investment style task if not set
        if profile.total_interactions >= 10 and not profile.investment_style:
            await self._create_task_if_not_exists(
                user_id, TaskType.STYLE_CONFIRM, priority=6
            )

        # Create stock confirmation tasks for frequently mentioned stocks
        for stock, count in profile.stock_mentions.items():
            if count >= 3 and stock not in profile.watchlist:
                await self._create_stock_confirm_task(user_id, stock)

    async def _create_task_if_not_exists(
        self,
        user_id: str,
        task_type: TaskType,
        priority: int = 5,
    ) -> bool:
        """Create a task if it doesn't already exist."""
        import aiosqlite
        import uuid

        template = self.TASK_TEMPLATES.get(task_type)
        if not template:
            return False

        async with aiosqlite.connect(self._db_path) as db:
            # Check if task already exists
            cursor = await db.execute(
                """
                SELECT task_id FROM learning_tasks
                WHERE user_id = ? AND task_type = ? AND answered = 0
                """,
                (user_id, task_type.value),
            )
            existing = await cursor.fetchone()

            if existing:
                return False

            # Create new task
            task_id = str(uuid.uuid4())[:8]
            await db.execute(
                """
                INSERT INTO learning_tasks
                (task_id, user_id, task_type, question, options, preference_key, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    user_id,
                    task_type.value,
                    template["question"],
                    json.dumps(template["options"]),
                    template["preference_key"],
                    priority,
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()

        logger.info(f"Created learning task {task_type.value} for user {user_id}")
        return True

    async def _create_stock_confirm_task(
        self, user_id: str, stock: str
    ) -> None:
        """Create a task to confirm stock interest."""
        import aiosqlite
        import uuid

        task_id = f"stock_{stock}_{str(uuid.uuid4())[:4]}"

        async with aiosqlite.connect(self._db_path) as db:
            # Check if task already exists
            cursor = await db.execute(
                """
                SELECT task_id FROM learning_tasks
                WHERE user_id = ? AND task_type = ? AND answer IS NULL
                """,
                (user_id, TaskType.STOCK_CONFIRM.value),
            )
            existing = await cursor.fetchone()

            if existing:
                return

            await db.execute(
                """
                INSERT INTO learning_tasks
                (task_id, user_id, task_type, question, options, preference_key, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    user_id,
                    TaskType.STOCK_CONFIRM.value,
                    f"您经常提到{stock}，是否将其加入自选？",
                    json.dumps(["是的，加入自选", "暂时不用"]),
                    "watchlist",
                    5,
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()

    async def mark_task_asked(self, task_id: str) -> None:
        """Mark a task as asked."""
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE learning_tasks SET asked = 1 WHERE task_id = ?",
                (task_id,),
            )
            await db.commit()

    async def complete_task(
        self, task_id: str, answer: str, option_index: Optional[int] = None
    ) -> Optional[str]:
        """Complete a learning task with the user's answer.

        Args:
            task_id: Task ID
            answer: User's answer text
            option_index: Selected option index (if applicable)

        Returns:
            The preference value that was set, or None
        """
        import aiosqlite

        await self._ensure_table()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM learning_tasks WHERE task_id = ?", (task_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            task = LearningTask.from_dict(dict(row))

            # Determine the preference value
            preference_value = None
            if option_index is not None and task.task_type in self.TASK_TEMPLATES:
                template = self.TASK_TEMPLATES[task.task_type]
                option_values = template.get("option_values", [])
                if 0 <= option_index < len(option_values):
                    preference_value = option_values[option_index]
            elif option_index is not None:
                # For stock confirm, option 0 means add to watchlist
                if task.task_type == TaskType.STOCK_CONFIRM and option_index == 0:
                    preference_value = "add_to_watchlist"

            # Update task
            await db.execute(
                """
                UPDATE learning_tasks
                SET answered = 1, answer = ?, answered_at = ?
                WHERE task_id = ?
                """,
                (answer, datetime.now().isoformat(), task_id),
            )
            await db.commit()

            # Update user profile
            if preference_value and task.preference_key != "watchlist":
                await self.profile_manager.set_preference(
                    task.user_id, task.preference_key, preference_value
                )
            elif task.task_type == TaskType.STOCK_CONFIRM and preference_value == "add_to_watchlist":
                # Extract stock from question
                import re
                match = re.search(r"提到(\w+)", task.question)
                if match:
                    stock = match.group(1)
                    await self.profile_manager.add_to_watchlist(task.user_id, stock)

            logger.info(f"Completed learning task {task_id} with answer: {answer}")

            return preference_value

    async def get_pending_task_for_user(self, user_id: str) -> Optional[dict]:
        """Get formatted pending task for response.

        Returns:
            Dict with task info formatted for response, or None
        """
        task = await self.get_next_task(user_id)

        if not task:
            return None

        # Mark as asked
        await self.mark_task_asked(task.task_id)

        return {
            "task_id": task.task_id,
            "question": task.question,
            "options": task.options,
            "task_type": task.task_type.value,
        }

    async def clear_user_tasks(self, user_id: str) -> None:
        """Clear all tasks for a user."""
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "DELETE FROM learning_tasks WHERE user_id = ?", (user_id,)
            )
            await db.commit()


# Global instance
_learning_manager: Optional[InteractiveLearningManager] = None


def get_learning_manager() -> InteractiveLearningManager:
    """Get or create the global learning manager."""
    global _learning_manager
    if _learning_manager is None:
        from config.settings import settings
        db_path = settings.sqlite_db_path or "./data/investmanager.db"
        _learning_manager = InteractiveLearningManager(db_path)
    return _learning_manager