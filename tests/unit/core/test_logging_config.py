"""
Unit tests for core/logging_config.py - Structlog based structured logging.
"""

import json
import logging
from pathlib import Path
import structlog
from core.logging_config import (
    get_logger,
    setup_logging,
)

class TestStructlogLogging:
    """Tests for the structlog-based setup_logging function."""

    def test_setup_creates_log_directory(self, temp_logs_dir: Path):
        """Test that setup creates log directory."""
        log_dir = temp_logs_dir / "new_logs"
        assert not log_dir.exists()
        setup_logging(log_level="INFO", log_dir=str(log_dir), use_json=True)
        assert log_dir.exists()

    def test_setup_configures_structlog(self, temp_logs_dir: Path):
        """Test that setup properly configures structlog."""
        setup_logging(log_level="INFO", log_dir=str(temp_logs_dir), use_json=True)
        
        # Check that structlog's processors include JSONRenderer when use_json is True
        config = structlog.get_config()
        assert any(isinstance(p, structlog.processors.JSONRenderer) for p in config["processors"])

    def test_log_file_creation(self, temp_logs_dir: Path):
        """Test that log file is created with correct name."""
        app_name = "testbot"
        setup_logging(log_level="INFO", log_dir=str(temp_logs_dir), use_json=True, app_name=app_name)

        log_file = temp_logs_dir / f"{app_name}.log"
        # We need to log something to ensure the file is created/written
        logger = get_logger("test")
        logger.info("Test log message")
        
        assert log_file.exists()

    def test_log_file_content_is_json(self, temp_logs_dir: Path):
        """Test that logs written to file are valid JSON."""
        app_name = "jsonbot"
        setup_logging(log_level="INFO", log_dir=str(temp_logs_dir), use_json=True, app_name=app_name)

        logger = get_logger("json_test")
        logger.info("JSON message", key="value")

        log_file = temp_logs_dir / f"{app_name}.log"
        content = log_file.read_text().strip()
        
        # File might contain multiple lines if other things logged, take the last one
        last_line = content.splitlines()[-1]
        parsed = json.loads(last_line)
        
        assert parsed["event"] == "JSON message"
        assert parsed["key"] == "value"
        assert "level" in parsed
        assert "timestamp" in parsed

class TestGetLogger:
    """Tests for the get_logger function."""

    def test_get_logger_returns_bound_logger(self):
        """Test that get_logger returns a structlog BoundLogger."""
        logger = get_logger("test.module")
        assert isinstance(logger, structlog.stdlib.BoundLogger)
