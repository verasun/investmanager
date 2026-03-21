"""Agent Memory - Task history and pattern learning."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger


class AgentMemory:
    """Memory system for the agent.

    Provides:
    - Task history storage
    - Execution trace tracking
    - Pattern learning
    """

    def __init__(self, db_path: str = None):
        """Initialize agent memory.

        Args:
            db_path: Path to SQLite database
        """
        if db_path is None:
            from config.settings import settings
            db_path = str(settings.sqlite_path).replace(
                "investmanager.db",
                "agent_memory.db"
            )

        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure database tables exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- Task history
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    goal TEXT,
                    plan JSON,
                    status TEXT,
                    result JSON,
                    success INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                );

                -- Execution traces
                CREATE TABLE IF NOT EXISTS agent_traces (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    step_id TEXT,
                    tool_name TEXT,
                    parameters JSON,
                    result JSON,
                    duration_ms INTEGER,
                    success INTEGER,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES agent_tasks(id)
                );

                -- Learned patterns
                CREATE TABLE IF NOT EXISTS agent_patterns (
                    id TEXT PRIMARY KEY,
                    pattern_type TEXT,
                    pattern_key TEXT,
                    pattern_data JSON,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    last_used TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Create indexes
                CREATE INDEX IF NOT EXISTS idx_tasks_user ON agent_tasks(user_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON agent_tasks(status);
                CREATE INDEX IF NOT EXISTS idx_traces_task ON agent_traces(task_id);
                CREATE INDEX IF NOT EXISTS idx_patterns_type ON agent_patterns(pattern_type);
            """)

    async def save_task(
        self,
        task_id: str,
        user_id: str,
        goal: str,
        plan: dict,
        status: str,
        result: dict = None,
        success: bool = None,
    ) -> None:
        """Save a task to history."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO agent_tasks
                (id, user_id, goal, plan, status, result, success, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id,
                user_id,
                goal,
                json.dumps(plan, ensure_ascii=False),
                status,
                json.dumps(result, ensure_ascii=False) if result else None,
                1 if success else 0 if success is False else None,
                datetime.now().isoformat() if status == "completed" else None,
            ))

    async def save_trace(
        self,
        trace_id: str,
        task_id: str,
        step_id: str,
        tool_name: str,
        parameters: dict,
        result: dict,
        duration_ms: int,
        success: bool,
        error: str = None,
    ) -> None:
        """Save an execution trace."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO agent_traces
                (id, task_id, step_id, tool_name, parameters, result, duration_ms, success, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id,
                task_id,
                step_id,
                tool_name,
                json.dumps(parameters, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False) if result else None,
                duration_ms,
                1 if success else 0,
                error,
            ))

    async def save_pattern(
        self,
        pattern_type: str,
        pattern_key: str,
        pattern_data: dict,
    ) -> None:
        """Save or update a learned pattern."""
        with sqlite3.connect(self.db_path) as conn:
            # Check if exists
            cursor = conn.execute(
                "SELECT id, success_count, failure_count FROM agent_patterns WHERE pattern_key = ?",
                (pattern_key,)
            )
            row = cursor.fetchone()

            if row:
                # Update
                conn.execute("""
                    UPDATE agent_patterns
                    SET pattern_data = ?, last_used = ?
                    WHERE pattern_key = ?
                """, (json.dumps(pattern_data, ensure_ascii=False), datetime.now().isoformat(), pattern_key))
            else:
                # Insert
                import uuid
                conn.execute("""
                    INSERT INTO agent_patterns
                    (id, pattern_type, pattern_key, pattern_data, last_used)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    f"pattern_{uuid.uuid4().hex[:8]}",
                    pattern_type,
                    pattern_key,
                    json.dumps(pattern_data, ensure_ascii=False),
                    datetime.now().isoformat(),
                ))

    async def get_task(self, task_id: str) -> Optional[dict]:
        """Get a task by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM agent_tasks WHERE id = ?",
                (task_id,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def get_user_tasks(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Get tasks for a user."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM agent_tasks
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    async def get_task_traces(self, task_id: str) -> list[dict]:
        """Get traces for a task."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM agent_traces
                WHERE task_id = ?
                ORDER BY created_at
            """, (task_id,))
            return [dict(row) for row in cursor.fetchall()]

    async def find_relevant_patterns(
        self,
        query: str,
        pattern_type: str = None,
        limit: int = 5,
    ) -> list[dict]:
        """Find patterns relevant to a query."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            sql = """
                SELECT * FROM agent_patterns
                WHERE success_count > failure_count
            """
            params = []

            if pattern_type:
                sql += " AND pattern_type = ?"
                params.append(pattern_type)

            # Simple keyword matching
            sql += " ORDER BY (success_count - failure_count) DESC, last_used DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(sql, params)
            patterns = [dict(row) for row in cursor.fetchall()]

            # Further filter by query keywords
            if query:
                query_words = set(query.lower().split())
                filtered = []
                for p in patterns:
                    pattern_data = json.loads(p.get("pattern_data", "{}"))
                    pattern_text = json.dumps(pattern_data, ensure_ascii=False).lower()
                    if any(word in pattern_text for word in query_words):
                        filtered.append(p)
                return filtered

            return patterns

    async def record_pattern_success(self, pattern_key: str) -> None:
        """Record a successful use of a pattern."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE agent_patterns
                SET success_count = success_count + 1, last_used = ?
                WHERE pattern_key = ?
            """, (datetime.now().isoformat(), pattern_key))

    async def record_pattern_failure(self, pattern_key: str) -> None:
        """Record a failed use of a pattern."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE agent_patterns
                SET failure_count = failure_count + 1, last_used = ?
                WHERE pattern_key = ?
            """, (datetime.now().isoformat(), pattern_key))

    async def learn_from_execution(
        self,
        plan: dict,
        result: dict,
        success: bool,
    ) -> None:
        """Learn patterns from execution results."""
        # Extract task template pattern
        goal = plan.get("goal", "")
        steps = plan.get("steps", [])

        if goal and steps:
            # Create a simple pattern key from goal keywords
            import re
            keywords = re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", goal)
            pattern_key = "_".join(keywords[:3]) if keywords else f"task_{hash(goal) % 10000}"

            # Extract step sequence pattern
            tool_sequence = [s.get("tool_name") for s in steps if s.get("tool_name")]
            pattern_data = {
                "goal_keywords": keywords[:5],
                "tool_sequence": tool_sequence,
                "step_count": len(steps),
            }

            await self.save_pattern("task_template", pattern_key, pattern_data)

            if success:
                await self.record_pattern_success(pattern_key)
            else:
                await self.record_pattern_failure(pattern_key)


# Global memory instance
_memory: Optional[AgentMemory] = None


def get_agent_memory() -> AgentMemory:
    """Get or create the global agent memory instance."""
    global _memory
    if _memory is None:
        _memory = AgentMemory()
    return _memory