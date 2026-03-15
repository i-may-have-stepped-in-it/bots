"""
Adapter Factory for image generation backends.

This module provides a factory pattern for creating image generation adapters
based on configuration. It supports Automatic1111, ComfyUI, and InvokeAI backends.
"""

import logging
from typing import Dict, Any, Type

from integrations.image_generation.base_adapter import BaseImageAdapter
from integrations.image_generation.automatic1111_adapter import Automatic1111Adapter
from integrations.image_generation.comfyui_adapter import ComfyUIAdapter
from integrations.image_generation.invokeai_adapter import InvokeAIAdapter


# Registry of available adapters
ADAPTER_REGISTRY: Dict[str, Type[BaseImageAdapter]] = {
    "automatic1111": Automatic1111Adapter,
    "auto": Automatic1111Adapter,  # Alias
    "a1111": Automatic1111Adapter,  # Alias
    "webui": Automatic1111Adapter,  # Alias
    "comfyui": ComfyUIAdapter,
    "comfy": ComfyUIAdapter,  # Alias
    "invokeai": InvokeAIAdapter,
    "invoke": InvokeAIAdapter,  # Alias
}


def get_available_adapters() -> list:
    """
    Get a list of available adapter names.
    
    Returns:
        List of registered adapter names
    """
    return list(ADAPTER_REGISTRY.keys())


def create_adapter(
    backend: str,
    config: Dict[str, Any]
) -> BaseImageAdapter:
    """
    Create an image generation adapter based on the backend name.
    
    Args:
        backend: The name of the backend to use (e.g., "automatic1111", "comfyui", "invokeai")
        config: Configuration dictionary containing settings for the adapter
        
    Returns:
        An instance of the appropriate BaseImageAdapter subclass
        
    Raises:
        ValueError: If the backend is not supported
    """
    backend_lower = backend.lower().strip()
    
    if backend_lower not in ADAPTER_REGISTRY:
        available = ", ".join(sorted(set(cls.__name__ for cls in ADAPTER_REGISTRY.values())))
        error_msg = (
            f"Unknown backend '{backend}'. "
            f"Available backends: {available}. "
            f"Registered names: {', '.join(sorted(ADAPTER_REGISTRY.keys()))}"
        )
        logging.error(error_msg)
        raise ValueError(error_msg)
    
    adapter_class = ADAPTER_REGISTRY[backend_lower]
    adapter = adapter_class(config)
    
    logging.info(f"Created adapter '{adapter.name}' for backend '{backend}'")
    return adapter


def create_adapter_from_config(config: Dict[str, Any]) -> BaseImageAdapter:
    """
    Create an adapter using the backend specified in the configuration.
    
    This function reads the 'SDBackend' key from the config dictionary
    and automatically selects the appropriate URL (SDURL, SDComfyURL, or SDInvokeURL).
    If not specified, defaults to 'automatic1111' for backward compatibility.
    
    Args:
        config: Configuration dictionary containing 'SDBackend' and other settings
        
    Returns:
        An instance of the appropriate BaseImageAdapter subclass
    """
    backend = config.get("SDBackend", "automatic1111")
    
    if not backend:
        logging.warning("SDBackend not specified in config, defaulting to 'automatic1111'")
        backend = "automatic1111"
    
    # Select the appropriate URL based on backend
    backend_lower = backend.lower()
    if backend_lower in ["comfyui", "comfy"]:
        # Use ComfyUI URL if available, fallback to default SDURL
        comfy_url = config.get("SDComfyURL")
        current_sdurl = config.get("SDURL")
        logging.debug(f"ComfyUI URL resolution: SDURL={current_sdurl}, SDComfyURL={comfy_url}")
        if comfy_url:
            config["SDURL"] = comfy_url
            logging.info(f"Using ComfyUI URL: {comfy_url}")
    elif backend_lower in ["invokeai", "invoke"]:
        # Use InvokeAI URL if available, fallback to default SDURL
        invoke_url = config.get("SDInvokeURL")
        if invoke_url:
            config["SDURL"] = invoke_url
            logging.info(f"Using InvokeAI URL: {invoke_url}")
    # For automatic1111, use the default SDURL
    
    return create_adapter(backend, config)


def register_adapter(
    name: str,
    adapter_class: Type[BaseImageAdapter],
    aliases: list = None
) -> None:
    """
    Register a custom adapter class.
    
    This allows extending the factory with custom adapters.
    
    Args:
        name: The primary name for the adapter
        adapter_class: The adapter class to register
        aliases: Optional list of alias names for the adapter
    """
    ADAPTER_REGISTRY[name.lower()] = adapter_class
    
    if aliases:
        for alias in aliases:
            ADAPTER_REGISTRY[alias.lower()] = adapter_class
    
    logging.info(f"Registered adapter '{name}' with aliases: {aliases}")


def is_backend_supported(backend: str) -> bool:
    """
    Check if a backend name is supported.
    
    Args:
        backend: The backend name to check
        
    Returns:
        True if the backend is supported, False otherwise
    """
    return backend.lower().strip() in ADAPTER_REGISTRY


def get_backend_display_name(backend: str) -> str:
    """
    Get a human-readable display name for a backend.
    
    Args:
        backend: The backend name
        
    Returns:
        A human-readable display name
    """
    display_names = {
        "automatic1111": "Automatic1111 WebUI",
        "auto": "Automatic1111 WebUI",
        "a1111": "Automatic1111 WebUI",
        "webui": "Automatic1111 WebUI",
        "comfyui": "ComfyUI",
        "comfy": "ComfyUI",
        "invokeai": "InvokeAI",
        "invoke": "InvokeAI",
    }
    
    return display_names.get(backend.lower(), backend)


# Convenience function for quick adapter creation
def get_adapter(config: Dict[str, Any]) -> BaseImageAdapter:
    """
    Get an adapter instance from configuration.
    
    This is a convenience alias for create_adapter_from_config.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        An instance of BaseImageAdapter
    """
    return create_adapter_from_config(config)
