\"\"\"
Mock AI providers for integration and unit testing.
Enables offline development and CI/CD without API dependencies.
\"\"\"

import asyncio
from typing import Dict, Any, List, Optional
from integrations.ai_interface import TextAIProvider, ImageAIProvider, VideoAIProvider, AIResponse

class MockTextProvider(TextAIProvider):
    \"\"\"Mock LLM provider.\"\"\"
    async def generate(self, request):
        return AIResponse(content=\"Mock LLM response for: \" + request.prompt)
    
    async def chat(self, messages, **kwargs):
        return AIResponse(content=\"Mock LLM chat response\")
    
    async def health_check(self):
        return True

class MockImageProvider(ImageAIProvider):
    \"\"\"Mock Image provider.\"\"\"
    async def generate(self, request):
        return AIResponse(content=b\"mock_image_bytes\")
    
    async def generate_image(self, prompt, **kwargs):
        return AIResponse(content=b\"mock_image_bytes\")
    
    async def health_check(self):
        return True

class MockVideoProvider(VideoAIProvider):
    \"\"\"Mock Video provider.\"\"\"
    async def generate(self, request):
        return AIResponse(content=\"https://mock.zai.api/video.mp4\")
    
    async def generate_video(self, prompt, **kwargs):
        return AIResponse(content=\"https://mock.zai.api/video.mp4\")
    
    async def health_check(self):
        return True
