#!/usr/bin/env python
"""Main entry point for the Task Orchestrator.

This module provides the orchestrator service that runs as a background
process, managing task execution for the InvestManager system.

Usage:
    python -m src.orchestrator.main [OPTIONS]

Options:
    --db-path PATH       Path to SQLite database (default: data/tasks.db)
    --poll-interval N    Polling interval in seconds (default: 5)
    --timeout N          Task timeout in seconds (default: 3600)
    --daemon             Run as a daemon process
    --pid-file PATH      PID file for daemon mode
"""

import argparse
import os
import sys
from pathlib import Path

from loguru import logger


def setup_logging(log_dir: Path = Path("logs")) -> None:
    """Configure logging for the orchestrator."""
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Console handler
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
    )

    # File handler
    logger.add(
        log_dir / "orchestrator.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Task Orchestrator for InvestManager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/tasks.db"),
        help="Path to SQLite database for task queue",
    )

    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Polling interval in seconds when idle",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="Task execution timeout in seconds",
    )

    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as a daemon process",
    )

    parser.add_argument(
        "--pid-file",
        type=Path,
        default=Path("data/orchestrator.pid"),
        help="PID file for daemon mode",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )

    return parser.parse_args()


def write_pid_file(pid_file: Path) -> None:
    """Write PID file for daemon mode."""
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))


def remove_pid_file(pid_file: Path) -> None:
    """Remove PID file on exit."""
    if pid_file.exists():
        pid_file.unlink()


def main():
    """Main entry point."""
    args = parse_args()

    # Setup logging
    setup_logging()

    logger.info("=" * 60)
    logger.info("Task Orchestrator Starting")
    logger.info("=" * 60)
    logger.info(f"Database: {args.db_path}")
    logger.info(f"Poll interval: {args.poll_interval}s")
    logger.info(f"Task timeout: {args.timeout}s")

    # Import after logging is configured
    from src.orchestrator.core import TaskOrchestrator
    from src.orchestrator.runner import RunnerConfig

    # Create runner config
    runner_config = RunnerConfig(
        timeout_seconds=args.timeout,
    )

    # Create orchestrator
    orchestrator = TaskOrchestrator(
        db_path=args.db_path,
        runner_config=runner_config,
        poll_interval=args.poll_interval,
    )

    # Handle daemon mode
    if args.daemon:
        write_pid_file(args.pid_file)
        logger.info(f"Running as daemon with PID {os.getpid()}")

    try:
        # Start the orchestrator
        logger.info("Starting orchestrator main loop...")
        orchestrator.start()

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
        orchestrator.stop()

    except Exception as e:
        logger.exception(f"Orchestrator error: {e}")
        sys.exit(1)

    finally:
        if args.daemon:
            remove_pid_file(args.pid_file)

    logger.info("Orchestrator stopped")


if __name__ == "__main__":
    main()