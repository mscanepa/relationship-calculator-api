import structlog
import logging
from typing import Any, Dict
from app.config import settings

def configure_logging() -> None:
    """Configure structured logging for the application."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set logging level
    logging.getLogger().setLevel(settings.LOG_LEVEL)

def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)

# Initialize logging
configure_logging()
logger = get_logger("app") 