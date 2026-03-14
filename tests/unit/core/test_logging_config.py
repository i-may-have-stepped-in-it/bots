"""
Unit tests for core/logging_config.py - Structured logging configuration.
"""

import json
import logging
import logging.handlers
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.logging_config import (
    JSONFormatter,
    ColoredFormatter,
    setup_logging,
    get_logger,
)


# =============================================================================
# JSONFormatter Tests
# =============================================================================

class TestJSONFormatter:
    """Tests for the JSONFormatter class."""

    def test_basic_formatting(self):
        """Test basic JSON log formatting."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["module"] == "test"
        assert parsed["function"] == "<module>"
        assert parsed["line"] == 42
        assert parsed["message"] == "Test message"
        assert "timestamp" in parsed

    def test_format_with_extra_fields(self):
        """Test formatting with extra fields."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        # Add extra fields
        record.user_id = 12345
        record.command = "!draw"
        record.guild_id = 67890
        record.channel_id = 11111
        
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        
        assert parsed["user_id"] == 12345
        assert parsed["command"] == "!draw"
        assert parsed["guild_id"] == 67890
        assert parsed["channel_id"] == 11111

    def test_format_with_exception(self):
        """Test formatting with exception info."""
        formatter = JSONFormatter()
        
        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = logging.sys.exc_info()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        
        assert parsed["level"] == "ERROR"
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "Test exception" in parsed["exception"]

    def test_special_characters_in_message(self):
        """Test handling special characters in log message."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='Message with "quotes" and \n newlines',
            args=(),
            exc_info=None,
        )
        
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        
        assert "quotes" in parsed["message"]
        # Newlines should be escaped in JSON
        assert "\\n" in formatted or "\n" in parsed["message"]

    def test_unicode_in_message(self):
        """Test handling unicode characters."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Unicode: 你好世界 🎉 émojis",
            args=(),
            exc_info=None,
        )
        
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        
        assert "你好世界" in parsed["message"]
        assert "🎉" in parsed["message"]


# =============================================================================
# ColoredFormatter Tests
# =============================================================================

class TestColoredFormatter:
    """Tests for the ColoredFormatter class."""

    def test_basic_formatting(self):
        """Test basic colored formatting."""
        formatter = ColoredFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        formatted = formatter.format(record)
        
        assert "INFO" in formatted
        assert "test.logger" in formatted
        assert "Test message" in formatted

    def test_level_colors(self):
        """Test different log levels have appropriate colors."""
        formatter = ColoredFormatter()
        
        colors = formatter.COLORS
        
        # Check that each level has a color code
        assert "DEBUG" in colors
        assert "INFO" in colors
        assert "WARNING" in colors
        assert "ERROR" in colors
        assert "CRITICAL" in colors
        
        # Each should be an ANSI escape code
        for level, color in colors.items():
            if level != "RESET":
                assert color.startswith("\033[")

    def test_level_alignment(self):
        """Test that level names are padded for alignment."""
        formatter = ColoredFormatter()
        
        debug_record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="t.py", lineno=1,
            msg="msg", args=(), exc_info=None,
        )
        critical_record = logging.LogRecord(
            name="test", level=logging.CRITICAL, pathname="t.py", lineno=1,
            msg="msg", args=(), exc_info=None,
        )
        
        debug_formatted = formatter.format(debug_record)
        critical_formatted = formatter.format(critical_record)
        
        # Both should have similar structure despite different level name lengths
        assert "DEBUG" in debug_formatted
        assert "CRITICAL" in critical_formatted


# =============================================================================
# setup_logging Tests
# =============================================================================

