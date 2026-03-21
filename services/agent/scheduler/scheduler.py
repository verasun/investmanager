"""Autonomous Scheduler - Scheduled tasks and proactive notifications."""

import asyncio
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Callable

from loguru import logger

from .triggers import Trigger, CronTrigger, IntervalTrigger, PriceTrigger, NewsTrigger
from .notifier import Notifier, get_notifier


@dataclass
class ScheduledTask:
    """A scheduled task."""

    id: str
    user_id: str
    name: str
    prompt: str
    trigger: Trigger
    enabled: bool = True
    notify_on_complete: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "prompt": self.prompt,
            "trigger_type": self.trigger.trigger_type.value,
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
        }


class AutonomousScheduler:
    """Scheduler for autonomous tasks.

    Supports:
    - Cron-based scheduling
    - Interval-based scheduling
    - Price-based triggers
    - News-based triggers
    - Proactive notifications
    """

    def __init__(
        self,
        agent_service=None,
        db_path: str = None,
        check_interval: int = 60,
    ):
        """Initialize scheduler.

        Args:
            agent_service: Agent service to execute tasks
            db_path: Path to SQLite database for tasks
            check_interval: Interval to check for due tasks (seconds)
        """
        self.agent_service = agent_service
        self.db_path = db_path or str(Path("/tmp/agent_scheduler.db"))
        self.check_interval = check_interval
        self.notifier = get_notifier()

        self._running = False
        self._tasks: dict[str, ScheduledTask] = {}
        self._task: Optional[asyncio.Task] = None

        self._ensure_tables()

    def set_agent_service(self, service) -> None:
        """Set agent service."""
        self.agent_service = service

    def _ensure_tables(self) -> None:
        """Ensure database tables exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    name TEXT,
                    prompt TEXT,
                    trigger_type TEXT,
                    trigger_config JSON,
                    enabled INTEGER,
                    notify_on_complete INTEGER,
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    run_count INTEGER,
                    created_at TIMESTAMP
                )
            """)

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        await self._load_tasks()

        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Scheduler started, check interval: {self.check_interval}s")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _load_tasks(self) -> None:
        """Load scheduled tasks from database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM scheduled_tasks WHERE enabled = 1")
            for row in cursor.fetchall():
                import json
                trigger_config = json.loads(row["trigger_config"])
                trigger_type = row["trigger_type"]

                # Reconstruct trigger
                trigger = self._create_trigger(trigger_type, trigger_config)

                task = ScheduledTask(
                    id=row["id"],
                    user_id=row["user_id"],
                    name=row["name"],
                    prompt=row["prompt"],
                    trigger=trigger,
                    enabled=bool(row["enabled"]),
                    notify_on_complete=bool(row["notify_on_complete"]),
                    last_run=datetime.fromisoformat(row["last_run"]) if row["last_run"] else None,
                    run_count=row["run_count"] or 0,
                )

                self._tasks[task.id] = task
                logger.info(f"Loaded scheduled task: {task.name}")

    def _create_trigger(self, trigger_type: str, config: dict) -> Trigger:
        """Create a trigger from config."""
        if trigger_type == "cron":
            return CronTrigger(
                hour=config.get("hour", 9),
                minute=config.get("minute", 0),
                day_of_week=config.get("day_of_week", "*"),
            )
        elif trigger_type == "interval":
            return IntervalTrigger(seconds=config.get("seconds", 60))
        elif trigger_type == "price":
            return PriceTrigger(
                symbol=config.get("symbol", ""),
                target_price=config.get("target_price", 0),
                condition=config.get("condition", "above"),
            )
        elif trigger_type == "news":
            return NewsTrigger(keywords=config.get("keywords", []))
        else:
            return IntervalTrigger(seconds=3600)  # Default: hourly

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_tasks()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(self.check_interval)

    async def _check_tasks(self) -> None:
        """Check for due tasks and execute them."""
        now = datetime.now()

        for task_id, task in list(self._tasks.items()):
            if not task.enabled:
                continue

            next_run = task.trigger.get_next_fire_time(task.last_run)

            if next_run and next_run <= now:
                logger.info(f"Executing scheduled task: {task.name}")
                await self._execute_task(task)

    async def _execute_task(self, task: ScheduledTask) -> None:
        """Execute a scheduled task."""
        if not self.agent_service:
            logger.warning("No agent service configured")
            return

        try:
            result = await self.agent_service.run(
                user_request=task.prompt,
                user_id=task.user_id,
            )

            # Update task
            task.last_run = datetime.now()
            task.run_count += 1

            # Notify if configured
            if task.notify_on_complete:
                await self.notifier.send_task_result(
                    user_id=task.user_id,
                    task_name=task.name,
                    result=result.output[:500] if result.output else "完成",
                    success=result.success,
                )

            # Save to database
            await self._save_task(task)

        except Exception as e:
            logger.error(f"Task execution failed: {e}")

    async def _save_task(self, task: ScheduledTask) -> None:
        """Save task to database."""
        import json

        trigger_config = {}
        if isinstance(task.trigger, CronTrigger):
            trigger_config = {
                "hour": task.trigger.hour,
                "minute": task.trigger.minute,
                "day_of_week": task.trigger.day_of_week,
            }
        elif isinstance(task.trigger, IntervalTrigger):
            trigger_config = {"seconds": task.trigger.seconds}
        elif isinstance(task.trigger, PriceTrigger):
            trigger_config = {
                "symbol": task.trigger.symbol,
                "target_price": task.trigger.target_price,
                "condition": task.trigger.condition,
            }
        elif isinstance(task.trigger, NewsTrigger):
            trigger_config = {"keywords": task.trigger.keywords}

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO scheduled_tasks
                (id, user_id, name, prompt, trigger_type, trigger_config,
                 enabled, notify_on_complete, last_run, next_run, run_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id,
                task.user_id,
                task.name,
                task.prompt,
                task.trigger.trigger_type.value,
                json.dumps(trigger_config),
                1 if task.enabled else 0,
                1 if task.notify_on_complete else 0,
                task.last_run.isoformat() if task.last_run else None,
                task.next_run.isoformat() if task.next_run else None,
                task.run_count,
                task.created_at.isoformat(),
            ))

    async def create_task(
        self,
        user_id: str,
        name: str,
        prompt: str,
        trigger: Trigger,
        notify_on_complete: bool = True,
    ) -> ScheduledTask:
        """Create a new scheduled task.

        Args:
            user_id: User ID
            name: Task name
            prompt: Task prompt
            trigger: Trigger configuration
            notify_on_complete: Whether to notify on completion

        Returns:
            Created ScheduledTask
        """
        task = ScheduledTask(
            id=f"task_{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            name=name,
            prompt=prompt,
            trigger=trigger,
            notify_on_complete=notify_on_complete,
            next_run=trigger.get_next_fire_time(),
        )

        self._tasks[task.id] = task
        await self._save_task(task)

        logger.info(f"Created scheduled task: {name}")
        return task

    async def delete_task(self, task_id: str) -> bool:
        """Delete a scheduled task.

        Args:
            task_id: Task ID to delete

        Returns:
            True if deleted
        """
        if task_id in self._tasks:
            del self._tasks[task_id]

            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))

            logger.info(f"Deleted scheduled task: {task_id}")
            return True
        return False

    async def list_tasks(self, user_id: str = None) -> list[ScheduledTask]:
        """List scheduled tasks.

        Args:
            user_id: Optional user ID filter

        Returns:
            List of ScheduledTask
        """
        if user_id:
            return [t for t in self._tasks.values() if t.user_id == user_id]
        return list(self._tasks.values())


# Global scheduler instance
_scheduler: Optional[AutonomousScheduler] = None


def get_scheduler() -> AutonomousScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AutonomousScheduler()
    return _scheduler