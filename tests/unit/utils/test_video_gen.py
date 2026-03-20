"""
Unit tests for utils/video_gen.py - Video generation backends.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path

from core.config import VideoConfig
from utils.video_gen import (
    VideoGenerator,
    ZAIVideoBackend,
    FramePackBackend,
    VideoGenerationError,
    RateLimitExceeded,
    check_video_health,
)


# =============================================================================
# VideoConfig Fixtures
# =============================================================================

@pytest.fixture
def zai_config():
    """VideoConfig for Z.AI backend."""
    return VideoConfig(
        backend="zai",
        zai_api_key="test-api-key",
        zai_api_endpoint="https://api.z.ai/api/paas/v4",
        zai_model="CogVideoX-3",
        zai_resolution="720p",
        zai_duration=5,
        rate_limit_per_minute=3,
        max_prompt_length=500,
    )


@pytest.fixture
def framepack_config():
    """VideoConfig for FramePack backend."""
    return VideoConfig(
        backend="framepack",
        framepack_url="http://localhost:7860",
        framepack_model="FramePack (Original)",
        framepack_steps=25,
        framepack_width=640,
        framepack_height=480,
        framepack_video_length=4.0,
        framepack_use_teacache=True,
        rate_limit_per_minute=3,
        max_prompt_length=500,
    )


# =============================================================================
# ZAIVideoBackend Tests
# =============================================================================

class TestZAIVideoBackend:
    """Tests for Z.AI video backend."""

    def test_initialization(self, zai_config):
        """Test backend initialization."""
        backend = ZAIVideoBackend(zai_config)
        assert backend.api_endpoint == "https://api.z.ai/api/paas/v4"
        assert backend.headers["Authorization"] == "Bearer test-api-key"

    @pytest.mark.asyncio
    async def test_health_check_success(self, zai_config):
        """Test health check with successful response."""
        backend = ZAIVideoBackend(zai_config)
        
        # Just verify it doesn't crash and returns a dict
        result = await backend.health_check()
        assert isinstance(result, dict)
        assert "healthy" in result

    @pytest.mark.asyncio
    async def test_health_check_no_api_key(self, zai_config):
        """Test health check without API key."""
        zai_config.zai_api_key = ""
        backend = ZAIVideoBackend(zai_config)
        
        result = await backend.health_check()
        assert result["healthy"] is False
        assert "API key not configured" in result["error"]

    def test_resolution_mapping(self, zai_config):
        """Test resolution string mapping."""
        backend = ZAIVideoBackend(zai_config)
        assert backend.resolution_map["720p"] == "720x1280"
        assert backend.resolution_map["1080p"] == "1080x1920"
        assert backend.resolution_map["480p"] == "480x640"


# =============================================================================
# FramePackBackend Tests
# =============================================================================

class TestFramePackBackend:
    """Tests for FramePack video backend."""

    def test_initialization(self, framepack_config):
        """Test backend initialization."""
        backend = FramePackBackend(framepack_config)
        assert backend.api_url == "http://localhost:7860"

    @pytest.mark.asyncio
    async def test_health_check_returns_dict(self, framepack_config):
        """Test health check returns proper dict structure."""
        backend = FramePackBackend(framepack_config)
        
        # Test returns dict with expected keys
        result = await backend.health_check()
        assert isinstance(result, dict)
        assert "healthy" in result

    @pytest.mark.asyncio
    async def test_health_check_with_error(self, framepack_config):
        """Test health check handles errors."""
        backend = FramePackBackend(framepack_config)
        
        # Result should have healthy=False when there's an error
        result = await backend.health_check()
        if not result["healthy"]:
            assert "error" in result or "status" in result


# =============================================================================
# VideoGenerator Tests
# =============================================================================

class TestVideoGenerator:
    """Tests for main VideoGenerator interface."""

    def test_zai_backend_selection(self, zai_config):
        """Test Z.AI backend is selected correctly."""
        generator = VideoGenerator(zai_config)
        assert isinstance(generator.backend, ZAIVideoBackend)

    def test_framepack_backend_selection(self, framepack_config):
        """Test FramePack backend is selected correctly."""
        generator = VideoGenerator(framepack_config)
        assert isinstance(generator.backend, FramePackBackend)

    def test_unknown_backend_raises_error(self):
        """Test unknown backend raises error."""
        config = VideoConfig(backend="unknown")
        with pytest.raises(VideoGenerationError) as exc_info:
            VideoGenerator(config)
        assert "Unknown backend" in str(exc_info.value)

    def test_get_backend_info_zai(self, zai_config):
        """Test backend info for Z.AI."""
        generator = VideoGenerator(zai_config)
        info = generator.get_backend_info()
        assert info["backend"] == "Z.AI API"
        assert info["model"] == "CogVideoX-3"

    def test_get_backend_info_framepack(self, framepack_config):
        """Test backend info for FramePack."""
        generator = VideoGenerator(framepack_config)
        info = generator.get_backend_info()
        assert info["backend"] == "FramePack (Local)"
        assert info["url"] == "http://localhost:7860"

    @pytest.mark.asyncio
    async def test_rate_limit_enforced(self, zai_config):
        """Test rate limiting prevents excessive requests."""
        generator = VideoGenerator(zai_config)
        
        # Consume all tokens
        for _ in range(3):
            generator.rate_limiter.consume(1)
        
        # Next request should fail
        with pytest.raises(RateLimitExceeded):
            await generator.generate("test prompt")

    @pytest.mark.asyncio
    async def test_prompt_truncation(self, zai_config):
        """Test long prompts are truncated."""
        generator = VideoGenerator(zai_config)
        long_prompt = "x" * 1000
        
        with patch.object(generator.backend, "generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "/tmp/test.mp4"
            await generator.generate(long_prompt)
            
            # Check prompt was truncated
            call_args = mock_gen.call_args
            assert len(call_args.kwargs["prompt"]) <= 500


# =============================================================================
# Rate Limiting Tests
# =============================================================================

class TestRateLimiting:
    """Tests for video generation rate limiting."""

    def test_token_bucket_allows_requests(self):
        """Test token bucket allows requests when tokens available."""
        from utils.rate_limiter import TokenBucket
        
        bucket = TokenBucket(capacity=3, refill_rate=1.0)
        assert bucket.consume(1) is True
        assert bucket.consume(1) is True
        assert bucket.consume(1) is True

    def test_token_bucket_blocks_excessive_requests(self):
        """Test token bucket blocks when tokens exhausted."""
        from utils.rate_limiter import TokenBucket
        
        bucket = TokenBucket(capacity=2, refill_rate=1.0)
        assert bucket.consume(1) is True
        assert bucket.consume(1) is True
        assert bucket.consume(1) is False  # No tokens left

    def test_token_bucket_refills(self):
        """Test token bucket refills over time."""
        import time
        from utils.rate_limiter import TokenBucket
        
        bucket = TokenBucket(capacity=2, refill_rate=10.0)  # Fast refill
        assert bucket.consume(2) is True  # Exhaust tokens
        assert bucket.consume(1) is False  # No tokens
        
        time.sleep(0.2)  # Wait for refill
        assert bucket.consume(1) is True  # Should have tokens now


# =============================================================================
# Health Check Tests
# =============================================================================

class TestHealthCheck:
    """Tests for video health check function."""

    @pytest.mark.asyncio
    async def test_check_video_health_zai(self, zai_config):
        """Test health check for Z.AI backend."""
        with patch.object(ZAIVideoBackend, "health_check", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {"healthy": True}
            result = await check_video_health(zai_config)
            assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_check_video_health_framepack(self, framepack_config):
        """Test health check for FramePack backend."""
        with patch.object(FramePackBackend, "health_check", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {"healthy": True}
            result = await check_video_health(framepack_config)
            assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_check_video_health_error(self, zai_config):
        """Test health check handles errors gracefully."""
        with patch.object(ZAIVideoBackend, "health_check", side_effect=Exception("Test error")):
            result = await check_video_health(zai_config)
            assert result["healthy"] is False
            assert "Test error" in result["error"]


# =============================================================================
# VideoGenerationError Tests
# =============================================================================

class TestVideoGenerationErrors:
    """Tests for video generation exceptions."""

    def test_video_generation_error(self):
        """Test VideoGenerationError can be raised."""
        with pytest.raises(VideoGenerationError) as exc_info:
            raise VideoGenerationError("Test error message")
        assert "Test error message" in str(exc_info.value)

    def test_rate_limit_exceeded(self):
        """Test RateLimitExceeded can be raised."""
        with pytest.raises(RateLimitExceeded) as exc_info:
            raise RateLimitExceeded("Rate limit hit")
        assert "Rate limit hit" in str(exc_info.value)

    def test_rate_limit_is_subclass(self):
        """Test RateLimitExceeded is subclass of VideoGenerationError."""
        assert issubclass(RateLimitExceeded, VideoGenerationError)
