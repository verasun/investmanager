"""User profile management for personalization."""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from loguru import logger


class CommunicationStyle(str, Enum):
    """User's preferred communication style."""
    CONCISE = "concise"      # 简洁快速
    BALANCED = "balanced"    # 平衡适中
    DETAILED = "detailed"    # 详细分析


class TonePreference(str, Enum):
    """User's preferred tone."""
    FORMAL = "formal"        # 正式专业
    FRIENDLY = "friendly"    # 友好亲切
    CASUAL = "casual"        # 轻松随意


class TechnicalLevel(str, Enum):
    """User's technical knowledge level."""
    BEGINNER = "beginner"    # 入门
    MEDIUM = "medium"        # 进阶
    EXPERT = "expert"        # 专业


class RiskPreference(str, Enum):
    """User's risk tolerance."""
    AGGRESSIVE = "aggressive"    # 激进
    MODERATE = "moderate"        # 稳健
    CONSERVATIVE = "conservative"  # 保守


class InvestmentStyle(str, Enum):
    """User's investment style."""
    VALUE = "value"          # 价值投资
    GROWTH = "growth"        # 成长投资
    INDEX = "index"          # 指数投资
    TRADING = "trading"      # 短线交易


class InvestmentExperience(str, Enum):
    """User's investment experience level."""
    BEGINNER = "beginner"        # 新手
    INTERMEDIATE = "intermediate"  # 中级
    ADVANCED = "advanced"        # 资深


class InvestmentHorizon(str, Enum):
    """User's investment time horizon."""
    SHORT = "short"          # 短期 (<1年)
    MEDIUM = "medium"        # 中期 (1-3年)
    LONG = "long"            # 长期 (>3年)


class LearningStage(str, Enum):
    """User's learning stage in the personalization system."""
    ONBOARDING = "onboarding"  # 新用户引导 (0-5次交互)
    LEARNING = "learning"      # 学习阶段 (5-20次交互)
    MATURE = "mature"          # 成熟阶段 (20+次交互)


@dataclass
class UserProfile:
    """User profile containing preferences and statistics."""

    user_id: str
    nickname: Optional[str] = None

    # 沟通偏好
    communication_style: str = "balanced"
    tone_preference: str = "friendly"
    technical_level: str = "medium"

    # 投资偏好
    risk_preference: Optional[str] = None
    investment_style: Optional[str] = None
    investment_experience: Optional[str] = None
    investment_horizon: Optional[str] = None

    # 工作模式
    work_mode: str = "invest"  # invest, chat, dev

    # 关注领域
    preferred_topics: list[str] = field(default_factory=list)
    favorite_stocks: list[str] = field(default_factory=list)
    watchlist: list[str] = field(default_factory=list)

    # 股票提及次数 (用于判断关注程度)
    stock_mentions: dict[str, int] = field(default_factory=dict)

    # 统计
    total_interactions: int = 0
    last_interaction_at: Optional[str] = None
    created_at: Optional[str] = None
    learning_stage: str = "onboarding"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        """Create from dictionary."""
        return cls(
            user_id=data.get("user_id", ""),
            nickname=data.get("nickname"),
            communication_style=data.get("communication_style", "balanced"),
            tone_preference=data.get("tone_preference", "friendly"),
            technical_level=data.get("technical_level", "medium"),
            risk_preference=data.get("risk_preference"),
            investment_style=data.get("investment_style"),
            investment_experience=data.get("investment_experience"),
            investment_horizon=data.get("investment_horizon"),
            work_mode=data.get("work_mode", "invest"),
            preferred_topics=data.get("preferred_topics", []),
            favorite_stocks=data.get("favorite_stocks", []),
            watchlist=data.get("watchlist", []),
            stock_mentions=data.get("stock_mentions", {}),
            total_interactions=data.get("total_interactions", 0),
            last_interaction_at=data.get("last_interaction_at"),
            created_at=data.get("created_at"),
            learning_stage=data.get("learning_stage", "onboarding"),
        )

    def update_stage(self) -> None:
        """Update learning stage based on interaction count."""
        if self.total_interactions >= 20:
            self.learning_stage = LearningStage.MATURE.value
        elif self.total_interactions >= 5:
            self.learning_stage = LearningStage.LEARNING.value
        else:
            self.learning_stage = LearningStage.ONBOARDING.value

    def get_style_description(self) -> str:
        """Get description of user's preferred style."""
        style_desc = {
            "concise": "简洁快速",
            "balanced": "平衡适中",
            "detailed": "详细分析",
        }
        return style_desc.get(self.communication_style, "平衡适中")

    def get_tone_description(self) -> str:
        """Get description of user's preferred tone."""
        tone_desc = {
            "formal": "正式专业",
            "friendly": "友好亲切",
            "casual": "轻松随意",
        }
        return tone_desc.get(self.tone_preference, "友好亲切")


