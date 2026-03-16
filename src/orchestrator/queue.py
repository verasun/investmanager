"""SQLite-based persistent task queue."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from src.orchestrator.task import Task, TaskPriority, TaskStatus, TaskType


class TaskQueue:
    """
    Persistent task queue using SQLite.

    Provides a lightweight, reliable queue with:
    - Task persistence across restarts
    - Priority-based ordering
    - Dependency tracking
    - Status management
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the task queue.

        Args:
            db_path: Path to SQLite database file.
                     Defaults to data/tasks.db
        """
        if db_path is None:
            db_path = Path("data/tasks.db")

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()
        logger.info(f"TaskQueue initialized with database: {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Get a database connection with context management."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Tasks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    input TEXT NOT NULL,
                    dependencies TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 5,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    output TEXT,
                    error TEXT,
                    tags TEXT,
                    metadata TEXT
                )
            """)

            # Index for efficient status queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status
                ON tasks(status)
            """)

            # Index for priority ordering
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_priority_status
                ON tasks(priority DESC, created_at ASC)
                WHERE status IN ('pending', 'queued', 'retrying')
            """)

    def enqueue(self, task: Task) -> str:
        """
        Add a task to the queue.

        Args:
            task: Task to enqueue

        Returns:
            Task ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO tasks (
                    id, name, type, description, input, dependencies,
                    status, priority, retry_count, max_retries,
                    created_at, started_at, completed_at, output, error,
                    tags, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id,
                task.name,
                task.type.value,
                task.description,
                json.dumps(task.input),
                json.dumps(task.dependencies),
                task.status.value,
                task.priority.value,
                task.retry_count,
                task.max_retries,
                task.created_at.isoformat(),
                task.started_at.isoformat() if task.started_at else None,
                task.completed_at.isoformat() if task.completed_at else None,
                json.dumps(task.output) if task.output else None,
                task.error,
                json.dumps(task.tags),
                json.dumps(task.metadata),
            ))

        logger.info(f"Enqueued task: {task.id} ({task.type.value})")
        return task.id

    def get_next(self) -> Optional[Task]:
        """
        Get the next task to execute.

        Returns the highest priority task that:
        - Is in pending/queued/retrying status
        - Has all dependencies completed

        Returns:
            Next task to execute, or None if no tasks available
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Get tasks that are ready to run
            cursor.execute("""
                SELECT * FROM tasks
                WHERE status IN ('pending', 'queued', 'retrying')
                ORDER BY priority DESC, created_at ASC
                LIMIT 20
            """)

            rows = cursor.fetchall()

            for row in rows:
                task = self._row_to_task(row)

                # Check dependencies
                if self._dependencies_satisfied(conn, task):
                    return task

        return None

    def _dependencies_satisfied(self, conn: sqlite3.Connection, task: Task) -> bool:
        """Check if all dependencies are completed."""
        if not task.dependencies:
            return True

        cursor = conn.cursor()
        placeholders = ",".join("?" * len(task.dependencies))
        cursor.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE id IN ({placeholders})
            AND status = 'completed'
        """, task.dependencies)

        count = cursor.fetchone()[0]
        return count == len(task.dependencies)

    def get_by_id(self, task_id: str) -> Optional[Task]:
        """
        Get a task by ID.

        Args:
            task_id: Task identifier

        Returns:
            Task if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_task(row)
            return None

    def get_by_status(self, status: TaskStatus) -> list[Task]:
        """
        Get all tasks with a specific status.

        Args:
            status: Task status to filter by

        Returns:
            List of matching tasks
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC",
                (status.value,)
            )
            rows = cursor.fetchall()
            return [self._row_to_task(row) for row in rows]

    def get_all(self, limit: int = 100, offset: int = 0) -> list[Task]:
        """
        Get all tasks with pagination.

        Args:
            limit: Maximum number of tasks to return
            offset: Offset for pagination

        Returns:
            List of tasks
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = cursor.fetchall()
            return [self._row_to_task(row) for row in rows]

    def count(self, status: Optional[TaskStatus] = None) -> int:
        """
        Count tasks, optionally filtered by status.

        Args:
            status: Optional status filter

        Returns:
            Number of tasks
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status = ?",
                    (status.value,)
                )
            else:
                cursor.execute("SELECT COUNT(*) FROM tasks")
            return cursor.fetchone()[0]

    def mark_running(self, task_id: str) -> bool:
        """
        Mark a task as running.

        Args:
            task_id: Task identifier

        Returns:
            True if updated successfully
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET status = 'running', started_at = ?
                WHERE id = ? AND status IN ('pending', 'queued', 'retrying')
            """, (datetime.now().isoformat(), task_id))
            return cursor.rowcount > 0

    def mark_completed(self, task_id: str, output: Optional[dict] = None) -> bool:
        """
        Mark a task as completed.

        Args:
            task_id: Task identifier
            output: Optional output data

        Returns:
            True if updated successfully
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET status = 'completed', completed_at = ?, output = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), json.dumps(output) if output else None, task_id))
            return cursor.rowcount > 0

    def mark_failed(self, task_id: str, error: str, retry: bool = True) -> bool:
        """
        Mark a task as failed.

        Args:
            task_id: Task identifier
            error: Error message
            retry: Whether to allow retry

        Returns:
            True if updated successfully
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Get current retry count
            cursor.execute(
                "SELECT retry_count, max_retries FROM tasks WHERE id = ?",
                (task_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False

            retry_count = row["retry_count"]
            max_retries = row["max_retries"]

            if retry and retry_count < max_retries:
                # Increment retry count and set status to retrying
                new_status = "retrying"
                new_retry_count = retry_count + 1
            else:
                new_status = "failed"
                new_retry_count = retry_count

            cursor.execute("""
                UPDATE tasks
                SET status = ?, error = ?, completed_at = ?, retry_count = ?
                WHERE id = ?
            """, (new_status, error, datetime.now().isoformat(), new_retry_count, task_id))
            return cursor.rowcount > 0

    def cancel(self, task_id: str) -> bool:
        """
        Cancel a pending or queued task.

        Args:
            task_id: Task identifier

        Returns:
            True if cancelled successfully
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET status = 'cancelled', completed_at = ?
                WHERE id = ? AND status IN ('pending', 'queued')
            """, (datetime.now().isoformat(), task_id))
            return cursor.rowcount > 0

    def retry(self, task_id: str) -> bool:
        """
        Manually retry a failed or retrying task.

        Args:
            task_id: Task identifier

        Returns:
            True if retry scheduled successfully
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET status = 'pending', error = NULL, completed_at = NULL,
                    retry_count = retry_count + 1
                WHERE id = ? AND status IN ('failed', 'retrying')
            """, (task_id,))
            return cursor.rowcount > 0

    def cleanup_completed(self, days: int = 7) -> int:
        """
        Remove completed tasks older than specified days.

        Args:
            days: Number of days to keep completed tasks

        Returns:
            Number of tasks removed
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cutoff = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # Simple date subtraction
            import datetime as dt
            cutoff = cutoff - dt.timedelta(days=days)

            cursor.execute("""
                DELETE FROM tasks
                WHERE status IN ('completed', 'cancelled')
                AND completed_at < ?
            """, (cutoff.isoformat(),))
            deleted = cursor.rowcount

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old completed tasks")

        return deleted

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        """Convert a database row to a Task object."""
        return Task(
            id=row["id"],
            name=row["name"],
            type=TaskType(row["type"]),
            description=row["description"],
            input=json.loads(row["input"]),
            dependencies=json.loads(row["dependencies"]) if row["dependencies"] else [],
            status=TaskStatus(row["status"]),
            priority=TaskPriority(row["priority"]),
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            output=json.loads(row["output"]) if row["output"] else None,
            error=row["error"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )