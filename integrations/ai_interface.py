"""
Unified AI Provider Interface for Jennifer Bot.
Provides a consistent abstraction for text, image, and video generation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AIRequest:
    """Common request parameters for all AI modalities."""

    prompt: str
    user_id: Optional[str] = None
    options: Optional[Dict[str, Any]] = None


@dataclass
class AIResponse:
    """Common response format for all AI modalities."""

    content: Any
    raw_response: Any = None
    provider_metadata: Optional[Dict[str, Any]] = None


class BaseAIProvider(ABC):
    """Base class for all AI service integrations."""

    @abstractmethod
    async def generate(self, request: AIRequest) -> AIResponse:
        """Execute the AI generation task."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the provider is reachable and functional."""


class TextAIProvider(BaseAIProvider):
    """Interface for text generation."""

    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> AIResponse:
        """Execute a chat completion request."""


class ImageAIProvider(BaseAIProvider):
    """Interface for image generation."""

    @abstractmethod
    async def generate_image(self, prompt: str, **kwargs) -> AIResponse:
        """Generate an image from a prompt."""


class VideoAIProvider(BaseAIProvider):
    """Interface for video generation."""

    @abstractmethod
    async def generate_video(self, prompt: str, **kwargs) -> AIResponse:
        """Generate a video from a prompt."""
