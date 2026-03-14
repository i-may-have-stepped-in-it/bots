"""
Image generation integrations module.

This module provides adapters for different image generation backends:
- Automatic1111 (Stable Diffusion WebUI)
- ComfyUI
- InvokeAI

Usage:
    from integrations.image_generation import create_adapter, PromptFormatter
    
    # Create adapter from config
    adapter = create_adapter_from_config(config)
    formatter = PromptFormatter(adapter)
    
    # Format a prompt
    payload = formatter.format_prompt("a beautiful sunset", upscale=False)
    
    # Get adapter info
    info = formatter.get_adapter_info()
    print(f"Using backend: {info['name']}")
"""

from integrations.image_generation.base_adapter import BaseImageAdapter
from integrations.image_generation.automatic1111_adapter import Automatic1111Adapter
from integrations.image_generation.comfyui_adapter import ComfyUIAdapter
from integrations.image_generation.invokeai_adapter import InvokeAIAdapter
from integrations.image_generation.prompt_formatter import PromptFormatter
from integrations.image_generation.adapter_factory import (
    create_adapter,
    create_adapter_from_config,
    get_adapter,
    get_available_adapters,
    register_adapter,
    is_backend_supported,
    get_backend_display_name,
)

__all__ = [
    # Base classes
    "BaseImageAdapter",
    # Adapters
    "Automatic1111Adapter",
    "ComfyUIAdapter",
    "InvokeAIAdapter",
    # Formatter
    "PromptFormatter",
    # Factory functions
    "create_adapter",
    "create_adapter_from_config",
    "get_adapter",
    "get_available_adapters",
    "register_adapter",
    "is_backend_supported",
    "get_backend_display_name",
]