class TestSetupLogging:
    """Tests for the setup_logging function."""

    def test_setup_creates_log_directory(self, temp_logs_dir: Path):
        """Test that setup creates log directory."""
        log_dir = temp_logs_dir / "new_logs"
        
        assert not log_dir.exists()
        
        setup_logging(log_level="INFO", log_dir=str(log_dir), use_json=True)
        
        assert log_dir.exists()

    def test_setup_creates_handlers(self, temp_logs_dir: Path):
        """Test that setup creates file and console handlers."""
        setup_logging(log_level="INFO", log_dir=str(temp_logs_dir), use_json=True)
        
        root_logger = logging.getLogger()
        
        # Should have at least 2 handlers (file + console)
        assert len(root_logger.handlers) >= 2
        
        # Check for file handler
        file_handlers = [
            h for h in root_logger.handlers 
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(file_handlers) >= 1
        
        # Check for console handler
        console_handlers = [
            h for h in root_logger.handlers 
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(console_handlers) >= 1

    def test_setup_sets_log_level(self, temp_logs_dir: Path):
        """Test that setup sets the correct log level."""
        setup_logging(log_level="DEBUG", log_dir=str(temp_logs_dir), use_json=True)
        
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
        
        # Clean up and test another level
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        setup_logging(log_level="WARNING", log_dir=str(temp_logs_dir), use_json=True)
        assert root_logger.level == logging.WARNING

    def test_setup_with_json_formatter(self, temp_logs_dir: Path):
        """Test setup with JSON formatter."""
        setup_logging(log_level="INFO", log_dir=str(temp_logs_dir), use_json=True)
        
        root_logger = logging.getLogger()
        file_handler = next(
            h for h in root_logger.handlers 
            if isinstance(h, logging.handlers.RotatingFileHandler)
        )
        
        assert isinstance(file_handler.formatter, JSONFormatter)

    def test_setup_without_json_formatter(self, temp_logs_dir: Path):
        """Test setup without JSON formatter."""
        setup_logging(log_level="INFO", log_dir=str(temp_logs_dir), use_json=False)
        
        root_logger = logging.getLogger()
        file_handler = next(
            h for h in root_logger.handlers 
            if isinstance(h, logging.handlers.RotatingFileHandler)
        )
        
        assert isinstance(file_handler.formatter, logging.Formatter)
        assert not isinstance(file_handler.formatter, JSONFormatter)

    def test_rotating_file_handler_settings(self, temp_logs_dir: Path):
        """Test RotatingFileHandler is configured correctly."""
        setup_logging(
            log_level="INFO", 
            log_dir=str(temp_logs_dir), 
            use_json=True,
            max_bytes=1024,
            backup_count=3
        )
        
        root_logger = logging.getLogger()
        file_handler = next(
            h for h in root_logger.handlers 
            if isinstance(h, logging.handlers.RotatingFileHandler)
        )
        
        assert file_handler.maxBytes == 1024
        assert file_handler.backupCount == 3

    def test_library_log_level_reduction(self, temp_logs_dir: Path):
        """Test that external library loggers are set to WARNING."""
        setup_logging(log_level="DEBUG", log_dir=str(temp_logs_dir), use_json=True)
        
        assert logging.getLogger("discord").level == logging.WARNING
        assert logging.getLogger("asyncio").level == logging.WARNING
        assert logging.getLogger("aiosqlite").level == logging.WARNING

    def test_log_file_creation(self, temp_logs_dir: Path):
        """Test that log file is created."""
        setup_logging(log_level="INFO", log_dir=str(temp_logs_dir), use_json=True)
        
        log_file = temp_logs_dir / "jennifer.log"
        assert log_file.exists()

    def test_log_file_writing(self, temp_logs_dir: Path):
        """Test that logs are written to file."""
        setup_logging(log_level="INFO", log_dir=str(temp_logs_dir), use_json=True)
        
        logger = logging.getLogger("test")
        logger.info("Test log message")
        
        log_file = temp_logs_dir / "jennifer.log"
        content = log_file.read_text()
        
        assert "Test log message" in content
        # Should be JSON formatted
        parsed = json.loads(content.strip())
        assert parsed["message"] == "Test log message"


# =============================================================================
# get_logger Tests
# =============================================================================

class TestGetLogger:
    """Tests for the get_logger function."""

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a Logger instance."""
        logger = get_logger("test.module")
        
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_get_logger_same_name(self):
        """Test that get_logger returns same logger for same name."""
        logger1 = get_logger("same.name")
        logger2 = get_logger("same.name")
        
        assert logger1 is logger2

    def test_get_logger_different_names(self):
        """Test that get_logger returns different loggers for different names."""
        logger1 = get_logger("name.one")
        logger2 = get_logger("name.two")
        
        assert logger1 is not logger2


# =============================================================================
# Integration Tests
# =============================================================================

class TestLoggingIntegration:
    """Integration tests for the logging system."""

    def test_full_logging_workflow(self, temp_logs_dir: Path):
        """Test a complete logging workflow."""
        setup_logging(log_level="DEBUG", log_dir=str(temp_logs_dir), use_json=True)
        
        logger = get_logger("test.workflow")
        
        # Log at different levels
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        
        # Read log file
        log_file = temp_logs_dir / "jennifer.log"
        lines = log_file.read_text().strip().split("\n")
        
        assert len(lines) == 3
        
        # Verify each line is valid JSON
        for line in lines:
            parsed = json.loads(line)
            assert "timestamp" in parsed
            assert "level" in parsed
            assert "message" in parsed

    def test_exception_logging(self, temp_logs_dir: Path):
        """Test logging exceptions."""
        setup_logging(log_level="INFO", log_dir=str(temp_logs_dir), use_json=True)
        
        logger = get_logger("test.exception")
        
        try:
            raise ValueError("Something went wrong")
        except ValueError:
            logger.exception("An error occurred")
        
        log_file = temp_logs_dir / "jennifer.log"
        content = log_file.read_text()
        parsed = json.loads(content.strip())
        
        assert parsed["level"] == "ERROR"
        assert "An error occurred" in parsed["message"]
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]

    def test_extra_fields_logging(self, temp_logs_dir: Path):
        """Test logging with extra fields."""
        setup_logging(log_level="INFO", log_dir=str(temp_logs_dir), use_json=True)
        
        logger = get_logger("test.extra")
        
        logger.info(
            "User action",
            extra={
                "user_id": 12345,
                "command": "!draw",
                "guild_id": 67890,
            }
        )
        
        log_file = temp_logs_dir / "jennifer.log"
        content = log_file.read_text()
        parsed = json.loads(content.strip())
        
        assert parsed["user_id"] == 12345
        assert parsed["command"] == "!draw"
        assert parsed["guild_id"] == 67890
