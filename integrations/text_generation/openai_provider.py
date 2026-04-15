"""
OpenAI-compatible Text Generation Provider.
Works with both official OpenAI and LocalAI/OpenClaw endpoints.
"""

from typing import Dict, Any, List, Optional
import logging
from openai import AsyncOpenAI
from circuitbreaker import circuit

from integrations.ai_interface import TextAIProvider, AIRequest, AIResponse

logger = logging.getLogger(__name__)

class OpenAITextProvider(TextAIProvider):
    """Provider for OpenAI-compatible chat endpoints."""
    
    def __init__(self, base_url: str, api_key: str, default_model: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.default_model = default_model
        
    async def generate(self, request: AIRequest) -> AIResponse:
        """Fallback for simple prompt generation."""
        messages = [{"role": "user", "content": request.prompt}]
        return await self.chat(messages, **(request.options or {}))

    @circuit(failure_threshold=5, recovery_timeout=60)
    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> AIResponse:
        """Execute chat completion with circuit breaker."""
        model = kwargs.get("model", self.default_model)
        try:

            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                **{k: v for k, v in kwargs.items() if k != "model"}
            )
            content = response.choices[0].message.content
            return AIResponse(
                content=content,
                raw_response=response,
                provider_metadata={"model": model, "usage": getattr(response, "usage", None)}
            )
        except Exception as e:
            logger.error(f"OpenAI chat error (model={model}): {e}")
            raise

    async def health_check(self) -> bool:
        """Verify endpoint connectivity by fetching models."""
        try:
            await self.client.models.list()
            return True
        except Exception as e:
            logger.warning(f"OpenAITextProvider health check failed: {e}")
            return False
