"""
Base adapter interface for image generation backends.

This module defines the abstract base class that all image generation
adapters must implement to provide a unified interface for different
Stable Diffusion backends (Automatic1111, ComfyUI, InvokeAI, etc.).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import io
from PIL import Image


class BaseImageAdapter(ABC):
    """
    Abstract base class for image generation adapters.
    
    All image generation backends must implement this interface to ensure
    consistent behavior across different APIs.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the adapter with configuration.
        
        Args:
            config: Dictionary containing configuration settings
        """
        self.config = config
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the adapter/backend."""
        pass
    
    @abstractmethod
    def prepare_payload(self, prompt: str, upscale: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Prepare the JSON payload for the image generation API.
        
        Args:
            prompt: The image generation prompt
            upscale: Whether to enable upscaling
            **kwargs: Additional parameters to include in the payload
            
        Returns:
            Dictionary containing the API payload
        """
        pass
    
    @abstractmethod
    def get_generation_endpoint(self) -> str:
        """
        Return the API endpoint URL for text-to-image generation.
        
        Returns:
            Full URL for the txt2img endpoint
        """
        pass
    
    @abstractmethod
    def process_response(self, response: Dict[str, Any]) -> Image.Image:
        """
        Process the API response and extract the generated image.
        
        Args:
            response: JSON response from the API
            
        Returns:
            PIL Image object
            
        Raises:
            ValueError: If the response cannot be processed
        """
        pass
    
    @abstractmethod
    def get_options_endpoint(self) -> str:
        """
        Return the API endpoint URL for fetching options.
        
        Returns:
            Full URL for the options endpoint
        """
        pass
    
    @abstractmethod
    def get_models_endpoint(self) -> str:
        """
        Return the API endpoint URL for fetching available models.
        
        Returns:
            Full URL for the models endpoint
        """
        pass
    
    @abstractmethod
    def get_refresh_models_endpoint(self) -> Optional[str]:
        """
        Return the API endpoint URL for refreshing model list.
        
        Returns:
            Full URL for the refresh endpoint, or None if not supported
        """
        pass
    
    @abstractmethod
    def parse_current_model(self, options: Dict[str, Any]) -> Optional[str]:
        """
        Extract the current model checkpoint from options response.
        
        Args:
            options: Options dictionary from the API
            
        Returns:
            Current model checkpoint name, or None if not found
        """
        pass
    
    @abstractmethod
    def create_model_switch_payload(self, model_name: str) -> Dict[str, Any]:
        """
        Create the payload for switching models.
        
        Args:
            model_name: Name of the model to switch to
            
        Returns:
            Dictionary containing the model switch payload
        """
        pass
    
    @abstractmethod
    def parse_models_list(self, models_data: Any) -> list:
        """
        Parse the models list response and return model names.
        
        Args:
            models_data: Raw models data from the API
            
        Returns:
            List of model names
        """
        pass
    
    def get_base_url(self) -> str:
        """
        Get the base URL for the API.
        
        Returns:
            Base URL from configuration
        """
        import logging
        url = self.config.get("SDURL", "").rstrip("/")
        logging.info(f"DEBUG: get_base_url() returning: {url}")
        logging.info(f"DEBUG: config type: {type(self.config)}")
        return url
    
    def format_prompt(self, prompt: str) -> str:
        """
        Format the prompt by combining with positive prompt from config.
        
        Args:
            prompt: User prompt
            
        Returns:
            Formatted prompt with positive prefix
        """
        positive_prefix = self.config.get("SDPositivePrompt", "")
        if isinstance(prompt, list):
            prompt = " ".join(prompt)
        return positive_prefix + prompt
