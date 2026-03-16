"""Main task orchestrator for managing task execution."""

import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from src.orchestrator.queue import TaskQueue
from src.orchestrator.runner import TaskRunner, RunnerConfig
from src.orchestrator.task import Task, TaskStatus, TaskType


class TaskOrchestrator:
    """
    Lightweight task orchestrator for resource-constrained environments.

    Features:
    - Single-threaded sequential task execution
    - SQLite-backed persistent task queue
    - Automatic retry with configurable max retries
    - Graceful shutdown handling
    - Task dependency resolution
    - Recovery from crashes

    Designed for servers with limited resources (2 cores, 2GB RAM).
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        runner_config: Optional[RunnerConfig] = None,
        poll_interval: float = 5.0,
        register_signals: bool = True,
    ):
        """
        Initialize the task orchestrator.

        Args:
            db_path: Path to SQLite database for task queue
            runner_config: Configuration for task runner
            poll_interval: Seconds to wait between queue polls when idle
            register_signals: Whether to register signal handlers (disable for testing)
        """
        self.task_queue = TaskQueue(db_path)
        self.task_runner = TaskRunner(runner_config)
        self.poll_interval = poll_interval

        self._running = False
        self._current_task: Optional[Task] = None
        self._shutdown_requested = False

        # Register signal handlers only in main thread
        if register_signals:
            try:
                signal.signal(signal.SIGINT, self._handle_shutdown)
                signal.signal(signal.SIGTERM, self._handle_shutdown)
            except ValueError:
                # Signal handling only works in main thread
                pass

        logger.info("TaskOrchestrator initialized")

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.warning(f"Received signal {signum}, initiating graceful shutdown...")
        self._shutdown_requested = True

        # Cancel current task if running
        if self._current_task:
            self.task_runner.cancel_current()

    def start(self) -> None:
        """
        Start the orchestrator main loop.

        This will run indefinitely until shutdown is requested.
        """
        if self._running:
            logger.warning("Orchestrator is already running")
            return

        self._running = True
        logger.info("TaskOrchestrator started")

        # Recover any interrupted tasks
        self._recover_interrupted_tasks()

        try:
            while self._running and not self._shutdown_requested:
                self._tick()
                time.sleep(self.poll_interval)
        except Exception as e:
            logger.exception(f"Orchestrator error: {e}")
            raise
        finally:
            self._running = False
            logger.info("TaskOrchestrator stopped")

    def stop(self) -> None:
        """Request the orchestrator to stop."""
        logger.info("Stop requested")
        self._shutdown_requested = True

    def _tick(self) -> None:
        """
        Single iteration of the main loop.

        Gets the next task, executes it, and updates status.
        """
        # Get next task
        task = self.task_queue.get_next()

        if task is None:
            # No tasks available, idle
            return

        self._current_task = task

        try:
            # Mark as running
            self.task_queue.mark_running(task.id)

            # Execute the task
            result = self.task_runner.run_task(task)

            # Update status based on result
            if result.success:
                self.task_queue.mark_completed(task.id, result.output)
                logger.info(
                    f"Task {task.id} completed successfully in "
                    f"{result.execution_time:.2f}s"
                )
            else:
                self.task_queue.mark_failed(
                    task.id,
                    result.error or "Unknown error",
                    retry=task.can_retry()
                )
                if task.can_retry():
                    logger.warning(
                        f"Task {task.id} failed, will retry "
                        f"({task.retry_count + 1}/{task.max_retries})"
                    )
                else:
                    logger.error(f"Task {task.id} failed permanently: {result.error}")

        except Exception as e:
            logger.exception(f"Error executing task {task.id}")
            self.task_queue.mark_failed(task.id, str(e), retry=False)

        finally:
            self._current_task = None

    def _recover_interrupted_tasks(self) -> None:
        """
        Recover tasks that were interrupted by a crash.

        Sets 'running' tasks back to 'pending' so they can be retried.
        """
        running_tasks = self.task_queue.get_by_status(TaskStatus.RUNNING)
        retrying_tasks = self.task_queue.get_by_status(TaskStatus.RETRYING)

        for task in running_tasks:
            logger.info(f"Recovering interrupted task: {task.id}")
            task.status = TaskStatus.PENDING
            task.retry_count += 1
            if task.can_retry():
                self.task_queue.mark_failed(
                    task.id,
                    "Task interrupted by system restart",
                    retry=True
                )
            else:
                self.task_queue.mark_failed(
                    task.id,
                    "Task interrupted by system restart (max retries exceeded)",
                    retry=False
                )

        for task in retrying_tasks:
            # Reset to pending for actual retry
            logger.info(f"Scheduling retry for task: {task.id}")
            self.task_queue.retry(task.id)

    # Task management methods

    def submit_task(self, task: Task) -> str:
        """
        Submit a new task to the queue.

        Args:
            task: Task to submit

        Returns:
            Task ID
        """
        return self.task_queue.enqueue(task)

    def submit_data_fetch(
        self,
        symbols: list[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Submit a data fetch task.

        Args:
            symbols: List of stock symbols
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            **kwargs: Additional task parameters

        Returns:
            Task ID
        """
        task = Task(
            type=TaskType.DATA_FETCH,
            input={
                "symbols": symbols,
                "start_date": start_date,
                "end_date": end_date,
            },
            **kwargs,
        )
        return self.submit_task(task)

    def submit_analysis(
        self,
        data_path: str,
        indicators: Optional[list[str]] = None,
        dependencies: Optional[list[str]] = None,
        **kwargs,
    ) -> str:
        """
        Submit an analysis task.

        Args:
            data_path: Path to input data
            indicators: List of indicators to calculate
            dependencies: Task IDs this task depends on
            **kwargs: Additional task parameters

        Returns:
            Task ID
        """
        task = Task(
            type=TaskType.ANALYSIS,
            input={
                "data_path": data_path,
                "indicators": indicators,
            },
            dependencies=dependencies or [],
            **kwargs,
        )
        return self.submit_task(task)

    def submit_backtest(
        self,
        strategy: str,
        data_path: str,
        config: Optional[dict] = None,
        dependencies: Optional[list[str]] = None,
        **kwargs,
    ) -> str:
        """
        Submit a backtest task.

        Args:
            strategy: Strategy name or config
            data_path: Path to input data
            config: Backtest configuration
            dependencies: Task IDs this task depends on
            **kwargs: Additional task parameters

        Returns:
            Task ID
        """
        task = Task(
            type=TaskType.BACKTEST,
            input={
                "strategy": strategy,
                "data_path": data_path,
                "config": config or {},
            },
            dependencies=dependencies or [],
            **kwargs,
        )
        return self.submit_task(task)

    def submit_report(
        self,
        report_type: str,
        data_path: str,
        output_format: str = "html",
        dependencies: Optional[list[str]] = None,
        **kwargs,
    ) -> str:
        """
        Submit a report generation task.

        Args:
            report_type: Type of report (daily, backtest, risk, etc.)
            data_path: Path to input data
            output_format: Output format (html, markdown)
            dependencies: Task IDs this task depends on
            **kwargs: Additional task parameters

        Returns:
            Task ID
        """
        task = Task(
            type=TaskType.REPORT,
            input={
                "report_type": report_type,
                "data_path": data_path,
                "output_format": output_format,
            },
            dependencies=dependencies or [],
            **kwargs,
        )
        return self.submit_task(task)

    def submit_email(
        self,
        to_addrs: list[str],
        subject: str,
        report_path: str,
        dependencies: Optional[list[str]] = None,
        **kwargs,
    ) -> str:
        """
        Submit an email task.

        Args:
            to_addrs: Recipient email addresses
            subject: Email subject
            report_path: Path to report file
            dependencies: Task IDs this task depends on
            **kwargs: Additional task parameters

        Returns:
            Task ID
        """
        task = Task(
            type=TaskType.EMAIL,
            input={
                "to_addrs": to_addrs,
                "subject": subject,
                "report_path": report_path,
            },
            dependencies=dependencies or [],
            **kwargs,
        )
        return self.submit_task(task)

    def submit_pipeline(
        self,
        symbols: list[str],
        strategies: Optional[list[str]] = None,
        email_recipients: Optional[list[str]] = None,
        **kwargs,
    ) -> list[str]:
        """
        Submit a complete analysis pipeline.

        Creates a chain of tasks: data_fetch -> analysis -> backtest -> report -> email

        Args:
            symbols: List of stock symbols
            strategies: List of strategy names to backtest
            email_recipients: Email recipients for final report
            **kwargs: Additional task parameters

        Returns:
            List of task IDs in order
        """
        task_ids = []

        # Step 1: Data fetch
        data_task_id = self.submit_data_fetch(symbols, **kwargs)
        task_ids.append(data_task_id)

        # Step 2: Analysis
        analysis_task_id = self.submit_analysis(
            data_path=f"task://{data_task_id}/output",
            dependencies=[data_task_id],
            **kwargs,
        )
        task_ids.append(analysis_task_id)

        # Step 3: Backtest (optional)
        if strategies:
            backtest_task_id = self.submit_backtest(
                strategy=",".join(strategies),
                data_path=f"task://{analysis_task_id}/output",
                dependencies=[analysis_task_id],
                **kwargs,
            )
            task_ids.append(backtest_task_id)
            report_dependency = backtest_task_id
        else:
            report_dependency = analysis_task_id

        # Step 4: Report
        report_task_id = self.submit_report(
            report_type="daily",
            data_path=f"task://{report_dependency}/output",
            dependencies=[report_dependency],
            **kwargs,
        )
        task_ids.append(report_task_id)

        # Step 5: Email (optional)
        if email_recipients:
            email_task_id = self.submit_email(
                to_addrs=email_recipients,
                subject="Daily Report",
                report_path=f"task://{report_task_id}/output",
                dependencies=[report_task_id],
                **kwargs,
            )
            task_ids.append(email_task_id)

        return task_ids

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """
        Get the status of a task.

        Args:
            task_id: Task identifier

        Returns:
            Task status dict or None if not found
        """
        task = self.task_queue.get_by_id(task_id)
        if task:
            return task.to_dict()
        return None

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task.

        Args:
            task_id: Task identifier

        Returns:
            True if cancelled successfully
        """
        return self.task_queue.cancel(task_id)

    def retry_task(self, task_id: str) -> bool:
        """
        Retry a failed task.

        Args:
            task_id: Task identifier

        Returns:
            True if retry scheduled successfully
        """
        return self.task_queue.retry(task_id)

    def get_stats(self) -> dict:
        """
        Get orchestrator statistics.

        Returns:
            Dictionary with queue statistics
        """
        return {
            "running": self._running,
            "current_task": self._current_task.id if self._current_task else None,
            "queue_size": {
                "pending": self.task_queue.count(TaskStatus.PENDING),
                "running": self.task_queue.count(TaskStatus.RUNNING),
                "completed": self.task_queue.count(TaskStatus.COMPLETED),
                "failed": self.task_queue.count(TaskStatus.FAILED),
                "retrying": self.task_queue.count(TaskStatus.RETRYING),
            },
        }


def main():
    """Main entry point for running the orchestrator."""
    import argparse

    parser = argparse.ArgumentParser(description="Task Orchestrator")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/tasks.db"),
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Polling interval in seconds",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="Task timeout in seconds",
    )

    args = parser.parse_args()

    # Configure logging
    logger.add(
        "logs/orchestrator.log",
        rotation="10 MB",
        retention="7 days",
        level="INFO",
    )

    # Create and start orchestrator
    orchestrator = TaskOrchestrator(
        db_path=args.db_path,
        runner_config=RunnerConfig(timeout_seconds=args.timeout),
        poll_interval=args.poll_interval,
    )

    logger.info("Starting TaskOrchestrator...")
    orchestrator.start()


if __name__ == "__main__":
    main()