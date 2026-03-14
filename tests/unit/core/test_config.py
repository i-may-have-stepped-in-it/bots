"""
Unit tests for core/config.py - Configuration management with Pydantic.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from core.config import (
    SDConfig,
    OpenClawConfig,
    VoiceConfig,
    VideoConfig,
    JenniferConfig,
    load_config,
    reload_config,
)


# =============================================================================
# SDConfig Tests
# =============================================================================

class TestSDConfig:
    """Tests for Stable Diffusion configuration."""

    def test_default_values(self):
        """Test SDConfig default values."""
        config = SDConfig()
        assert config.url == "http://100.85.221.20:7860"
        assert config.model == "cyberrealistic_classic40"
        assert config.clip_skip == 0
        assert config.cfg_scale == 7.0
        assert config.height == 1024
        assert config.width == 512
        assert config.sampler == "DPM++ 2M"
        assert config.scheduler == "automatic"
        assert config.steps == 20

    def test_custom_values(self):
        """Test SDConfig with custom values."""
        config = SDConfig(
            url="http://custom:7860",
            model="custom-model",
            clip_skip=2,
            cfg_scale=8.5,
            height=768,
            width=768,
            negative_prompt="custom negative",
            positive_prompt_prefix="custom positive",
            sampler="Euler",
            scheduler="karras",
            steps=30,
        )
        assert config.url == "http://custom:7860"
        assert config.model == "custom-model"
        assert config.clip_skip == 2
        assert config.cfg_scale == 8.5
        assert config.height == 768
        assert config.width == 768
        assert config.negative_prompt == "custom negative"
        assert config.positive_prompt_prefix == "custom positive"
        assert config.sampler == "Euler"
        assert config.scheduler == "karras"
        assert config.steps == 30

    def test_to_dict(self):
        """Test SDConfig can be converted to dict."""
        config = SDConfig(model="test-model")
        config_dict = config.model_dump()
        assert config_dict["model"] == "test-model"
        assert "url" in config_dict


# =============================================================================
# OpenClawConfig Tests
# =============================================================================

class TestOpenClawConfig:
    """Tests for OpenClaw gateway configuration."""

    def test_default_values(self):
        """Test OpenClawConfig default values."""
        config = OpenClawConfig()
        assert config.gateway == "https://vmi3115281.tail36566.ts.net/"
        assert config.token == ""
        assert config.model == "localai/Qwen3-14B-Nexa-Uncensored"
        assert config.async_mode is True
        assert config.bearer == "password"
        assert config.context_window == 10240
        assert config.embedding == "text-embedding-ada-002"
        assert config.embedding_dim == 1024
        assert config.embedding_endpoint_type == "openai"
        assert config.model_endpoint_type == "openai"
        assert config.use_assistant_message is False
        assert config.stream is False
        assert config.timeout == 600
        assert config.fallback_models == []
        assert config.embedding_endpoints == []
        assert config.model_endpoints == []

    def test_fallback_chain(self):
        """Test OpenClawConfig with fallback models."""
        config = OpenClawConfig(
            fallback_models=["model1", "model2", "model3"],
            model_endpoints=["http://ep1", "http://ep2"],
            embedding_endpoints=["http://embed1", "http://embed2"],
        )
        assert config.fallback_models == ["model1", "model2", "model3"]
        assert config.model_endpoints == ["http://ep1", "http://ep2"]
        assert config.embedding_endpoints == ["http://embed1", "http://embed2"]


# =============================================================================
# VoiceConfig Tests
# =============================================================================

class TestVoiceConfig:
    """Tests for voice/TTS configuration."""

    def test_default_values(self):
        """Test VoiceConfig default values."""
        config = VoiceConfig()
        assert config.silero_speaker == "en_107"
        assert config.openai_tts_backend == "bark"
        assert config.openai_tts_voice_model == ""
        assert config.recognizer == "whisper"


# =============================================================================
# VideoConfig Tests
# =============================================================================

class TestVideoConfig:
    """Tests for Video generation configuration."""

    def test_default_values(self):
        """Test VideoConfig default values."""
        config = VideoConfig()
        assert config.backend == "zai"
        assert config.zai_api_key == ""
        assert config.zai_api_endpoint == "https://api.z.ai/api/paas/v4"
        assert config.zai_model == "CogVideoX-3"
        assert config.zai_resolution == "720p"
        assert config.zai_duration == 5
        assert config.framepack_url == "http://localhost:7860"
        assert config.framepack_model == "FramePack (Original)"
        assert config.framepack_steps == 25
        assert config.framepack_width == 640
        assert config.framepack_height == 480
        assert config.framepack_video_length == 4.0
        assert config.framepack_use_teacache is True
        assert config.rate_limit_per_minute == 3
        assert config.max_prompt_length == 500

    def test_custom_zai_values(self):
        """Test VideoConfig with Z.AI backend."""
        config = VideoConfig(
            backend="zai",
            zai_api_key="test-key",
            zai_api_endpoint="https://custom.z.ai/api",
            zai_model="ViduQ1",
            zai_resolution="1080p",
            zai_duration=10,
        )
        assert config.backend == "zai"
        assert config.zai_api_key == "test-key"
        assert config.zai_model == "ViduQ1"
        assert config.zai_resolution == "1080p"
        assert config.zai_duration == 10

    def test_custom_framepack_values(self):
        """Test VideoConfig with FramePack backend."""
        config = VideoConfig(
            backend="framepack",
            framepack_url="http://192.168.1.100:7860",
            framepack_model="FramePack-F1",
            framepack_steps=30,
            framepack_width=512,
            framepack_height=768,
            framepack_video_length=6.0,
            framepack_use_teacache=False,
        )
        assert config.backend == "framepack"
        assert config.framepack_url == "http://192.168.1.100:7860"
        assert config.framepack_model == "FramePack-F1"
        assert config.framepack_steps == 30
        assert config.framepack_use_teacache is False


# =============================================================================
# JenniferConfig Tests
# =============================================================================

class TestJenniferConfig:
    """Tests for main Jennifer configuration."""

    def test_default_values(self):
        """Test JenniferConfig default values."""
        config = JenniferConfig()
        assert config.name == "Jennifer"
        assert config.personality == ""
        assert config.appearance == ""
        assert config.log_level == "INFO"
        assert config.log_level_debug == "DEBUG"
        assert config.typing_delay == 1
        assert config.history_length == 12000
        assert config.only_when_called is True
        assert config.respond_to_mentions is True
        assert config.interaction_timeout == 60
        assert config.allow_dm_responses is True
        assert config.discord_token == ""
        assert config.allowed_channels == []
        assert config.power_users == []
        assert config.allowed_dm_users == []
        assert config.bot_users == []
        assert config.ignored_users == []
        assert config.ignored_words == []
        # Nested configs
        assert isinstance(config.sd, SDConfig)
        assert isinstance(config.openclaw, OpenClawConfig)
        assert isinstance(config.voice, VoiceConfig)
        assert isinstance(config.video, VideoConfig)

    def test_get_history_file_name(self):
        """Test history filename generation."""
        config = JenniferConfig(name="TestBot")
        assert config.get_history_file_name() == "TestBot_message_histories.json"
        
        config_default = JenniferConfig()
        assert config_default.get_history_file_name() == "Jennifer_message_histories.json"

    def test_is_power_user(self):
        """Test power user checking."""
        config = JenniferConfig(power_users=[123, 456])
        assert config.is_power_user(123) is True
        assert config.is_power_user(456) is True
        assert config.is_power_user(789) is False
        assert config.is_power_user(0) is False

    def test_is_allowed_channel(self):
        """Test allowed channel checking."""
        config = JenniferConfig(allowed_channels=[100, 200, 300])
        assert config.is_allowed_channel(100) is True
        assert config.is_allowed_channel(300) is True
        assert config.is_allowed_channel(999) is False
        assert config.is_allowed_channel(0) is False

    def test_is_ignored_user(self):
        """Test ignored user checking."""
        config = JenniferConfig(ignored_users=[666, 777])
        assert config.is_ignored_user(666) is True
        assert config.is_ignored_user(777) is True
        assert config.is_ignored_user(123) is False
        assert config.is_ignored_user(0) is False


# =============================================================================
# Config Loading Tests
# =============================================================================

class TestConfigLoading:
    """Tests for loading configuration from files."""

    def test_load_valid_config(self, temp_config_dir: Path, minimal_config_dict: dict):
        """Test loading a valid config file."""
        config_path = temp_config_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(minimal_config_dict, f)
        
        config = JenniferConfig.load(str(config_path))
        
        assert config.name == "TestJennifer"
        assert config.personality == "A friendly test bot"
        assert config.discord_token == "test-token-12345"
        assert 123456789 in config.allowed_channels
        assert 987654321 in config.power_users
        assert "spam" in config.ignored_words

    def test_load_file_not_found(self, temp_config_dir: Path):
        """Test loading non-existent config file."""
        config_path = temp_config_dir / "nonexistent.json"
        
        with pytest.raises(FileNotFoundError) as exc_info:
            JenniferConfig.load(str(config_path))
        
        assert "not found" in str(exc_info.value)

    def test_load_invalid_json(self, temp_config_dir: Path):
        """Test loading invalid JSON."""
        config_path = temp_config_dir / "invalid.json"
        with open(config_path, "w") as f:
            f.write("{ invalid json }")
        
        with pytest.raises(json.JSONDecodeError):
            JenniferConfig.load(str(config_path))


# =============================================================================
# Legacy Migration Tests
# =============================================================================

class TestLegacyMigration:
    """Tests for migrating legacy config format."""

    def test_migrate_legacy_basic(self, legacy_config_dict: dict):
        """Test basic legacy config migration."""
        config = JenniferConfig._migrate_legacy(legacy_config_dict)
        
        assert config.name == "LegacyJennifer"
        assert config.discord_token == "legacy-token"

    def test_migrate_legacy_fallback_models(self, legacy_config_dict: dict):
        """Test migration of numbered fallback models."""
        config = JenniferConfig._migrate_legacy(legacy_config_dict)
        
        assert config.openclaw.fallback_models == [
            "fallback-model-1",
            "fallback-model-2",
            "fallback-model-3",
        ]

    def test_migrate_legacy_endpoints(self, legacy_config_dict: dict):
        """Test migration of numbered endpoints."""
        config = JenniferConfig._migrate_legacy(legacy_config_dict)
        
        assert config.openclaw.model_endpoints == [
            "http://endpoint1:8000",
            "http://endpoint2:8000",
        ]
        assert config.openclaw.embedding_endpoints == [
            "http://embed1:8000",
        ]

    def test_migrate_legacy_no_numbered_fields(self):
        """Test migration when no numbered fields exist."""
        raw = {"Name": "SimpleBot", "DiscordToken": "token123"}
        config = JenniferConfig._migrate_legacy(raw)
        
        assert config.name == "SimpleBot"
        assert config.openclaw.fallback_models == []
        assert config.openclaw.model_endpoints == []

    def test_migrate_legacy_partial_numbered_fields(self):
        """Test migration with partial numbered fields (gaps in sequence)."""
        raw = {
            "Name": "GapBot",
            "OpenClawmodel1": "model-1",
            "OpenClawmodel3": "model-3",  # Skip model2
            "OpenClawmodel5": "model-5",  # Skip model4
        }
        config = JenniferConfig._migrate_legacy(raw)
        
        assert config.openclaw.fallback_models == ["model-1", "model-3", "model-5"]


# =============================================================================
# Full Config Tests
# =============================================================================

class TestFullConfig:
    """Tests for full configuration with all options."""

    def test_full_config(self, full_config_dict: dict):
        """Test migration of full config dictionary."""
        config = JenniferConfig._migrate_legacy(full_config_dict)
        
        # Basic settings
        assert config.name == "TestJennifer"
        assert config.log_level == "DEBUG"
        assert config.history_length == 10000
        assert config.only_when_called is False
        assert config.interaction_timeout == 120
        
        # Lists
        assert len(config.allowed_channels) == 2
        assert len(config.power_users) == 2
        assert len(config.ignored_words) == 2
        
        # SD Config
        assert config.sd.url == "http://test-sd:7860"
        assert config.sd.model == "test-sd-model"
        assert config.sd.clip_skip == 2
        assert config.sd.cfg_scale == 7.5
        assert config.sd.height == 1024
        assert config.sd.width == 1024
        assert config.sd.sampler == "DPM++ 2M"
        assert config.sd.scheduler == "karras"
        assert config.sd.steps == 25
        
        # OpenClaw Config
        assert config.openclaw.gateway == "http://test-gateway:8000"
        assert config.openclaw.model == "test-model-v1"
        assert config.openclaw.context_window == 8192
        assert config.openclaw.embedding_dim == 768
        assert config.openclaw.use_assistant_message is True
        
        # Voice Config
        assert config.voice.silero_speaker == "en_test"
        assert config.voice.recognizer == "whisper"


# =============================================================================
# Global Config Functions Tests
# =============================================================================

class TestGlobalConfig:
    """Tests for global config loading functions."""

    def test_load_config_caching(self, temp_config_dir: Path, minimal_config_dict: dict):
        """Test that load_config caches the config."""
        config_path = temp_config_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(minimal_config_dict, f)
        
        # Reset the global cache
        import core.config as config_module
        config_module._config = None
        
        # First load should cache
        config1 = load_config(str(config_path))
        
        # Second load should return cached
        config2 = load_config(str(config_path))
        
        assert config1 is config2

    def test_reload_config_forces_reload(self, temp_config_dir: Path, minimal_config_dict: dict):
        """Test that reload_config forces a fresh load."""
        config_path = temp_config_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(minimal_config_dict, f)
        
        # Reset the global cache
        import core.config as config_module
        config_module._config = None
        
        config1 = load_config(str(config_path))
        
        # Modify the file
        minimal_config_dict["Name"] = "ModifiedName"
        with open(config_path, "w") as f:
            json.dump(minimal_config_dict, f)
        
        # Reload should get new values
        config2 = reload_config(str(config_path))
        
        assert config2.name == "ModifiedName"
        assert config1 is config2  # Should replace cached instance


# =============================================================================
# Edge Cases and Validation Tests
# =============================================================================

class TestConfigEdgeCases:
    """Tests for edge cases and validation."""

    def test_empty_config(self):
        """Test with completely empty config."""
        config = JenniferConfig._migrate_legacy({})
        
        assert config.name == "Jennifer"  # Default
        assert config.discord_token == ""
        assert config.allowed_channels == []

    def test_special_characters_in_strings(self):
        """Test handling of special characters."""
        raw = {
            "Name": "Bot with \"quotes\" and 'apostrophes'",
            "Personality": "Line1\nLine2\tTabbed",
            "DiscordToken": "token_with_special!@#$%",
        }
        config = JenniferConfig._migrate_legacy(raw)
        
        assert "quotes" in config.name
        assert "apostrophes" in config.name
        assert config.personality == "Line1\nLine2\tTabbed"

    def test_very_long_strings(self):
        """Test handling of very long strings."""
        long_personality = "A" * 10000
        raw = {"Personality": long_personality}
        config = JenniferConfig._migrate_legacy(raw)
        
        assert len(config.personality) == 10000

    def test_unicode_in_config(self):
        """Test handling of unicode characters."""
        raw = {
            "Name": "詹妮弗 🤖",
            "Personality": "日本語 테스트 🎌",
        }
        config = JenniferConfig._migrate_legacy(raw)
        
        assert config.name == "詹妮弗 🤖"
        assert config.personality == "日本語 테스트 🎌"
