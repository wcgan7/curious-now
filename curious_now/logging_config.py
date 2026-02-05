"""Structured logging configuration.

This module provides JSON-structured logging configuration for the
Curious Now application.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields from the record
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "message",
                "thread",
                "threadName",
                "taskName",
            ):
                log_entry[key] = value

        return json.dumps(log_entry, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Standard text formatter with timestamps."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def setup_logging(
    log_format: str = "json",
    log_level: str = "INFO",
) -> None:
    """
    Configure application logging.

    Args:
        log_format: "json" for structured logging, "text" for standard format
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Convert level string to logging constant
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create formatter based on format type
    if log_format.lower() == "json":
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add stdout handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(level)
    root_logger.addHandler(handler)

    # Configure specific loggers
    # Reduce noise from uvicorn access logs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Reduce noise from httpx/httpcore
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Args:
        name: Logger name, typically __name__

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding extra context to log messages."""

    def __init__(self, logger: logging.Logger, **kwargs: Any) -> None:
        self.logger = logger
        self.extra = kwargs
        self._old_extra: dict[str, Any] = {}

    def __enter__(self) -> logging.Logger:
        # Store existing extra if any
        if hasattr(self.logger, "_extra"):
            self._old_extra = getattr(self.logger, "_extra", {}).copy()

        # Create adapter with extra context
        adapter = logging.LoggerAdapter(self.logger, self.extra)
        return adapter  # type: ignore[return-value]

    def __exit__(self, *args: Any) -> None:
        pass


# Convenience function for request logging
def log_request(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    latency_ms: float,
    user_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Log an HTTP request with structured data."""
    logger.info(
        "HTTP request",
        extra={
            "http_method": method,
            "http_path": path,
            "http_status": status_code,
            "latency_ms": round(latency_ms, 2),
            "user_id": user_id,
            "request_id": request_id,
        },
    )
