"""Task runner using subprocess for isolated execution."""

import json
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from src.orchestrator.task import Task, TaskResult, TaskType


@dataclass
class RunnerConfig:
    """Configuration for task runner."""

    timeout_seconds: int = 3600  # 1 hour default timeout
    max_memory_mb: int = 512  # Memory limit (for logging)
    working_dir: Optional[Path] = None
    python_path: str = sys.executable
    env: Optional[dict] = None


class TaskRunner:
    """
    Task runner that executes tasks in isolated subprocesses.

    Each task is executed as a separate Python process,
    ensuring resource isolation and clean memory management.
    Tasks communicate via stdin/stdout using JSON.
    """

    # Mapping of task types to their node modules
    NODE_MODULES = {
        TaskType.DATA_FETCH: "src.orchestrator.nodes.data_fetch",
        TaskType.ANALYSIS: "src.orchestrator.nodes.analysis",
        TaskType.BACKTEST: "src.orchestrator.nodes.backtest",
        TaskType.REPORT: "src.orchestrator.nodes.report",
        TaskType.EMAIL: "src.orchestrator.nodes.email",
    }

    def __init__(self, config: Optional[RunnerConfig] = None):
        """
        Initialize the task runner.

        Args:
            config: Runner configuration
        """
        self.config = config or RunnerConfig()
        self._current_process: Optional[subprocess.Popen] = None
        logger.info(f"TaskRunner initialized with timeout={self.config.timeout_seconds}s")

    def run_task(self, task: Task) -> TaskResult:
        """
        Execute a task in a subprocess.

        Args:
            task: Task to execute

        Returns:
            TaskResult with execution outcome
        """
        start_time = time.time()
        logger.info(f"Starting task: {task.id} ({task.type.value})")

        try:
            # Get the node module for this task type
            node_module = self.NODE_MODULES.get(task.type)
            if not node_module:
                raise ValueError(f"No node module for task type: {task.type}")

            # Prepare input data
            input_data = {
                "task_id": task.id,
                "task_type": task.type.value,
                "input": task.input,
                "metadata": task.metadata,
            }

            # Build command
            cmd = [
                self.config.python_path,
                "-m", node_module,
            ]

            # Set working directory
            cwd = self.config.working_dir or Path.cwd()

            # Prepare environment
            env = self.config.env or {}
            env.update({
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1",
            })

            # Run the subprocess
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(cwd),
                env=env,
                text=True,
            )
            self._current_process = process

            # Send input and get output
            try:
                stdout, stderr = process.communicate(
                    input=json.dumps(input_data),
                    timeout=self.config.timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                raise TimeoutError(
                    f"Task {task.id} timed out after {self.config.timeout_seconds}s"
                )

            # Check return code
            if process.returncode != 0:
                error_msg = stderr.strip() or f"Process exited with code {process.returncode}"
                logger.error(f"Task {task.id} failed: {error_msg}")
                return TaskResult(
                    task_id=task.id,
                    success=False,
                    error=error_msg,
                    execution_time=time.time() - start_time,
                )

            # Parse output
            try:
                output_data = json.loads(stdout.strip())
                result = TaskResult(
                    task_id=task.id,
                    success=output_data.get("success", True),
                    output=output_data.get("output"),
                    error=output_data.get("error"),
                    execution_time=time.time() - start_time,
                    artifacts=output_data.get("artifacts", []),
                )
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse task output: {e}")
                logger.debug(f"Raw stdout: {stdout[:500]}")
                return TaskResult(
                    task_id=task.id,
                    success=False,
                    error=f"Invalid output format: {str(e)}",
                    execution_time=time.time() - start_time,
                )

            logger.info(
                f"Task {task.id} completed in {result.execution_time:.2f}s "
                f"(success={result.success})"
            )
            return result

        except Exception as e:
            logger.exception(f"Task {task.id} failed with exception")
            return TaskResult(
                task_id=task.id,
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                execution_time=time.time() - start_time,
            )

        finally:
            self._current_process = None

    def cancel_current(self) -> bool:
        """
        Cancel the currently running task.

        Returns:
            True if a task was cancelled
        """
        if self._current_process:
            logger.warning("Cancelling current task...")
            self._current_process.terminate()
            try:
                self._current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._current_process.kill()
            return True
        return False

    def run_task_sync(self, task: Task) -> TaskResult:
        """
        Execute a task synchronously (in the same process).

        This is useful for lightweight tasks that don't need
        process isolation, or for testing.

        Args:
            task: Task to execute

        Returns:
            TaskResult with execution outcome
        """
        start_time = time.time()

        try:
            # Import the appropriate node
            if task.type == TaskType.DATA_FETCH:
                from src.orchestrator.nodes.data_fetch import DataFetchNode
                node = DataFetchNode()
            elif task.type == TaskType.ANALYSIS:
                from src.orchestrator.nodes.analysis import AnalysisNode
                node = AnalysisNode()
            elif task.type == TaskType.BACKTEST:
                from src.orchestrator.nodes.backtest import BacktestNode
                node = BacktestNode()
            elif task.type == TaskType.REPORT:
                from src.orchestrator.nodes.report import ReportNode
                node = ReportNode()
            elif task.type == TaskType.EMAIL:
                from src.orchestrator.nodes.email import EmailNode
                node = EmailNode()
            else:
                raise ValueError(f"Unknown task type: {task.type}")

            # Execute
            output = node.execute(task.input)

            return TaskResult(
                task_id=task.id,
                success=True,
                output=output,
                execution_time=time.time() - start_time,
                artifacts=output.get("artifacts", []) if output else [],
            )

        except Exception as e:
            logger.exception(f"Task {task.id} failed")
            return TaskResult(
                task_id=task.id,
                success=False,
                error=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}",
                execution_time=time.time() - start_time,
            )


class TaskRunnerPool:
    """
    A pool of task runners for parallel execution.

    Note: Given the resource constraints (2 cores, 2GB RAM),
    this should be used sparingly. Maximum recommended workers: 2.
    """

    def __init__(self, max_workers: int = 1):
        """
        Initialize the runner pool.

        Args:
            max_workers: Maximum concurrent tasks (recommend 1-2)
        """
        self.max_workers = max_workers
        self.runners = [TaskRunner() for _ in range(max_workers)]
        self._active = 0

    @property
    def available(self) -> bool:
        """Check if any runner is available."""
        return self._active < self.max_workers

    def get_runner(self) -> Optional[TaskRunner]:
        """
        Get an available runner.

        Returns:
            TaskRunner if available, None otherwise
        """
        if self.available:
            self._active += 1
            return self.runners[self._active - 1]
        return None

    def release_runner(self, runner: TaskRunner) -> None:
        """Release a runner back to the pool."""
        idx = self.runners.index(runner)
        if idx < self._active:
            self._active -= 1
            # Swap with the last active runner
            if idx != self._active:
                self.runners[idx], self.runners[self._active] = \
                    self.runners[self._active], self.runners[idx]