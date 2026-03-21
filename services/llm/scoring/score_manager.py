"""Score management for model performance tracking.

Stores and retrieves model scores per scenario with SQLite persistence.
"""

import asyncio
import json
import aiosqlite
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from loguru import logger

from config.settings import settings


@dataclass
class ModelScore:
    """Score record for a model in a specific scenario."""
    model_id: str
    scenario: str  # text, deep_thinking, visual, coding
    quality_score: float = 0.5  # Primary metric (0-1)
    latency_score: float = 0.5
    cost_score: float = 0.5
    satisfaction_score: float = 0.5
    sample_count: int = 0
    last_updated: Optional[datetime] = None

    def weighted_score(
        self,
        quality_weight: float = 0.5,
        latency_weight: float = 0.3,
        cost_weight: float = 0.2,
    ) -> float:
        """Calculate weighted overall score."""
        return (
            self.quality_score * quality_weight +
            self.latency_score * latency_weight +
            self.cost_score * cost_weight
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "model_id": self.model_id,
            "scenario": self.scenario,
            "quality_score": self.quality_score,
            "latency_score": self.latency_score,
            "cost_score": self.cost_score,
            "satisfaction_score": self.satisfaction_score,
            "sample_count": self.sample_count,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


@dataclass
class ExecutionRecord:
    """Record of a model execution for scoring."""
    trace_id: str
    model_id: str
    scenario: str
    task_type: str
    latency_ms: int
    tokens_used: int
    success: bool
    explicit_feedback: Optional[int] = None  # 1-5 rating
    implicit_feedback: Optional[dict] = None  # {"reasked": true, "followup_count": 2}
    quality_score: Optional[float] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "trace_id": self.trace_id,
            "model_id": self.model_id,
            "scenario": self.scenario,
            "task_type": self.task_type,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "success": self.success,
            "explicit_feedback": self.explicit_feedback,
            "implicit_feedback": self.implicit_feedback,
            "quality_score": self.quality_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ScoreManager:
    """Manages model performance scores with SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.sqlite_db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def _get_db(self) -> aiosqlite.Connection:
        """Get or create database connection."""
        if self._db is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
            await self._create_tables()
        return self._db

    async def _create_tables(self):
        """Create database tables if they don't exist."""
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS model_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT NOT NULL,
                scenario TEXT NOT NULL,
                quality_score REAL DEFAULT 0.5,
                latency_score REAL DEFAULT 0.5,
                cost_score REAL DEFAULT 0.5,
                satisfaction_score REAL DEFAULT 0.5,
                sample_count INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(model_id, scenario)
            );

            CREATE TABLE IF NOT EXISTS execution_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT,
                model_id TEXT NOT NULL,
                scenario TEXT NOT NULL,
                task_type TEXT,
                latency_ms INTEGER,
                tokens_used INTEGER,
                success BOOLEAN,
                explicit_feedback INTEGER,
                implicit_feedback TEXT,
                quality_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT,
                user_id TEXT,
                message_id TEXT,
                model_id TEXT,
                feedback_type TEXT,
                rating INTEGER,
                signal_type TEXT,
                signal_value REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_execution_trace ON execution_history(trace_id);
            CREATE INDEX IF NOT EXISTS idx_execution_model ON execution_history(model_id);
            CREATE INDEX IF NOT EXISTS idx_feedback_trace ON user_feedback(trace_id);
        """)
        await self._db.commit()

    async def close(self):
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def get_score(self, model_id: str, scenario: str) -> ModelScore:
        """Get score for a model in a scenario."""
        async with self._lock:
            db = await self._get_db()
            cursor = await db.execute(
                """
                SELECT * FROM model_scores
                WHERE model_id = ? AND scenario = ?
                """,
                (model_id, scenario),
            )
            row = await cursor.fetchone()

            if row:
                return ModelScore(
                    model_id=row["model_id"],
                    scenario=row["scenario"],
                    quality_score=row["quality_score"],
                    latency_score=row["latency_score"],
                    cost_score=row["cost_score"],
                    satisfaction_score=row["satisfaction_score"],
                    sample_count=row["sample_count"],
                    last_updated=datetime.fromisoformat(row["last_updated"])
                    if row["last_updated"] else None,
                )

            # Return default score if not found
            return ModelScore(model_id=model_id, scenario=scenario)

    async def get_all_scores(self, scenario: Optional[str] = None) -> list[ModelScore]:
        """Get all scores, optionally filtered by scenario."""
        async with self._lock:
            db = await self._get_db()

            if scenario:
                cursor = await db.execute(
                    "SELECT * FROM model_scores WHERE scenario = ?",
                    (scenario,),
                )
            else:
                cursor = await db.execute("SELECT * FROM model_scores")

            rows = await cursor.fetchall()
            return [
                ModelScore(
                    model_id=row["model_id"],
                    scenario=row["scenario"],
                    quality_score=row["quality_score"],
                    latency_score=row["latency_score"],
                    cost_score=row["cost_score"],
                    satisfaction_score=row["satisfaction_score"],
                    sample_count=row["sample_count"],
                    last_updated=datetime.fromisoformat(row["last_updated"])
                    if row["last_updated"] else None,
                )
                for row in rows
            ]

    async def update_score(self, score: ModelScore):
        """Update or insert a score record."""
        async with self._lock:
            db = await self._get_db()
            await db.execute(
                """
                INSERT INTO model_scores
                    (model_id, scenario, quality_score, latency_score, cost_score,
                     satisfaction_score, sample_count, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(model_id, scenario)
                DO UPDATE SET
                    quality_score = excluded.quality_score,
                    latency_score = excluded.latency_score,
                    cost_score = excluded.cost_score,
                    satisfaction_score = excluded.satisfaction_score,
                    sample_count = excluded.sample_count,
                    last_updated = CURRENT_TIMESTAMP
                """,
                (
                    score.model_id,
                    score.scenario,
                    score.quality_score,
                    score.latency_score,
                    score.cost_score,
                    score.satisfaction_score,
                    score.sample_count,
                ),
            )
            await db.commit()

    async def record_execution(self, record: ExecutionRecord):
        """Record an execution for history tracking."""
        async with self._lock:
            db = await self._get_db()
            await db.execute(
                """
                INSERT INTO execution_history
                    (trace_id, model_id, scenario, task_type, latency_ms, tokens_used,
                     success, explicit_feedback, implicit_feedback, quality_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.trace_id,
                    record.model_id,
                    record.scenario,
                    record.task_type,
                    record.latency_ms,
                    record.tokens_used,
                    record.success,
                    record.explicit_feedback,
                    json.dumps(record.implicit_feedback) if record.implicit_feedback else None,
                    record.quality_score,
                ),
            )
            await db.commit()

    async def record_feedback(
        self,
        trace_id: str,
        user_id: str,
        message_id: str,
        model_id: str,
        feedback_type: str,
        rating: Optional[int] = None,
        signal_type: Optional[str] = None,
        signal_value: Optional[float] = None,
    ):
        """Record user feedback."""
        async with self._lock:
            db = await self._get_db()
            await db.execute(
                """
                INSERT INTO user_feedback
                    (trace_id, user_id, message_id, model_id, feedback_type,
                     rating, signal_type, signal_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    user_id,
                    message_id,
                    model_id,
                    feedback_type,
                    rating,
                    signal_type,
                    signal_value,
                ),
            )
            await db.commit()

    async def get_execution_stats(
        self,
        model_id: str,
        scenario: str,
        limit: int = 100,
    ) -> dict:
        """Get execution statistics for a model."""
        async with self._lock:
            db = await self._get_db()
            cursor = await db.execute(
                """
                SELECT
                    COUNT(*) as total_count,
                    AVG(latency_ms) as avg_latency,
                    AVG(tokens_used) as avg_tokens,
                    SUM(CASE WHEN success THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate,
                    AVG(explicit_feedback) as avg_feedback
                FROM execution_history
                WHERE model_id = ? AND scenario = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (model_id, scenario, limit),
            )
            row = await cursor.fetchone()

            if row and row["total_count"] > 0:
                return {
                    "total_count": row["total_count"],
                    "avg_latency_ms": row["avg_latency"] or 0,
                    "avg_tokens": row["avg_tokens"] or 0,
                    "success_rate": row["success_rate"] or 0,
                    "avg_feedback": row["avg_feedback"] or 0,
                }

            return {
                "total_count": 0,
                "avg_latency_ms": 0,
                "avg_tokens": 0,
                "success_rate": 0,
                "avg_feedback": 0,
            }


# Global score manager instance
_score_manager: Optional[ScoreManager] = None


def get_score_manager() -> ScoreManager:
    """Get or create the global score manager."""
    global _score_manager
    if _score_manager is None:
        _score_manager = ScoreManager()
    return _score_manager