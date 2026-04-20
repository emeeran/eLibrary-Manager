"""Centralized logging configuration."""

import logging
import sys
from typing import Literal

from app.config import get_config


def setup_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] | None = None,
    log_file: str | None = None
) -> None:
    """Configure application logging with consistent formatting.

    Args:
        level: Logging level (defaults to config)
        log_file: Optional file path for log output

    Example:
        >>> setup_logging("DEBUG", "dawnstar.log")
    """
    config = get_config()
    log_level = level or config.log_level

    # Define format
    format_str = (
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
    )
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure handlers
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout)
    ]

    if log_file:
        from pathlib import Path

        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.FileHandler(log_file, encoding="utf-8")
        )

    # Apply configuration
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=format_str,
        datefmt=date_format,
        handlers=handlers,
        force=True  # Override any existing config
    )

    # Set specific log levels for noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Application started")
    """
    return logging.getLogger(name)
