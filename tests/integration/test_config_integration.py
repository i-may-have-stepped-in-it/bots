"""
Integration tests for configuration loading and validation.
"""

import json
from pathlib import Path

import pytest

from core.config import JenniferConfig


@pytest.mark.integration
class TestConfigIntegration:
    """Integration tests for configuration system."""

    def test_config_end_to_end(self, temp_config_dir: Path):
        """Test complete config loading workflow."""
        # Create config file
        config_data = {
            "Name": "IntegrationTestBot",
            "DiscordToken": "integration-test-token",
            "AllowedChannels": [111, 222, 333],
            "Power_Users": [999, 888],
            "SDURL": "http://sd-server:7860",
            "OpenClawGateway": "http://gateway:8000",
        }

        config_path = temp_config_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        # Load config
        config = JenniferConfig.load(str(config_path))

        # Verify all values
        assert config.name == "IntegrationTestBot"
        assert config.discord_token == "integration-test-token"
        assert config.allowed_channels == [111, 222, 333]
        assert config.power_users == [999, 888]
        assert config.sd.url == "http://sd-server:7860"
        assert config.openclaw.gateway == "http://gateway:8000"

    def test_config_file_modification_and_reload(self, temp_config_dir: Path):
        """Test modifying config file and reloading."""
        config_path = temp_config_dir / "config.json"

        # Initial config
        initial = {"Name": "BotV1", "DiscordToken": "token1"}
        with open(config_path, "w") as f:
            json.dump(initial, f)

        # Load initial
        config1 = JenniferConfig.load(str(config_path))
        assert config1.name == "BotV1"

        # Modify file
        modified = {"Name": "BotV2", "DiscordToken": "token2"}
        with open(config_path, "w") as f:
            json.dump(modified, f)

        # Reload
        config2 = JenniferConfig.load(str(config_path))
        assert config2.name == "BotV2"


@pytest.mark.integration
class TestLoggingIntegration:
    """Integration tests for logging configuration."""

    def test_logging_setup_creates_files(self, temp_logs_dir: Path):
        """Test that logging setup creates log files."""
        import logging

        from core.logging_config import setup_logging

        setup_logging(
            log_level="DEBUG",
            log_dir=str(temp_logs_dir),
            use_json=True,
        )

        # Log some messages
        logger = logging.getLogger("test.integration")
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        # Verify log file exists and contains messages
        log_file = temp_logs_dir / "jennifer.log"
        assert log_file.exists()

        content = log_file.read_text()
        assert "Debug message" in content
        assert "Info message" in content
        assert "Warning message" in content
        assert "Error message" in content
