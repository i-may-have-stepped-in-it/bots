"""
Pydantic-based configuration management for Jennifer.
Replaces the messy dict-based config with validated, typed settings.
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.secrets import vault

logger = logging.getLogger(__name__)

# Load encrypted secrets into environment before Pydantic evaluates BaseSettings
# vault.load_secrets_to_env() -- REMOVED for security

class SDConfig(BaseModel):
    """Stable Diffusion configuration."""
    backend: str = "automatic1111"  # automatic1111, comfyui, invokeai
    url: str = ""
    comfy_url: str = ""
    invoke_url: str = ""
    model: str = "cyberrealistic_classic40"
    clip_skip: int = 0
    cfg_scale: float = 7.0
    height: int = 1024
    width: int = 512
    negative_prompt: str = "CyberRealistic_Negative-neg"
    positive_prompt_prefix: str = "((best quality)), ((masterpiece)), (detailed), RAW photo, 8k uhd"
    sampler: str = "DPM++ 2M"
    scheduler: str = "automatic"
    steps: int = 20
    openai_prompt: str = ""  # Additional instructions for image prompt generation


class OpenClawConfig(BaseModel):
    """OpenClaw gateway configuration."""
    gateway: str = ""
    token: str = ""
    device_token: str = ""
    device_identity_path: str = ""
    model: str = "localai/Qwen3-14B-Nexa-Uncensored"
    agent: str = ""
    async_mode: bool = True
    bearer: str = "password"
    context_window: int = 10240
    embedding: str = "text-embedding-ada-002"
    embedding_dim: int = 1024
    embedding_endpoint: str = ""
    embedding_endpoint_type: str = "openai"
    model_endpoint: str = ""
    model_endpoint_type: str = "openai"
    personality: str = ""
    system_prompt: str = ""
    use_assistant_message: bool = False
    stream: bool = False
    timeout: int = 600
    primer: str = ""  # Initial greeting/message primer

    # Fields accessed via dict-style config["OpenClawPersona"]
    persona: str = ""  # Alias for personality (legacy compatibility)

    # Fallback chain (replaces numbered models)
    fallback_models: list[str] = Field(default_factory=list)

    # Legacy endpoint lists (for compatibility)
    embedding_endpoints: list[str] = Field(default_factory=list)
    model_endpoints: list[str] = Field(default_factory=list)


class VoiceConfig(BaseModel):
    """Voice/TTS configuration."""
    silero_speaker: str = "en_107"
    openai_tts_backend: str = "bark"
    openai_tts_voice_model: str = ""
    recognizer: str = "whisper"


class VideoConfig(BaseModel):
    """Video generation configuration.
    
    Supports two backends:
    - "zai": Z.AI API (cloud-based, models: CogVideoX-3, ViduQ1, Vidu2)
    - "framepack": Local FramePack instance (self-hosted)
    """
    # Backend selection
    backend: str = "zai"  # "zai" or "framepack"

    # Z.AI API settings
    zai_api_key: str = ""
    zai_api_endpoint: str = "https://api.z.ai/api/paas/v4"
    zai_model: str = "CogVideoX-3"  # CogVideoX-3, ViduQ1, Vidu2
    zai_resolution: str = "720p"  # 480p, 720p, 1080p (model dependent)
    zai_duration: int = 5  # seconds (model dependent)

    # FramePack local settings
    framepack_url: str = "http://localhost:7860"
    framepack_model: str = "FramePack (Original)"  # or "FramePack-F1"
    framepack_steps: int = 25
    framepack_width: int = 640
    framepack_height: int = 480
    framepack_video_length: float = 4.0  # seconds
    framepack_use_teacache: bool = True

    # Rate limiting (shared across backends)
    rate_limit_per_minute: int = 3
    max_prompt_length: int = 500


class ModelRouterConfig(BaseModel):
    """Model routing configuration for intelligent tier selection.
    
    Models are selected based on task complexity and content type.
    Each tier can have a primary model and optional fallback chain.
    """
    # High-speed tier: Fast, cheap models for simple queries
    highspeed_model: str = "zai/glm-4.7-flash"
    highspeed_fallbacks: list[str] = Field(default_factory=list)

    # Intelligence tier: Capable models for complex tasks
    intelligence_model: str = "moonshot/kimi-k2.5"
    intelligence_fallbacks: list[str] = Field(default_factory=lambda: [
        "zai/glm-4.7-flash",
    ])

    # Uncensored tier: Models for NSFW/sensitive content
    uncensored_model: str = "venice/venice-uncensored-role-play"
    uncensored_fallbacks: list[str] = Field(default_factory=lambda: [
        "venice/olafangensan-glm-4.7-flash-heretic",
        "localai/Qwen3-14B-Nexa-Uncensored",
    ])


class JenniferConfig(BaseSettings):
    """Main Jennifer bot configuration."""
    model_config = SettingsConfigDict(
        env_prefix="JENNIFER_",
        env_nested_delimiter="__",
        extra="ignore",
        env_ignore_empty=True,
    )

    # Bot identity
    name: str = "Jennifer"
    personality: str = ""
    appearance: str = ""

    # Logging
    log_level: str = "INFO"
    log_level_debug: str = "DEBUG"

    # Behavior
    typing_delay: int = 1
    history_length: int = 12000
    only_when_called: bool = True
    respond_to_mentions: bool = True
    interaction_timeout: int = 60
    allow_dm_responses: bool = True

    # Discord settings
    discord_token: str = ""
    allowed_channels: list[int] = Field(default_factory=list)
    power_users: list[int] = Field(default_factory=list)
    allowed_dm_users: list[int] = Field(default_factory=list)
    bot_users: list[int] = Field(default_factory=list)
    ignored_users: list[int] = Field(default_factory=list)
    ignored_words: list[str] = Field(default_factory=list)

    # Nested configs
    sd: SDConfig = Field(default_factory=SDConfig)
    openclaw: OpenClawConfig = Field(default_factory=OpenClawConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    model_router: ModelRouterConfig = Field(default_factory=ModelRouterConfig)

    # Legacy compatibility
    openapi_endpoint: str = "disabled"
    openapi_key: str = "password"
    openai_model: str = "dolphin-2.9-llama3-8b:Q6_K"
    secondary_openapi_endpoint: str = "disabled"
    secondary_openapi_key: str = "None"
    secondary_openai_model: str = "dolphin-llama3:8b"

    @classmethod
    def load(cls, path: str = "config/config.json") -> "JenniferConfig":
        """Load configuration from JSON file with migration support and ENV override."""
        config_path = Path(path)
        raw = {}

        if config_path.exists():
            with open(config_path, encoding='utf-8') as f:
                raw = json.load(f)

        # Migrate from old flat format if needed
        migrated_dict = cls._migrate_legacy_to_dict(raw)

        # Merge in decrypted secrets from the vault
        vault_secrets = vault.get_all_decrypted()
        if vault_secrets:
            # We recursively merge or just update top level if keys match Pydantic expectations
            # For BaseSettings, top-level keys like JENNIFER_DISCORD_TOKEN will be handled
            # but it's better to provide them in a way BaseSettings expects.
            # We'll update the migrated_dict with any keys that match.
            for k, v in vault_secrets.items():
                if k.startswith("JENNIFER_"):
                    # Strip prefix and handle nested keys if any, 
                    # but simple update is safest for now.
                    clean_k = k.replace("JENNIFER_", "").lower()
                    if clean_k in migrated_dict:
                        migrated_dict[clean_k] = v
                else:
                    migrated_dict[k] = v

        # BaseSettings automatically handles environment variable overrides
        config = cls(**migrated_dict)
        return config

    @classmethod
    def _migrate_legacy(cls, raw: dict) -> "JenniferConfig":
        """Legacy method for backward compatibility in tests."""
        return cls(**cls._migrate_legacy_to_dict(raw))

    @classmethod
    def _migrate_legacy_to_dict(cls, raw: dict) -> dict:
        """Migrate legacy flat config to new structure dict."""
        # Build fallback models list from numbered entries
        fallback_models = []
        for i in range(1, 10):
            key = f"OpenClawmodel{i}"
            if key in raw and raw[key]:
                fallback_models.append(raw[key])

        # Build endpoint lists
        model_endpoints = []
        for i in range(1, 10):
            key = f"OpenClawModelEndpoint{i}"
            if key in raw and raw[key]:
                model_endpoints.append(raw[key])

        embedding_endpoints = []
        for i in range(1, 10):
            key = f"OpenClawEmbeddingEndpoint{i}"
            if key in raw and raw[key]:
                embedding_endpoints.append(raw[key])

        return {
            "name": raw.get("Name", "Jennifer"),
            "personality": raw.get("Personality", ""),
            "appearance": raw.get("Appearance", ""),
            "log_level": raw.get("LogLevel", "INFO"),
            "log_level_debug": raw.get("LogLevel1", "DEBUG"),
            "typing_delay": raw.get("TypingDelay", 1),
            "history_length": raw.get("History_Length", 12000),
            "only_when_called": raw.get("OnlyWhenCalled", True),
            "respond_to_mentions": raw.get("RespondToMentions", True),
            "interaction_timeout": raw.get("InteractionTimeout", 60),
            "allow_dm_responses": raw.get("AllowDMResponses", True),
            "discord_token": raw.get("DiscordToken", ""),
            "allowed_channels": raw.get("AllowedChannels", []),
            "power_users": raw.get("Power_Users", []),
            "allowed_dm_users": raw.get("AllowedDMUsers", []),
            "bot_users": raw.get("bot_user", []),
            "ignored_users": raw.get("IgnoredUsers", []),
            "ignored_words": raw.get("IgnoredWords", []),
            "sd": {
                "backend": raw.get("SDBackend", "automatic1111"),
                "url": raw.get("SDURL", ""),
                "comfy_url": raw.get("SDComfyURL", ""),
                "invoke_url": raw.get("SDInvokeURL", ""),
                "model": raw.get("SDmodel", "cyberrealistic_classic40"),
                "clip_skip": raw.get("SDClipSkip", 0),
                "cfg_scale": raw.get("SDConfig", 7.0),
                "height": raw.get("SDHeight", 1024),
                "width": raw.get("SDWidth", 512),
                "negative_prompt": raw.get("SDNegativePrompt", ""),
                "positive_prompt_prefix": raw.get("SDPositivePrompt", ""),
                "sampler": raw.get("SDSampler", "DPM++ 2M"),
                "scheduler": raw.get("SDScheduler", "automatic"),
                "steps": raw.get("SDSteps", 20),
                "openai_prompt": raw.get("SDOpenAI", ""),
            },
            "openclaw": {
                "gateway": raw.get("OpenClawGateway", ""),
                "token": raw.get("OpenClawToken", ""),
                "device_token": raw.get("OpenClawDeviceToken", ""),
                "device_identity_path": raw.get("OpenClawDeviceIdentityPath", ""),
                "model": raw.get("OpenClawmodel", "chat"),
                "agent": raw.get("OpenClawAgent", ""),
                "async_mode": raw.get("OpenClawAsync", True),
                "bearer": raw.get("OpenClawBearer", "password"),
                "context_window": raw.get("OpenClawContextWindow", 10240),
                "embedding": raw.get("OpenClawEmbedding", "text-embedding-ada-002"),
                "embedding_dim": raw.get("OpenClawEmbeddingDim", 1024),
                "embedding_endpoint": raw.get("OpenClawEmbeddingEndpoint", ""),
                "embedding_endpoint_type": raw.get("OpenClawEmbeddingEndpointType", "openai"),
                "model_endpoint": raw.get("OpenClawModelEndpoint", ""),
                "model_endpoint_type": raw.get("OpenClawModelEndpointType", "openai"),
                "personality": raw.get("OpenClawPersonality", raw.get("OpenClawPersona", "")),
                "system_prompt": raw.get("OpenClawSystemPrompt", ""),
                "use_assistant_message": raw.get("OpenClawUseAssistantMessage", False),
                "stream": raw.get("OpenClawStream", False),
                "timeout": raw.get("OpenClawtimeout", 600),
                "primer": raw.get("OpenClawPrimer", ""),
                "persona": raw.get("OpenClawPersona", ""),
                "fallback_models": fallback_models,
                "embedding_endpoints": embedding_endpoints,
                "model_endpoints": model_endpoints,
            },
            "voice": {
                "silero_speaker": raw.get("SileroSpeaker", "en_107"),
                "openai_tts_backend": raw.get("OpenaiTTSBackend", "bark"),
                "openai_tts_voice_model": raw.get("OpenaiTTSVoiceModel", ""),
                "recognizer": raw.get("recognizer", "whisper"),
            },
            "video": {
                "backend": raw.get("VideoBackend", "zai"),
                "zai_api_key": raw.get("ZaiAPIKey", ""),
                "zai_api_endpoint": raw.get("ZaiAPIEndpoint", "https://api.z.ai/api/paas/v4"),
                "zai_model": raw.get("ZaiVideoModel", "CogVideoX-3"),
                "zai_resolution": raw.get("ZaiVideoResolution", "720p"),
                "zai_duration": raw.get("ZaiVideoDuration", 5),
                "framepack_url": raw.get("FramePackURL", "http://localhost:7860"),
                "framepack_model": raw.get("FramePackModel", "FramePack (Original)"),
                "framepack_steps": raw.get("FramePackSteps", 25),
                "framepack_width": raw.get("FramePackWidth", 640),
                "framepack_height": raw.get("FramePackHeight", 480),
                "framepack_video_length": raw.get("FramePackVideoLength", 4.0),
                "framepack_use_teacache": raw.get("FramePackUseTeaCache", True),
                "rate_limit_per_minute": raw.get("VideoRateLimit", 3),
                "max_prompt_length": raw.get("VideoMaxPromptLength", 500),
            },
            "model_router": {
                "highspeed_model": raw.get("ModelRouterHighspeed", "zai/glm-4.7-flash"),
                "highspeed_fallbacks": raw.get("ModelRouterHighspeedFallbacks", []),
                "intelligence_model": raw.get("ModelRouterIntelligence", "moonshot/kimi-k2.5"),
                "intelligence_fallbacks": raw.get("ModelRouterIntelligenceFallbacks", [
                    "zai/glm-4.7-flash",
                ]),
                "uncensored_model": raw.get("ModelRouterUncensored", "venice/venice-uncensored-role-play"),
                "uncensored_fallbacks": raw.get("ModelRouterUncensoredFallbacks", [
                    "venice/olafangensan-glm-4.7-flash-heretic",
                    "localai/Qwen3-14B-Nexa-Uncensored",
                ]),
            },
            "openapi_endpoint": raw.get("OpenAPIEndpoint", "disabled"),
            "openapi_key": raw.get("OpenAPIKey", "password"),
            "openai_model": raw.get("OpenaiModel", ""),
            "secondary_openapi_endpoint": raw.get("SecondaryOpenAPIEndpoint", "disabled"),
            "secondary_openapi_key": raw.get("SecondaryOpenAPIKey", "None"),
            "secondary_openai_model": raw.get("SecondaryOpenaiModel", ""),
        }

    def get_history_file_name(self) -> str:
        """Generate history filename based on bot name."""
        return f"{self.name}_message_histories.json"

    def is_power_user(self, user_id: int) -> bool:
        """Check if user is a power user."""
        return user_id in self.power_users

    def is_allowed_channel(self, channel_id: int) -> bool:
        """Check if channel is allowed."""
        return channel_id in self.allowed_channels

    def is_ignored_user(self, user_id: int) -> bool:
        """Check if user should be ignored."""
        return user_id in self.ignored_users

    # =========================================================================
    # Backward Compatibility - Dict-style access for legacy code
    # =========================================================================

    def __getitem__(self, key: str):
        """Allow dict-style access: config['key']"""
        # Map legacy keys to new attribute names
        key_map = {
            # Bot identity
            "Name": "name",
            "Personality": "personality",
            "Appearance": "appearance",
            # Logging
            "LogLevel": "log_level",
            "LogLevel1": "log_level_debug",
            # Behavior
            "TypingDelay": "typing_delay",
            "History_Length": "history_length",
            "OnlyWhenCalled": "only_when_called",
            "RespondToMentions": "respond_to_mentions",
            "InteractionTimeout": "interaction_timeout",
            "AllowDMResponses": "allow_dm_responses",
            # Discord
            "DiscordToken": "discord_token",
            "AllowedChannels": "allowed_channels",
            "Power_Users": "power_users",
            "AllowedDMUsers": "allowed_dm_users",
            "bot_user": "bot_users",
            "IgnoredUsers": "ignored_users",
            "IgnoredWords": "ignored_words",
            # SD Config
            "SDBackend": "sd.backend",
            "SDURL": "sd.url",
            "SDComfyURL": "sd.comfy_url",
            "SDInvokeURL": "sd.invoke_url",
            "SDmodel": "sd.model",
            "SDClipSkip": "sd.clip_skip",
            "SDConfig": "sd.cfg_scale",
            "SDHeight": "sd.height",
            "SDWidth": "sd.width",
            "SDNegativePrompt": "sd.negative_prompt",
            "SDPositivePrompt": "sd.positive_prompt_prefix",
            "SDSampler": "sd.sampler",
            "SDScheduler": "sd.scheduler",
            "SDSteps": "sd.steps",
            "SDOpenAI": "sd.openai_prompt",
            # OpenClaw Config
            "OpenClawGateway": "openclaw.gateway",
            "OpenClawToken": "openclaw.token",
            "OpenClawDeviceToken": "openclaw.device_token",
            "OpenClawDeviceIdentityPath": "openclaw.device_identity_path",
            "OpenClawmodel": "openclaw.model",
            "OpenClawAgent": "openclaw.agent",
            "OpenClawAsync": "openclaw.async_mode",
            "OpenClawBearer": "openclaw.bearer",
            "OpenClawContextWindow": "openclaw.context_window",
            "OpenClawEmbedding": "openclaw.embedding",
            "OpenClawEmbeddingDim": "openclaw.embedding_dim",
            "OpenClawEmbeddingEndpoint": "openclaw.embedding_endpoint",
            "OpenClawEmbeddingEndpointType": "openclaw.embedding_endpoint_type",
            "OpenClawModelEndpoint": "openclaw.model_endpoint",
            "OpenClawModelEndpointType": "openclaw.model_endpoint_type",
            "OpenClawPersonality": "openclaw.personality",
            "OpenClawSystemPrompt": "openclaw.system_prompt",
            "OpenClawUseAssistantMessage": "openclaw.use_assistant_message",
            "OpenClawPrimer": "openclaw.primer",
            "OpenClawPersona": "openclaw.persona",
            "OpenClawStream": "openclaw.stream",
            "OpenClawtimeout": "openclaw.timeout",
            # Voice Config
            "SileroSpeaker": "voice.silero_speaker",
            "OpenaiTTSBackend": "voice.openai_tts_backend",
            "OpenaiTTSVoiceModel": "voice.openai_tts_voice_model",
            "recognizer": "voice.recognizer",
            # Legacy OpenAI
            "OpenAPIEndpoint": "openapi_endpoint",
            "OpenAPIKey": "openapi_key",
            "OpenaiModel": "openai_model",
            "SecondaryOpenAPIEndpoint": "secondary_openapi_endpoint",
            "SecondaryOpenAPIKey": "secondary_openapi_key",
            "SecondaryOpenaiModel": "secondary_openai_model",
            # Video Config (new)
            "VideoBackend": "video.backend",
            "ZaiAPIKey": "video.zai_api_key",
            "ZaiAPIEndpoint": "video.zai_api_endpoint",
            "ZaiVideoModel": "video.zai_model",
            "ZaiVideoResolution": "video.zai_resolution",
            "ZaiVideoDuration": "video.zai_duration",
            "FramePackURL": "video.framepack_url",
            "FramePackModel": "video.framepack_model",
            "FramePackSteps": "video.framepack_steps",
            "FramePackWidth": "video.framepack_width",
            "FramePackHeight": "video.framepack_height",
            "FramePackVideoLength": "video.framepack_video_length",
            "FramePackUseTeaCache": "video.framepack_use_teacache",
            "VideoRateLimit": "video.rate_limit_per_minute",
            "VideoMaxPromptLength": "video.max_prompt_length",
        }

        if key in key_map:
            attr_path = key_map[key]
            # Handle nested attributes like "sd.url"
            value = self
            for part in attr_path.split("."):
                value = getattr(value, part)
            return value

        # Try direct attribute access
        if hasattr(self, key):
            return getattr(self, key)

        # Check extra config for dynamically set keys
        if hasattr(self, '_extra_config') and key in self._extra_config:
            return self._extra_config[key]

        raise KeyError(f"Config key not found: {key}")

    def get(self, key: str, default=None):
        """Allow dict-style .get() method: config.get('key', default)"""
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        """Allow 'in' operator: 'key' in config"""
        # Check _extra_config first
        if hasattr(self, '_extra_config') and key in self._extra_config:
            return True
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __setitem__(self, key: str, value):
        """Allow dict-style assignment: config['key'] = value"""
        # Map legacy keys to new attribute names
        key_map = {
            "OpenClawmodel": "openclaw.model",
            "OpenClawPrimer": "openclaw.primer",
            "SDmodel": "sd.model",
            "SDURL": "sd.url",
            "SDComfyURL": "sd.comfy_url",
            "SDInvokeURL": "sd.invoke_url",
            "SDBackend": "sd.backend",
        }

        if key in key_map:
            attr_path = key_map[key]
            # Handle nested attributes
            parts = attr_path.split(".")
            target = self
            for part in parts[:-1]:
                target = getattr(target, part)
            setattr(target, parts[-1], value)
        elif hasattr(self, key):
            setattr(self, key, value)
        else:
            # Store in a special dict for dynamic keys (like _routing)
            if not hasattr(self, '_extra_config'):
                object.__setattr__(self, '_extra_config', {})
            self._extra_config[key] = value

    def get_extra(self, key: str, default=None):
        """Get value from extra config storage."""
        if hasattr(self, '_extra_config'):
            return self._extra_config.get(key, default)
        return default


# Global config instance
_config: JenniferConfig | None = None


def load_config(path: str = "config/config.json") -> JenniferConfig:
    """Load and cache configuration."""
    global _config
    if _config is None:
        _config = JenniferConfig.load(path)
    return _config


def reload_config(path: str = "config/config.json") -> JenniferConfig:
    """Force reload configuration."""
    global _config
    _config = JenniferConfig.load(path)
    return _config


async def watch_config(
    path: str,
    callback: Callable[["JenniferConfig"], None],
    poll_interval: float = 5.0,
) -> None:
    """Watch a config file for changes and invoke callback on reload.

    Polls the file's mtime every *poll_interval* seconds.  On a detected
    change it attempts to reload and calls *callback(new_config)*.  Errors
    in the JSON / validation are logged but do not crash the watcher — the
    previous config stays active until a valid file is saved.

    Note: Discord token and queue-backend settings cannot be hot-applied
    (they require a full reconnect).  The callback in bot/client.py skips
    those fields intentionally.

    Args:
        path: Absolute or relative path to config.json.
        callback: Async-compatible callable that receives the new config.
        poll_interval: Seconds between mtime checks (default 5).
    """
    config_path = Path(path)
    warning_cooldown_seconds = 60.0
    last_warning_at = 0.0
    in_error_state = False

    def log_transient_warning(exc: Exception) -> None:
        nonlocal last_warning_at, in_error_state
        now = time.monotonic()
        in_error_state = True
        if now - last_warning_at >= warning_cooldown_seconds:
            logger.warning(f"Config watcher transient filesystem error for {path}: {exc}")
            last_warning_at = now

    try:
        last_mtime = config_path.stat().st_mtime
    except FileNotFoundError:
        logger.error(f"watch_config: file not found: {path}")
        return
    except OSError as exc:
        log_transient_warning(exc)
        last_mtime = None

    logger.info(f"Config watcher started for {path} (poll every {poll_interval}s)")

    while True:
        await asyncio.sleep(poll_interval)
        try:
            current_mtime = config_path.stat().st_mtime
        except asyncio.CancelledError:
            logger.info("Config watcher cancelled")
            break
        except FileNotFoundError as exc:
            log_transient_warning(exc)
            continue
        except OSError as exc:
            log_transient_warning(exc)
            continue

        try:
            if in_error_state:
                logger.info(f"Config watcher access restored for {path}")
                in_error_state = False

            if last_mtime is None:
                last_mtime = current_mtime
                continue

            if current_mtime == last_mtime:
                continue
            last_mtime = current_mtime
            logger.info(f"Config file changed — reloading {path}")
            try:
                new_config = JenniferConfig.load(path)
            except Exception as parse_err:
                logger.error(
                    f"Config reload failed (keeping previous config): {parse_err}"
                )
                continue

            # Update the global singleton so load_config() callers also see the change
            global _config
            _config = new_config

            try:
                result = callback(new_config)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as cb_err:
                logger.error(f"Config reload callback raised an error: {cb_err}")
        except asyncio.CancelledError:
            logger.info("Config watcher cancelled")
            break
        except Exception as e:
            logger.warning(f"Config watcher encountered an error: {e}")
