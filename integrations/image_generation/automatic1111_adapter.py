"""
Automatic1111 API adapter for image generation.

This module provides an adapter for the Automatic1111 Stable Diffusion WebUI API,
which is one of the most popular interfaces for running Stable Diffusion locally.
"""

import base64
import io
import logging
from typing import Dict, Any, Optional, List
from PIL import Image

from integrations.image_generation.base_adapter import BaseImageAdapter


class Automatic1111Adapter(BaseImageAdapter):
    """
    Adapter for Automatic1111 Stable Diffusion WebUI API.
    
    Supports the standard /sdapi/v1/ endpoints used by Automatic1111.
    """
    
    @property
    def name(self) -> str:
        return "automatic1111"
    
    def prepare_payload(self, prompt: str, upscale: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Prepare the JSON payload for Automatic1111 txt2img API.
        
        Args:
            prompt: The image generation prompt
            upscale: Whether to enable high-res upscaling
            **kwargs: Additional parameters to override defaults
            
        Returns:
            Dictionary containing the API payload for Automatic1111
        """
        formatted_prompt = self.format_prompt(prompt)
        
        payload = {
            "prompt": formatted_prompt,
            "steps": kwargs.get("steps", self.config.get("SDSteps", 20)),
            "width": kwargs.get("width", self.config.get("SDWidth", 512)),
            "height": kwargs.get("height", self.config.get("SDHeight", 512)),
            "negative_prompt": kwargs.get("negative_prompt", self.config.get("SDNegativePrompt", "")),
            "sampler_index": kwargs.get("sampler", self.config.get("SDSampler", "DPM++ 2M")),
            "scheduler": kwargs.get("scheduler", self.config.get("SDScheduler", "automatic")),
            "cfg_scale": kwargs.get("cfg_scale", self.config.get("SDConfig", 7)),
            "self_attention": "yes",
            "enable_hr": upscale,
            "hr_upscaler": "R-ESRGAN 4x+",
            "hr_prompt": formatted_prompt,
            "hr_negative_prompt": kwargs.get("negative_prompt", self.config.get("SDNegativePrompt", "")),
            "denoising_strength": 0.5,
            "override_settings_restore_afterwards": False,
            "override_settings": {
                "sd_model_checkpoint": kwargs.get("model", self.config.get("SDmodel", "")),
                "CLIP_stop_at_last_layers": kwargs.get("clip_skip", self.config.get("SDClipSkip", 0))
            }
        }
        
        # Allow overriding any payload field via kwargs
        for key, value in kwargs.items():
            if key not in ["steps", "width", "height", "negative_prompt", 
                          "sampler", "scheduler", "cfg_scale", "model", "clip_skip"]:
                payload[key] = value
        
        logging.debug(f"Prepared Automatic1111 payload: {payload}")
        return payload
    
    def get_generation_endpoint(self) -> str:
        """Return the txt2img endpoint URL."""
        return f"{self.get_base_url()}/sdapi/v1/txt2img"
    
    def process_response(self, response: Dict[str, Any]) -> Image.Image:
        """
        Process Automatic1111 API response and extract the image.
        
        Args:
            response: JSON response from Automatic1111 API
            
        Returns:
            PIL Image object
            
        Raises:
            ValueError: If the response format is invalid or image cannot be decoded
        """
        try:
            if "images" not in response or not response["images"]:
                raise ValueError("No images found in response")
            
            image_data = base64.b64decode(response["images"][0])
            image = Image.open(io.BytesIO(image_data))
            
            logging.debug(f"Successfully processed image: {image.size}")
            return image
            
        except (KeyError, IndexError, base64.binascii.Error) as e:
            error_msg = f"Failed to process Automatic1111 response: {str(e)}"
            logging.error(error_msg)
            raise ValueError(error_msg) from e
    
    def get_options_endpoint(self) -> str:
        """Return the options endpoint URL."""
        return f"{self.get_base_url()}/sdapi/v1/options"
    
    def get_models_endpoint(self) -> str:
        """Return the SD models endpoint URL."""
        return f"{self.get_base_url()}/sdapi/v1/sd-models"
    
    def get_refresh_models_endpoint(self) -> Optional[str]:
        """Return the refresh checkpoints endpoint URL."""
        return f"{self.get_base_url()}/sdapi/v1/refresh-checkpoints"
    
    def parse_current_model(self, options: Dict[str, Any]) -> Optional[str]:
        """
        Extract the current model checkpoint from options.
        
        Args:
            options: Options dictionary from the API
            
        Returns:
            Current model checkpoint name, or None if not found
        """
        return options.get("sd_model_checkpoint")
    
    def create_model_switch_payload(self, model_name: str) -> Dict[str, Any]:
        """
        Create the payload for switching models.
        
        Args:
            model_name: Name of the model to switch to
            
        Returns:
            Dictionary with model checkpoint setting
        """
        return {"sd_model_checkpoint": model_name}
    
    def parse_models_list(self, models_data: Any) -> List[str]:
        """
        Parse the models list response and return model names.
        
        Args:
            models_data: Raw models data from the API (list of model dicts)
            
        Returns:
            List of model names
        """
        if isinstance(models_data, list):
            return [model.get("model_name", "") for model in models_data if model.get("model_name")]
        return []
