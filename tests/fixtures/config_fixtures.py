"""
Configuration fixtures for testing.
"""

from typing import Dict, Any


def create_minimal_config(
    name: str = "TestJennifer",
    token: str = "test-token-12345",
) -> Dict[str, Any]:
    """
    Create a minimal valid configuration dictionary.
    
    Args:
        name: Bot name
        token: Discord token
        
    Returns:
        Configuration dictionary
    """
    return {
        "Name": name,
        "Personality": "A friendly test bot",
        "Appearance": "Digital assistant",
        "DiscordToken": token,
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


def create_full_config() -> Dict[str, Any]:
    """
    Create a full configuration dictionary with all options.
    
    Returns:
        Complete configuration dictionary
    """
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


def create_legacy_config(
    name: str = "LegacyJennifer",
    num_models: int = 3,
) -> Dict[str, Any]:
    """
    Create a legacy config with numbered model fields for migration testing.
    
    Args:
        name: Bot name
        num_models: Number of fallback models to include
        
    Returns:
        Legacy configuration dictionary
    """
    config = {
        "Name": name,
        "DiscordToken": "legacy-token",
    }
    
    # Add numbered model fields
    for i in range(1, num_models + 1):
        config[f"OpenClawmodel{i}"] = f"fallback-model-{i}"
        
    # Add some endpoint fields
    config["OpenClawModelEndpoint1"] = "http://endpoint1:8000"
    config["OpenClawModelEndpoint2"] = "http://endpoint2:8000"
    config["OpenClawEmbeddingEndpoint1"] = "http://embed1:8000"
    
    return config


def create_invalid_config() -> Dict[str, Any]:
    """
    Create an invalid configuration for error testing.
    
    Returns:
        Invalid configuration dictionary
    """
    return {
        "Name": "",  # Empty name
        "DiscordToken": 12345,  # Should be string
        "AllowedChannels": "not-a-list",  # Should be list
        "Power_Users": None,  # Should be list
    }
