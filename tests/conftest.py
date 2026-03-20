"""
Pytest configuration and shared fixtures for Jennifer bot tests.
"""

import asyncio
import json
import os
import pytest
import pytest_asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Generator, AsyncGenerator


# =============================================================================
# Event Loop Fixture (for async tests)
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Temporary Directory Fixtures
# =============================================================================

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def temp_data_dir(temp_dir: Path) -> Path:
    """Create a temporary data directory."""
    data_dir = temp_dir / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


@pytest.fixture
def temp_config_dir(temp_dir: Path) -> Path:
    """Create a temporary config directory."""
    config_dir = temp_dir / "config"
    config_dir.mkdir(exist_ok=True)
    return config_dir


@pytest.fixture
def temp_logs_dir(temp_dir: Path) -> Path:
    """Create a temporary logs directory."""
    logs_dir = temp_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    return logs_dir


# =============================================================================
# Configuration Fixtures
# =============================================================================

@pytest.fixture
def minimal_config_dict() -> dict:
    """Return a minimal valid configuration dictionary."""
    return {
        "Name": "TestJennifer",
        "Personality": "A friendly test bot",
        "Appearance": "Digital assistant",
        "DiscordToken": "test-token-12345",
        "AllowedChannels": [123456789],
        "Power_Users": [987654321],
        "IgnoredUsers": [],
        "IgnoredWords": ["spam"],
        "LogLevel": "DEBUG",
        "OnlyWhenCalled": True,
        "RespondToMentions": True,
        "History_Length": 5000,
        "SDBackend": "automatic1111",
        "SDURL": "http://localhost:7860",
        "SDmodel": "test-model",
        "OpenClawGateway": "http://localhost:8000",
        "OpenClawToken": "test-token",
        "OpenClawmodel": "test-model",
    }


@pytest.fixture
def full_config_dict() -> dict:
    """Return a full configuration dictionary with all options."""
    return {
        "Name": "TestJennifer",
        "Personality": "A friendly test bot personality",
        "Appearance": "Digital assistant with blue theme",
        "LogLevel": "DEBUG",
        "LogLevel1": "TRACE",
        "TypingDelay": 0,
        "History_Length": 10000,
        "OnlyWhenCalled": False,
        "RespondToMentions": True,
        "InteractionTimeout": 120,
        "AllowDMResponses": True,
        "DiscordToken": "test-discord-token-12345",
        "AllowedChannels": [111111111, 222222222],
        "Power_Users": [987654321, 876543210],
        "AllowedDMUsers": [111111111],
        "bot_user": [999999999],
        "IgnoredUsers": [666666666],
        "IgnoredWords": ["spam", "badword"],
        "SDBackend": "automatic1111",
        "SDURL": "http://test-sd:7860",
        "SDmodel": "test-sd-model",
        "SDClipSkip": 2,
        "SDConfig": 7.5,
        "SDHeight": 1024,
        "SDWidth": 1024,
        "SDNegativePrompt": "test negative",
        "SDPositivePrompt": "test positive",
        "SDSampler": "DPM++ 2M",
        "SDScheduler": "karras",
        "SDSteps": 25,
        "OpenClawGateway": "http://test-gateway:8000",
        "OpenClawToken": "test-openclaw-token",
        "OpenClawmodel": "test-model-v1",
        "OpenClawAgent": "test-agent",
        "OpenClawAsync": True,
        "OpenClawBearer": "test-bearer",
        "OpenClawContextWindow": 8192,
        "OpenClawEmbedding": "text-embedding-test",
        "OpenClawEmbeddingDim": 768,
        "OpenClawEmbeddingEndpoint": "http://test-embed:38078/v1",
        "OpenClawEmbeddingEndpointType": "openai",
        "OpenClawModelEndpoint": "http://test-model:38078/v1",
        "OpenClawModelEndpointType": "openai",
        "OpenClawPersonality": "Test personality",
        "OpenClawSystemPrompt": "You are a test bot",
        "OpenClawUseAssistantMessage": True,
        "OpenClawStream": False,
        "OpenClawtimeout": 300,
        "SileroSpeaker": "en_test",
        "OpenaiTTSBackend": "test",
        "recognizer": "whisper",
    }


@pytest.fixture
def legacy_config_dict() -> dict:
    """Return a legacy config with numbered model fields for migration testing."""
    return {
        "Name": "LegacyJennifer",
        "OpenClawmodel1": "fallback-model-1",
        "OpenClawmodel2": "fallback-model-2",
        "OpenClawmodel3": "fallback-model-3",
        "OpenClawModelEndpoint1": "http://endpoint1:8000",
        "OpenClawModelEndpoint2": "http://endpoint2:8000",
        "OpenClawEmbeddingEndpoint1": "http://embed1:8000",
        "DiscordToken": "legacy-token",
    }


