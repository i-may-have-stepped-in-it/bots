"""
Pydantic-based configuration management for Jennifer.
Replaces the messy dict-based config with validated, typed settings.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Callable, List, Optional
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class SDConfig(BaseModel):
    """Stable Diffusion configuration."""
    backend: str = "automatic1111"  # automatic1111, comfyui, invokeai
    url: str = Field(default_factory=lambda: os.getenv("SD_URL", ""))
    comfy_url: str = Field(default_factory=lambda: os.getenv("SD_COMFY_URL", ""))
    invoke_url: str = Field(default_factory=lambda: os.getenv("SD_INVOKE_URL", ""))
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
    gateway: str = Field(default_factory=lambda: os.getenv("OPENCLAW_GATEWAY", ""))
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
    embedding_endpoint: str = Field(default_factory=lambda: os.getenv("OPENCLAW_EMBEDDING_ENDPOINT", ""))
    embedding_endpoint_type: str = "openai"
    model_endpoint: str = Field(default_factory=lambda: os.getenv("OPENCLAW_MODEL_ENDPOINT", ""))
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
    fallback_models: List[str] = Field(default_factory=list)
    
    # Legacy endpoint lists (for compatibility)
    embedding_endpoints: List[str] = Field(default_factory=list)
    model_endpoints: List[str] = Field(default_factory=list)


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
    framepack_url: str = "http://localhost:7860"  # Gradio API endpoint
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
    highspeed_fallbacks: List[str] = Field(default_factory=list)
    
    # Intelligence tier: Capable models for complex tasks
    intelligence_model: str = "moonshot/kimi-k2.5"
    intelligence_fallbacks: List[str] = Field(default_factory=lambda: [
        "zai/glm-4.7-flash",
    ])
    
    # Uncensored tier: Models for NSFW/sensitive content
    uncensored_model: str = "venice/venice-uncensored-role-play"
    uncensored_fallbacks: List[str] = Field(default_factory=lambda: [
        "venice/olafangensan-glm-4.7-flash-heretic",
        "localai/Qwen3-14B-Nexa-Uncensored",
    ])


class JenniferConfig(BaseModel):
    """Main Jennifer bot configuration."""
    # Bot identity
    name: str = "Jennifer"
    personality: str = ""
    appearance: str = ""
    
    # Logging
    log_level: str = "INFO"  # Can be overridden via LOG_LEVEL env var
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
    allowed_channels: List[int] = Field(default_factory=list)
    power_users: List[int] = Field(default_factory=list)
    allowed_dm_users: List[int] = Field(default_factory=list)
    bot_users: List[int] = Field(default_factory=list)
    ignored_users: List[int] = Field(default_factory=list)
    ignored_words: List[str] = Field(default_factory=list)
    
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
        """Load configuration from JSON file with migration support."""
        config_path = Path(path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        
        # Migrate from old flat format to new nested format
        return cls._migrate_legacy(raw)
    
    @classmethod
    def _migrate_legacy(cls, raw: dict) -> "JenniferConfig":
        """Migrate legacy flat config to new structure."""
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
        
        return cls(
            name=raw.get("Name", "Jennifer"),
            personality=raw.get("Personality", ""),
            appearance=raw.get("Appearance", ""),
            log_level=os.getenv("LOG_LEVEL", raw.get("LogLevel", "INFO")),
            log_level_debug=raw.get("LogLevel1", "DEBUG"),
            typing_delay=raw.get("TypingDelay", 1),
            history_length=raw.get("History_Length", 12000),
            only_when_called=raw.get("OnlyWhenCalled", True),
            respond_to_mentions=raw.get("RespondToMentions", True),
            interaction_timeout=raw.get("InteractionTimeout", 60),
            allow_dm_responses=raw.get("AllowDMResponses", True),
            discord_token=raw.get("DiscordToken", ""),
            allowed_channels=raw.get("AllowedChannels", []),
            power_users=raw.get("Power_Users", []),
            allowed_dm_users=raw.get("AllowedDMUsers", []),
            bot_users=raw.get("bot_user", []),
            ignored_users=raw.get("IgnoredUsers", []),
            ignored_words=raw.get("IgnoredWords", []),
            sd=SDConfig(
                backend=raw.get("SDBackend", "automatic1111"),
                url=raw.get("SDURL", os.getenv("SD_URL", "")),
                comfy_url=raw.get("SDComfyURL", os.getenv("SD_COMFY_URL", "")),
                invoke_url=raw.get("SDInvokeURL", os.getenv("SD_INVOKE_URL", "")),
                model=raw.get("SDmodel", "cyberrealistic_classic40"),
                clip_skip=raw.get("SDClipSkip", 0),
                cfg_scale=raw.get("SDConfig", 7.0),
                height=raw.get("SDHeight", 1024),
                width=raw.get("SDWidth", 512),
                negative_prompt=raw.get("SDNegativePrompt", ""),
                positive_prompt_prefix=raw.get("SDPositivePrompt", ""),
                sampler=raw.get("SDSampler", "DPM++ 2M"),
                scheduler=raw.get("SDScheduler", "automatic"),
                steps=raw.get("SDSteps", 20),
                openai_prompt=raw.get("SDOpenAI", ""),
            ),
            openclaw=OpenClawConfig(
                gateway=raw.get("OpenClawGateway", os.getenv("OPENCLAW_GATEWAY", "")),
                token=raw.get("OpenClawToken", ""),
                device_token=raw.get("OpenClawDeviceToken", ""),
                device_identity_path=raw.get("OpenClawDeviceIdentityPath", ""),
                model=raw.get("OpenClawmodel", "chat"),
                agent=raw.get("OpenClawAgent", ""),
                async_mode=raw.get("OpenClawAsync", True),
                bearer=raw.get("OpenClawBearer", "password"),
                context_window=raw.get("OpenClawContextWindow", 10240),
                embedding=raw.get("OpenClawEmbedding", "text-embedding-ada-002"),
                embedding_dim=raw.get("OpenClawEmbeddingDim", 1024),
                embedding_endpoint=raw.get("OpenClawEmbeddingEndpoint", os.getenv("OPENCLAW_EMBEDDING_ENDPOINT", "")),
                embedding_endpoint_type=raw.get("OpenClawEmbeddingEndpointType", "openai"),
                model_endpoint=raw.get("OpenClawModelEndpoint", os.getenv("OPENCLAW_MODEL_ENDPOINT", "")),
                model_endpoint_type=raw.get("OpenClawModelEndpointType", "openai"),
                personality=raw.get("OpenClawPersonality", raw.get("OpenClawPersona", "")),
                system_prompt=raw.get("OpenClawSystemPrompt", ""),
                use_assistant_message=raw.get("OpenClawUseAssistantMessage", False),
                stream=raw.get("OpenClawStream", False),
                timeout=raw.get("OpenClawtimeout", 600),
                primer=raw.get("OpenClawPrimer", ""),
                persona=raw.get("OpenClawPersona", ""),
                fallback_models=fallback_models,
                embedding_endpoints=embedding_endpoints,
                model_endpoints=model_endpoints,
            ),
            voice=VoiceConfig(
                silero_speaker=raw.get("SileroSpeaker", "en_107"),
                openai_tts_backend=raw.get("OpenaiTTSBackend", "bark"),
                openai_tts_voice_model=raw.get("OpenaiTTSVoiceModel", ""),
                recognizer=raw.get("recognizer", "whisper"),
            ),
            video=VideoConfig(
                backend=raw.get("VideoBackend", "zai"),
                zai_api_key=raw.get("ZaiAPIKey", ""),
                zai_api_endpoint=raw.get("ZaiAPIEndpoint", "https://api.z.ai/api/paas/v4"),
                zai_model=raw.get("ZaiVideoModel", "CogVideoX-3"),
                zai_resolution=raw.get("ZaiVideoResolution", "720p"),
                zai_duration=raw.get("ZaiVideoDuration", 5),
                framepack_url=raw.get("FramePackURL", "http://localhost:7860"),
                framepack_model=raw.get("FramePackModel", "FramePack (Original)"),
                framepack_steps=raw.get("FramePackSteps", 25),
                framepack_width=raw.get("FramePackWidth", 640),
                framepack_height=raw.get("FramePackHeight", 480),
                framepack_video_length=raw.get("FramePackVideoLength", 4.0),
                framepack_use_teacache=raw.get("FramePackUseTeaCache", True),
                rate_limit_per_minute=raw.get("VideoRateLimit", 3),
                max_prompt_length=raw.get("VideoMaxPromptLength", 500),
            ),
            model_router=ModelRouterConfig(
                highspeed_model=raw.get("ModelRouterHighspeed", "zai/glm-4.7-flash"),
                highspeed_fallbacks=raw.get("ModelRouterHighspeedFallbacks", []),
                intelligence_model=raw.get("ModelRouterIntelligence", "moonshot/kimi-k2.5"),
                intelligence_fallbacks=raw.get("ModelRouterIntelligenceFallbacks", [
                    "zai/glm-4.7-flash",
                ]),
                uncensored_model=raw.get("ModelRouterUncensored", "venice/venice-uncensored-role-play"),
                uncensored_fallbacks=raw.get("ModelRouterUncensoredFallbacks", [
                    "venice/olafangensan-glm-4.7-flash-heretic",
                    "localai/Qwen3-14B-Nexa-Uncensored",
                ]),
            ),
            openapi_endpoint=raw.get("OpenAPIEndpoint", "disabled"),
            openapi_key=raw.get("OpenAPIKey", "password"),
            openai_model=raw.get("OpenaiModel", ""),
            secondary_openapi_endpoint=raw.get("SecondaryOpenAPIEndpoint", "disabled"),
            secondary_openapi_key=raw.get("SecondaryOpenAPIKey", "None"),
            secondary_openai_model=raw.get("SecondaryOpenaiModel", ""),
        )
    
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
_config: Optional[JenniferConfig] = None


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
    try:
        last_mtime = config_path.stat().st_mtime
    except FileNotFoundError:
        logger.error(f"watch_config: file not found: {path}")
        return

    logger.info(f"Config watcher started for {path} (poll every {poll_interval}s)")

    while True:
        await asyncio.sleep(poll_interval)
        try:
            current_mtime = config_path.stat().st_mtime
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
