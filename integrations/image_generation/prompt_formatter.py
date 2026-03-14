"""
Prompt Formatter for image generation.

This module provides a standardized way to format prompts for different
image generation backends, handling the conversion of user prompts into
backend-specific formats while maintaining a consistent interface.
"""

import logging
from typing import Dict, Any, Optional, Union, List
from integrations.image_generation.base_adapter import BaseImageAdapter


class PromptFormatter:
    """
    Formats prompts and parameters for image generation backends.
    
    This class provides a unified interface for preparing image generation
    requests across different backends (Automatic1111, ComfyUI, InvokeAI, etc.).
    """
    
    def __init__(self, adapter: BaseImageAdapter):
        """
        Initialize the prompt formatter with an adapter.
        
        Args:
            adapter: The image generation adapter to use for formatting
        """
        self.adapter = adapter
        logging.info(f"Initialized PromptFormatter with adapter: {adapter.name}")
    
    def format_prompt(
        self,
        prompt: Union[str, List[str]],
        upscale: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Format a prompt into a backend-specific payload.
        
        This is the main entry point for preparing image generation requests.
        It delegates to the adapter's prepare_payload method while providing
        standardized logging and validation.
        
        Args:
            prompt: The image generation prompt (string or list of strings)
            upscale: Whether to enable upscaling
            **kwargs: Additional parameters to include in the payload:
                - steps: Number of generation steps
                - width: Image width
                - height: Image height
                - negative_prompt: Negative prompt text
                - sampler: Sampler name
                - scheduler: Scheduler name
                - cfg_scale: CFG scale value
                - model: Model checkpoint name
                - clip_skip: CLIP skip value
                - seed: Random seed
                - Any other backend-specific parameters
        
        Returns:
            Dictionary containing the formatted payload for the backend
        """
        try:
            # Normalize prompt to string
            if isinstance(prompt, list):
                prompt = " ".join(prompt)
            
            # Use the adapter to prepare the backend-specific payload
            payload = self.adapter.prepare_payload(prompt, upscale=upscale, **kwargs)
            
            logging.info(f"Prompt formatted successfully for {self.adapter.name}")
            logging.debug(f"Formatted payload: {payload}")
            
            return payload
            
        except Exception as e:
            error_msg = f"Failed to format prompt for {self.adapter.name}: {str(e)}"
            logging.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def format_batch_prompts(
        self,
        prompts: List[str],
        upscale: bool = False,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Format multiple prompts into backend-specific payloads.
        
        Args:
            prompts: List of image generation prompts
            upscale: Whether to enable upscaling
            **kwargs: Additional parameters (same as format_prompt)
        
        Returns:
            List of formatted payload dictionaries
        """
        return [
            self.format_prompt(prompt, upscale=upscale, **kwargs)
            for prompt in prompts
        ]
    
    def get_adapter_info(self) -> Dict[str, Any]:
        """
        Get information about the current adapter.
        
        Returns:
            Dictionary containing adapter information
        """
        return {
            "name": self.adapter.name,
            "base_url": self.adapter.get_base_url(),
            "generation_endpoint": self.adapter.get_generation_endpoint(),
            "options_endpoint": self.adapter.get_options_endpoint(),
            "models_endpoint": self.adapter.get_models_endpoint(),
        }
    
    def extract_prompt_from_payload(self, payload: Dict[str, Any]) -> Optional[str]:
        """
        Extract the prompt text from a formatted payload.
        
        This is useful for logging or displaying what prompt was actually sent.
        
        Args:
            payload: The formatted payload
            
        Returns:
            The prompt text, or None if not found
        """
        # Try common prompt field names across different backends
        prompt_fields = ["prompt", "text", "positive_prompt", "input"]
        
        for field in prompt_fields:
            if field in payload:
                value = payload[field]
                # Handle nested structures (e.g., ComfyUI workflows)
                if isinstance(value, str):
                    return value
                elif isinstance(value, dict) and "inputs" in value:
                    # ComfyUI-style nested prompt
                    inputs = value.get("inputs", {})
                    if "text" in inputs:
                        return inputs["text"]
        
        return None
