"""
Video generation module supporting multiple backends:
- Z.AI API (cloud): CogVideoX-3, ViduQ1, Vidu2
- FramePack (local): Self-hosted video generation

Usage:
    from utils.video_gen import VideoGenerator
    
    generator = VideoGenerator(config.video)
    video_path = await generator.generate("A cat playing piano", output_path="video.mp4")
"""

import asyncio
import base64
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import aiohttp

from core.config import VideoConfig

try:
    from utils.rate_limiter import TokenBucket
except ImportError:
    # Fallback if rate_limiter module not available
    import threading
    import time

    class TokenBucket:
        def __init__(self, capacity, refill_rate):
            self.capacity = capacity
            self.tokens = capacity
            self.refill_rate = refill_rate
            self.last_refill_time = time.time()
            self._lock = threading.Lock()

        def consume(self, tokens):
            with self._lock:
                current_time = time.time()
                elapsed = current_time - self.last_refill_time
                self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
                self.last_refill_time = current_time
                if tokens <= self.tokens:
                    self.tokens -= tokens
                    return True
                return False

logger = logging.getLogger(__name__)

# Module-level rate limiters keyed by backend config identity so that the
# generate_video() convenience function (which creates a new VideoGenerator
# per call) still enforces the shared limit.
_rate_limiters: dict[str, "TokenBucket"] = {}


def _get_shared_limiter(config: "VideoConfig") -> "TokenBucket":
    """Return a shared TokenBucket for the given config's rate limit."""
    key = f"{config.backend}:{config.rate_limit_per_minute}"
    if key not in _rate_limiters:
        rpm = config.rate_limit_per_minute
        _rate_limiters[key] = TokenBucket(capacity=rpm, refill_rate=rpm / 60.0)
    return _rate_limiters[key]


class VideoGenerationError(Exception):
    """Base exception for video generation errors."""
    pass


class RateLimitExceeded(VideoGenerationError):
    """Raised when rate limit is exceeded."""
    pass


