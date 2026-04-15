"""
Structured logging using structlog.
Provides deep observability and log aggregation capabilities.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
import structlog

def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    use_json: bool = True,
    app_name: str = "jennifer",
) -> None:
    """Setup structured logging using structlog."""
    
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Standard python logging configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.handlers.clear()

    # Console Handler (Human-readable for stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    if use_json:
        console_handler.setFormatter(logging.Formatter('%(message)s'))
    else:
        # We'll let structlog render to console directly, 
        # so we just need a bare formatter here.
        console_handler.setFormatter(logging.Formatter('%(message)s'))
    root_logger.addHandler(console_handler)

    # File Handler (JSON rotated logs)
    log_file = log_path / f"{app_name.lower()}.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    root_logger.addHandler(file_handler)

    # Structlog processor pipeline
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
    ]

    # Use JSONRenderer for the final output
    if use_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Reduce noise
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)

    logger = structlog.get_logger()
    logger.info("Logging initialized", log_level=log_level, dir=log_dir, app=app_name)

def get_logger(name: str) -> structlog.BoundLogger:
    """Get structlog logger with specified name."""
    return structlog.get_logger(name)