class UserProfileManager:
    """Manager for user profiles."""

    # SQLite table definition
    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        nickname TEXT,
        communication_style TEXT DEFAULT 'balanced',
        tone_preference TEXT DEFAULT 'friendly',
        technical_level TEXT DEFAULT 'medium',
        risk_preference TEXT,
        investment_style TEXT,
        investment_experience TEXT,
        investment_horizon TEXT,
        work_mode TEXT DEFAULT 'invest',
        preferred_topics TEXT,
        favorite_stocks TEXT,
        watchlist TEXT,
        stock_mentions TEXT,
        total_interactions INTEGER DEFAULT 0,
        last_interaction_at TEXT,
        created_at TEXT,
        learning_stage TEXT DEFAULT 'onboarding'
    )
    """

    def __init__(self, db_path: str = "./data/investmanager.db"):
        """Initialize profile manager."""
        self._db_path = db_path
        self._cache: dict[str, UserProfile] = {}
        self._initialized = False

    async def _ensure_table(self) -> None:
        """Ensure the table exists and has all required columns."""
        if self._initialized:
            return

        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(self.CREATE_TABLE_SQL)
            # Migration: Add work_mode column if it doesn't exist
            try:
                await db.execute(
                    "ALTER TABLE user_profiles ADD COLUMN work_mode TEXT DEFAULT 'invest'"
                )
            except Exception:
                pass  # Column already exists
            await db.commit()

        self._initialized = True
        logger.info("User profiles table initialized")

    async def get(self, user_id: str) -> UserProfile:
        """Get user profile, create if not exists."""
        # Check cache first
        if user_id in self._cache:
            return self._cache[user_id]

        await self._ensure_table()

        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()

            if row:
                profile = UserProfile(
                    user_id=row["user_id"],
                    nickname=row["nickname"],
                    communication_style=row["communication_style"] or "balanced",
                    tone_preference=row["tone_preference"] or "friendly",
                    technical_level=row["technical_level"] or "medium",
                    risk_preference=row["risk_preference"],
                    investment_style=row["investment_style"],
                    investment_experience=row["investment_experience"],
                    investment_horizon=row["investment_horizon"],
                    work_mode=row["work_mode"] or "invest",
                    preferred_topics=json.loads(row["preferred_topics"] or "[]"),
                    favorite_stocks=json.loads(row["favorite_stocks"] or "[]"),
                    watchlist=json.loads(row["watchlist"] or "[]"),
                    stock_mentions=json.loads(row["stock_mentions"] or "{}"),
                    total_interactions=row["total_interactions"] or 0,
                    last_interaction_at=row["last_interaction_at"],
                    created_at=row["created_at"],
                    learning_stage=row["learning_stage"] or "onboarding",
                )
            else:
                # Create new profile
                profile = UserProfile(
                    user_id=user_id,
                    created_at=datetime.now().isoformat(),
                )
                await self._save(profile)

        self._cache[user_id] = profile
        return profile

    async def update(self, profile: UserProfile) -> None:
        """Update user profile."""
        profile.update_stage()
        profile.last_interaction_at = datetime.now().isoformat()
        await self._save(profile)
        self._cache[profile.user_id] = profile

    async def _save(self, profile: UserProfile) -> None:
        """Save profile to database."""
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO user_profiles (
                    user_id, nickname, communication_style, tone_preference,
                    technical_level, risk_preference, investment_style,
                    investment_experience, investment_horizon, work_mode,
                    preferred_topics, favorite_stocks, watchlist, stock_mentions,
                    total_interactions, last_interaction_at, created_at, learning_stage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.user_id,
                    profile.nickname,
                    profile.communication_style,
                    profile.tone_preference,
                    profile.technical_level,
                    profile.risk_preference,
                    profile.investment_style,
                    profile.investment_experience,
                    profile.investment_horizon,
                    profile.work_mode,
                    json.dumps(profile.preferred_topics),
                    json.dumps(profile.favorite_stocks),
                    json.dumps(profile.watchlist),
                    json.dumps(profile.stock_mentions),
                    profile.total_interactions,
                    profile.last_interaction_at,
                    profile.created_at,
                    profile.learning_stage,
                ),
            )
            await db.commit()

    async def increment_interactions(self, user_id: str) -> UserProfile:
        """Increment interaction count and update stage."""
        profile = await self.get(user_id)
        profile.total_interactions += 1
        await self.update(profile)
        return profile

    async def set_preference(
        self, user_id: str, key: str, value: str
    ) -> UserProfile:
        """Set a specific preference."""
        profile = await self.get(user_id)

        # Map keys to profile attributes
        valid_keys = {
            "communication_style", "tone_preference", "technical_level",
            "risk_preference", "investment_style", "investment_experience",
            "investment_horizon", "nickname", "work_mode",
        }

        if key in valid_keys:
            setattr(profile, key, value)
            await self.update(profile)

        return profile

    async def get_work_mode(self, user_id: str) -> str:
        """Get user's current work mode."""
        profile = await self.get(user_id)
        return profile.work_mode

    async def set_work_mode(self, user_id: str, mode: str) -> UserProfile:
        """Set user's work mode."""
        valid_modes = {"invest", "chat", "dev"}
        if mode not in valid_modes:
            raise ValueError(f"Invalid work mode: {mode}. Valid modes: {valid_modes}")
        return await self.set_preference(user_id, "work_mode", mode)

    async def cycle_work_mode(self, user_id: str) -> tuple[str, UserProfile]:
        """Cycle to next work mode for user.

        Returns:
            Tuple of (new_mode, updated_profile)
        """
        profile = await self.get(user_id)
        modes = ["invest", "chat", "dev"]
        current_idx = modes.index(profile.work_mode) if profile.work_mode in modes else 0
        next_mode = modes[(current_idx + 1) % len(modes)]
        profile = await self.set_work_mode(user_id, next_mode)
        return next_mode, profile

    async def add_to_watchlist(self, user_id: str, stock: str) -> UserProfile:
        """Add stock to user's watchlist."""
        profile = await self.get(user_id)
        if stock not in profile.watchlist:
            profile.watchlist.append(stock)
            await self.update(profile)
        return profile

    async def remove_from_watchlist(self, user_id: str, stock: str) -> UserProfile:
        """Remove stock from user's watchlist."""
        profile = await self.get(user_id)
        if stock in profile.watchlist:
            profile.watchlist.remove(stock)
            await self.update(profile)
        return profile

    async def add_stock_mention(self, user_id: str, stock: str) -> UserProfile:
        """Record a stock mention."""
        profile = await self.get(user_id)
        profile.stock_mentions[stock] = profile.stock_mentions.get(stock, 0) + 1
        await self.update(profile)
        return profile

    async def clear_profile(self, user_id: str) -> None:
        """Clear user profile (reset to defaults)."""
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "DELETE FROM user_profiles WHERE user_id = ?", (user_id,)
            )
            await db.commit()

        if user_id in self._cache:
            del self._cache[user_id]

        logger.info(f"Cleared profile for user {user_id}")


# Global instance
_profile_manager: Optional[UserProfileManager] = None


def get_profile_manager() -> UserProfileManager:
    """Get or create the global profile manager."""
    global _profile_manager
    if _profile_manager is None:
        from config.settings import settings
        db_path = settings.sqlite_db_path or "./data/investmanager.db"
        _profile_manager = UserProfileManager(db_path)
    return _profile_manager