class VideoBackend(ABC):
    """Abstract base class for video generation backends."""

    def __init__(self, config: VideoConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        output_path: str,
        image_path: str | None = None,
        **kwargs
    ) -> str:
        """Generate video and save to output_path. Returns the path to the generated video."""
        pass

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Check if the backend is healthy."""
        pass


class ZAIVideoBackend(VideoBackend):
    """Z.AI API video generation backend.
    
    Supports models:
    - CogVideoX-3: High quality, text/image to video
    - ViduQ1: Theatrical quality, 1080P
    - Vidu2: Fast delivery, 720P
    """

    def __init__(self, config: VideoConfig):
        super().__init__(config)
        self.api_endpoint = config.zai_api_endpoint.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {config.zai_api_key}",
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en",
        }
        # Map resolution to API format
        self.resolution_map = {
            "480p": "480x640",
            "720p": "720x1280",
            "1080p": "1080x1920",
        }

    async def generate(
        self,
        prompt: str,
        output_path: str,
        image_path: str | None = None,
        **kwargs
    ) -> str:
        """Generate video using Z.AI API.
        
        This is an async operation - we submit the job and poll for completion.
        """
        if not self.config.zai_api_key:
            raise VideoGenerationError("Z.AI API key not configured")

        # Submit generation request
        task_id = await self._submit_job(prompt, image_path, **kwargs)
        self.logger.info(f"Submitted video generation job: {task_id}")

        # Poll for completion
        video_url = await self._poll_for_completion(task_id)

        # Download the video
        await self._download_video(video_url, output_path)

        return output_path

    async def _submit_job(
        self,
        prompt: str,
        image_path: str | None = None,
        **kwargs
    ) -> str:
        """Submit video generation job to Z.AI API."""
        url = f"{self.api_endpoint}/video/generation"

        # Build payload
        payload = {
            "model": kwargs.get("model", self.config.zai_model),
            "prompt": prompt[:self.config.max_prompt_length],
        }

        # Add optional parameters
        resolution = kwargs.get("resolution", self.config.zai_resolution)
        if resolution in self.resolution_map:
            payload["resolution"] = self.resolution_map[resolution]

        duration = kwargs.get("duration", self.config.zai_duration)
        if duration:
            payload["duration"] = duration

        # Handle image input (img2vid)
        if image_path:
            image_data = await self._encode_image(image_path)
            payload["image_url"] = [image_data]

        async with aiohttp.ClientSession() as session, session.post(
            url,
            headers=self.headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise VideoGenerationError(
                    f"Z.AI API error: {response.status} - {error_text}"
                )

            data = await response.json()
            if "id" not in data:
                raise VideoGenerationError(f"No task ID in response: {data}")

            return data["id"]

    async def _encode_image(self, image_path: str) -> str:
        """Encode image to base64 for API upload."""
        path = Path(image_path)
        if not path.exists():
            raise VideoGenerationError(f"Image not found: {image_path}")

        # Check file size (max 5MB)
        if path.stat().st_size > 5 * 1024 * 1024:
            raise VideoGenerationError("Image too large (max 5MB)")

        # Offload blocking read to thread pool
        image_data = await asyncio.to_thread(path.read_bytes)

        # Determine MIME type
        mime_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"

        b64_data = base64.b64encode(image_data).decode("utf-8")
        return f"data:{mime_type};base64,{b64_data}"

    async def _poll_for_completion(self, task_id: str, max_wait: int = 600) -> str:
        """Poll for task completion and return video URL."""
        url = f"{self.api_endpoint}/video/result"
        start_time = time.time()
        poll_interval = 5  # seconds

        async with aiohttp.ClientSession() as session:
            while time.time() - start_time < max_wait:
                async with session.get(
                    url,
                    headers=self.headers,
                    params={"id": task_id},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise VideoGenerationError(
                            f"Poll error: {response.status} - {error_text}"
                        )

                    data = await response.json()
                    status = data.get("status", "unknown")

                    if status == "success":
                        video_url = data.get("video_url")
                        if not video_url:
                            raise VideoGenerationError("No video URL in success response")
                        return video_url
                    elif status == "failed":
                        error_msg = data.get("error", "Unknown error")
                        raise VideoGenerationError(f"Generation failed: {error_msg}")
                    elif status in ("processing", "queued"):
                        self.logger.debug(f"Task {task_id} status: {status}, waiting...")
                    else:
                        self.logger.warning(f"Unknown status: {status}")

                await asyncio.sleep(poll_interval)

            raise VideoGenerationError(f"Timeout waiting for task {task_id}")

    async def _download_video(self, video_url: str, output_path: str) -> None:
        """Download video from URL to local path."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                video_url,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                if response.status != 200:
                    raise VideoGenerationError(
                        f"Download failed: {response.status}"
                    )

                # Ensure output directory exists
                await asyncio.to_thread(
                    Path(output_path).parent.mkdir, parents=True, exist_ok=True  # type: ignore[arg-type]
                )

                # Stream download — collect chunks then write in one thread call
                chunks = []
                async for chunk in response.content.iter_chunked(8192):
                    chunks.append(chunk)
                await asyncio.to_thread(
                    Path(output_path).write_bytes, b"".join(chunks)
                )

        self.logger.info(f"Downloaded video to: {output_path}")

    async def health_check(self) -> dict[str, Any]:
        """Check Z.AI API health."""
        if not self.config.zai_api_key:
            return {"healthy": False, "error": "API key not configured"}

        try:
            # Try to get available models (lightweight check)
            url = f"{self.api_endpoint}/models"
            async with aiohttp.ClientSession() as session, session.get(
                url,
                headers={"Authorization": f"Bearer {self.config.zai_api_key}"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    return {"healthy": True, "status": "available"}
                else:
                    return {
                        "healthy": False,
                        "status": f"HTTP {response.status}"
                    }
        except Exception as e:
            return {"healthy": False, "error": str(e)}


class FramePackBackend(VideoBackend):
    """FramePack local video generation backend.
    
    Communicates with FramePack's Gradio API.
    """

    def __init__(self, config: VideoConfig):
        super().__init__(config)
        self.api_url = config.framepack_url.rstrip("/")

    async def generate(
        self,
        prompt: str,
        output_path: str,
        image_path: str | None = None,
        **kwargs
    ) -> str:
        """Generate video using local FramePack instance."""
        # Import gradio client
        try:
            from gradio_client import Client, handle_file
        except ImportError:
            raise VideoGenerationError(
                "gradio_client not installed. Run: pip install gradio_client"
            )

        # Run gradio client in thread pool (it's blocking)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,  # Default executor
            self._generate_sync,
            prompt,
            output_path,
            image_path,
            kwargs
        )

    def _generate_sync(
        self,
        prompt: str,
        output_path: str,
        image_path: str | None = None,
        kwargs: dict = None
    ) -> str:
        """Synchronous generation using Gradio client."""
        from gradio_client import Client, handle_file

        kwargs = kwargs or {}
        client = Client(self.api_url)

        # Prepare parameters based on FramePack's API
        params = {
            "prompt": prompt[:self.config.max_prompt_length],
            "model": kwargs.get("model", self.config.framepack_model),
            "steps": kwargs.get("steps", self.config.framepack_steps),
            "width": kwargs.get("width", self.config.framepack_width),
            "height": kwargs.get("height", self.config.framepack_height),
            "video_length": kwargs.get(
                "video_length",
                self.config.framepack_video_length
            ),
            "use_teacache": kwargs.get(
                "use_teacache",
                self.config.framepack_use_teacache
            ),
        }

        # Handle image input
        if image_path:
            params["image"] = handle_file(image_path)

        try:
            # Call FramePack API
            result = client.predict(**params)

            # Result is typically a tuple of (video_path, ...)
            if isinstance(result, (tuple, list)):
                generated_video_path = result[0]
            else:
                generated_video_path = result

            # Copy to output path
            import shutil
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(generated_video_path, output_path)

            return output_path

        except Exception as e:
            raise VideoGenerationError(f"FramePack generation failed: {e}")

    async def health_check(self) -> dict[str, Any]:
        """Check FramePack API health."""
        try:
            async with aiohttp.ClientSession() as session, session.get(
                f"{self.api_url}/",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    return {"healthy": True, "status": "available"}
                else:
                    return {
                        "healthy": False,
                        "status": f"HTTP {response.status}"
                    }
        except Exception as e:
            return {"healthy": False, "error": str(e)}


class VideoGenerator:
    """Main video generation interface.
    
    Handles backend selection, rate limiting, and queue management.
    """

    def __init__(self, config: VideoConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

        # Initialize backend
        if config.backend == "zai":
            self.backend = ZAIVideoBackend(config)
        elif config.backend == "framepack":
            self.backend = FramePackBackend(config)
        else:
            raise VideoGenerationError(f"Unknown backend: {config.backend}")

        # Shared rate limiter — survives VideoGenerator re-creation
        self.rate_limiter = _get_shared_limiter(config)

        self.logger.info(
            f"VideoGenerator initialized with backend: {config.backend}"
        )

    async def generate(
        self,
        prompt: str,
        output_dir: str = "outputs/videos",
        user_id: int | None = None,
        image_path: str | None = None,
        **kwargs
    ) -> str:
        """Generate video with rate limiting.
        
        Args:
            prompt: Text description of the video to generate
            output_dir: Directory to save the video
            user_id: Discord user ID for personalized generation
            image_path: Optional image to use as starting frame (img2vid)
            **kwargs: Additional parameters for the backend
            
        Returns:
            Path to the generated video file
        """
        # Check rate limit
        if not self.rate_limiter.consume(1):
            raise RateLimitExceeded(
                f"Rate limit exceeded. Max {self.config.rate_limit_per_minute} "
                f"videos per minute."
            )

        # Sanitize prompt
        prompt = prompt.strip()
        if len(prompt) > self.config.max_prompt_length:
            prompt = prompt[:self.config.max_prompt_length]

        # Generate unique filename
        timestamp = int(time.time())
        user_suffix = f"_user{user_id}" if user_id else ""
        safe_prompt = "".join(c for c in prompt[:30] if c.isalnum() or c == " ")
        safe_prompt = safe_prompt.replace(" ", "_")

        filename = f"video_{timestamp}{user_suffix}_{safe_prompt}.mp4"
        output_path = str(Path(output_dir) / filename)

        self.logger.info(f"Generating video: {prompt[:50]}...")

        try:
            result_path = await self.backend.generate(
                prompt=prompt,
                output_path=output_path,
                image_path=image_path,
                **kwargs
            )
            self.logger.info(f"Video generated: {result_path}")
            return result_path
        except Exception as e:
            self.logger.error(f"Video generation failed: {e}")
            raise

    async def health_check(self) -> dict[str, Any]:
        """Check if video generation is available."""
        return await self.backend.health_check()

    def get_backend_info(self) -> dict[str, str]:
        """Get information about the current backend."""
        if isinstance(self.backend, ZAIVideoBackend):
            return {
                "backend": "Z.AI API",
                "model": self.config.zai_model,
                "endpoint": self.config.zai_api_endpoint,
            }
        elif isinstance(self.backend, FramePackBackend):
            return {
                "backend": "FramePack (Local)",
                "url": self.config.framepack_url,
                "model": self.config.framepack_model,
            }
        return {"backend": "unknown"}


# Convenience function for direct usage
async def generate_video(
    config: VideoConfig,
    prompt: str,
    output_dir: str = "outputs/videos",
    user_id: int | None = None,
    image_path: str | None = None,
    **kwargs
) -> str:
    """Generate video using the configured backend.
    
    This is a convenience function for one-off generations.
    For repeated use, create a VideoGenerator instance.
    """
    generator = VideoGenerator(config)
    return await generator.generate(
        prompt=prompt,
        output_dir=output_dir,
        user_id=user_id,
        image_path=image_path,
        **kwargs
    )


async def check_video_health(config: VideoConfig) -> dict[str, Any]:
    """Check video generation backend health."""
    try:
        generator = VideoGenerator(config)
        return await generator.health_check()
    except Exception as e:
        return {"healthy": False, "error": str(e)}
