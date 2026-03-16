"""Logging configuration for InvestManager."""

import sys
from pathlib import Path

from loguru import logger

from config.settings import settings


def setup_logging() -> None:
    """Configure loguru logger with application settings."""
    # Remove default handler
    logger.remove()

    # Console handler with color
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.log_level,
        colorize=True,
        backtrace=True,
        diagnose=settings.is_development,
    )

    # File handler for all logs
    log_path = Path("logs")
    log_path.mkdir(exist_ok=True)

    logger.add(
        log_path / "investmanager_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level=settings.log_level,
        rotation="00:00",  # Rotate at midnight
        retention="30 days",
        compression="zip",
        backtrace=True,
        diagnose=settings.is_development,
    )

    # Separate file for errors
    logger.add(
        log_path / "error_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="ERROR",
        rotation="00:00",
        retention="90 days",
        compression="zip",
        backtrace=True,
        diagnose=True,
    )

    logger.info(f"Logging configured for {settings.app_env} environment")