@pytest.fixture
def config_file(temp_config_dir: Path, minimal_config_dict: dict) -> Path:
    """Create a temporary config file."""
    config_path = temp_config_dir / "config.json"
    with open(config_path, "w") as f:
        json.dump(minimal_config_dict, f)
    return config_path


# =============================================================================
# Discord Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_discord_message():
    """Create a mock Discord message."""
    message = MagicMock()
    message.id = 123456789
    message.content = "Hello Jennifer!"
    message.author = MagicMock()
    message.author.id = 987654321
    message.author.display_name = "TestUser"
    message.author.name = "testuser"
    message.author.bot = False
    message.channel = MagicMock()
    message.channel.id = 111111111
    message.channel.type = MagicMock()
    message.channel.type.name = "text"
    message.channel.send = AsyncMock()
    message.guild = MagicMock()
    message.guild.id = 555555555
    message.guild.voice_client = None
    message.mentions = []
    message.reference = None
    return message


@pytest.fixture
def mock_discord_dm():
    """Create a mock Discord DM channel message."""
    message = MagicMock()
    message.id = 123456789
    message.content = "Hello in DM!"
    message.author = MagicMock()
    message.author.id = 987654321
    message.author.display_name = "TestUser"
    message.author.name = "testuser"
    message.author.bot = False
    message.channel = MagicMock()
    message.channel.id = 987654321  # DM channel ID
    message.channel.type = MagicMock()
    message.channel.type.name = "private"
    message.channel.send = AsyncMock()
    message.guild = None
    message.mentions = []
    message.reference = None
    return message


@pytest.fixture
def mock_discord_user():
    """Create a mock Discord user."""
    user = MagicMock()
    user.id = 987654321
    user.name = "testuser"
    user.display_name = "TestUser"
    user.bot = False
    return user


@pytest.fixture
def mock_discord_bot_user():
    """Create a mock Discord bot user."""
    user = MagicMock()
    user.id = 111111111
    user.name = "Jennifer"
    user.display_name = "Jennifer"
    user.bot = True
    return user


@pytest.fixture
def mock_voice_channel():
    """Create a mock voice channel."""
    channel = MagicMock()
    channel.id = 777777777
    channel.name = "Test Voice Channel"
    channel.connect = AsyncMock()
    return channel


@pytest.fixture
def mock_member_with_voice():
    """Create a mock member in a voice channel."""
    member = MagicMock()
    member.id = 987654321
    member.name = "testuser"
    member.voice = MagicMock()
    member.voice.channel = MagicMock()
    member.voice.channel.id = 777777777
    member.voice.channel.name = "Test Voice"
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = False
    member.guild_permissions.manage_guild = False
    member.guild_permissions.manage_messages = False
    member.guild_permissions.moderate_members = False
    return member


@pytest.fixture
def mock_admin_member():
    """Create a mock member with admin permissions."""
    member = MagicMock()
    member.id = 987654321
    member.name = "adminuser"
    member.display_name = "AdminUser"
    member.voice = None
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = True
    member.guild_permissions.manage_guild = True
    member.guild_permissions.manage_messages = True
    member.guild_permissions.moderate_members = True
    return member


# =============================================================================
# Queue Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def temp_queue(temp_data_dir: Path):
    """Create a temporary persistent queue for testing."""
    from core.persistent_queue import PersistentQueue
    
    db_path = temp_data_dir / "test_queue.db"
    queue = PersistentQueue(str(db_path), max_retries=2)
    await queue.initialize()
    yield queue
    # Cleanup
    try:
        if db_path.exists():
            db_path.unlink()
    except:
        pass


@pytest_asyncio.fixture
async def temp_task_manager(temp_data_dir: Path):
    """Create a temporary task manager for testing."""
    from core.persistent_queue import TaskManager
    
    manager = TaskManager(str(temp_data_dir))
    yield manager


@pytest.fixture
def sample_task_payload() -> dict:
    """Return a sample task payload."""
    return {
        "message_content": "Test message",
        "channel_id": 111111111,
        "message_id": 123456789,
        "user_id": 987654321,
        "user_name": "TestUser",
    }


# =============================================================================
# pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "discord: marks tests that require discord.py")
    config.addinivalue_line("markers", "config: marks configuration-related tests")
    config.addinivalue_line("markers", "queue: marks queue-related tests")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test location."""
    for item in items:
        # Add marker based on file path
        if "test_config" in item.nodeid:
            item.add_marker(pytest.mark.config)
        elif "test_queue" in item.nodeid:
            item.add_marker(pytest.mark.queue)
        elif "/integration/" in item.nodeid:
            item.add_marker(pytest.mark.integration)
