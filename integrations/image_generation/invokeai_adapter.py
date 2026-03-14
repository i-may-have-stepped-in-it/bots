"""
InvokeAI API adapter for image generation.

This module provides an adapter for the InvokeAI API, which provides
a modern RESTful interface for image generation with support for
various diffusion models and workflows.
"""

import base64
import io
import logging
from typing import Dict, Any, Optional, List
from PIL import Image

from integrations.image_generation.base_adapter import BaseImageAdapter


class InvokeAIAdapter(BaseImageAdapter):
    """
    Adapter for InvokeAI API.
    
    InvokeAI provides a RESTful API with endpoints for text-to-image,
    image-to-image, and various other image generation capabilities.
    """
    
    @property
    def name(self) -> str:
        return "invokeai"
    
    def _convert_sampler(self, sampler: str) -> str:
        """Convert sampler name to InvokeAI format."""
        sampler_map = {
            "DPM++ 2M": "dpmpp_2m",
            "DPM++ SDE": "dpmpp_sde",
            "DPM++ 2M SDE": "dpmpp_2m_sde",
            "DPM++ 2S a": "dpmpp_2s_ancestral",
            "Euler": "euler",
            "Euler a": "euler_ancestral",
            "Heun": "heun",
            "LMS": "lms",
            "DDIM": "ddim",
            "PLMS": "plms",
            "UniPC": "uni_pc_bh2",
            "DPM2": "dpm_2",
            "DPM2 a": "dpm_2_ancestral",
        }
        return sampler_map.get(sampler, sampler.lower().replace(" ", "_"))
    
    def _convert_scheduler(self, scheduler: str) -> str:
        """Convert scheduler name to InvokeAI format."""
        scheduler_map = {
            "automatic": "auto",
            "uniform": "normal",
            "karras": "karras",
            "exponential": "exponential",
            "polyexponential": "polyexponential",
        }
        return scheduler_map.get(scheduler, "auto")
    
    def prepare_payload(self, prompt: str, upscale: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Prepare the JSON payload for InvokeAI text-to-image API.
        
        Args:
            prompt: The image generation prompt
            upscale: Whether to enable upscaling ( InvokeAI handles this via separate endpoints)
            **kwargs: Additional parameters
            
        Returns:
            Dictionary containing the API payload for InvokeAI
        """
        formatted_prompt = self.format_prompt(prompt)
        
        # InvokeAI uses a different payload structure
        # It uses the "metadata" style with specific field names
        payload = {
            "prompt": formatted_prompt,
            "negative_prompt": kwargs.get("negative_prompt", self.config.get("SDNegativePrompt", "")),
            "width": kwargs.get("width", self.config.get("SDWidth", 512)),
            "height": kwargs.get("height", self.config.get("SDHeight", 512)),
            "steps": kwargs.get("steps", self.config.get("SDSteps", 20)),
            "cfg_scale": kwargs.get("cfg_scale", self.config.get("SDConfig", 7)),
            "seed": kwargs.get("seed", -1),
            "scheduler": self._convert_scheduler(kwargs.get("scheduler", self.config.get("SDScheduler", "auto"))),
            "sampler": self._convert_sampler(kwargs.get("sampler", self.config.get("SDSampler", "dpmpp_2m"))),
            "model": kwargs.get("model", self.config.get("SDmodel", "")),
            "clip_skip": kwargs.get("clip_skip", self.config.get("SDClipSkip", 0)),
        }
        
        # Add optional parameters if provided
        if upscale:
            # InvokeAI handles upscaling separately or via specific parameters
            payload["high_resolution"] = {
                "scale": 2.0,
                "strength": 0.5
            }
        
        # InvokeAI v3 uses a sessions-based approach or direct generation
        # This payload works for the direct text-to-image endpoint
        logging.debug(f"Prepared InvokeAI payload: {payload}")
        return payload
    
    def get_generation_endpoint(self) -> str:
        """Return the text-to-image endpoint URL."""
        # InvokeAI v3 API uses /api/v1/images/generate or /api/v1/sessions
        return f"{self.get_base_url()}/api/v1/images/generate"
    
    def process_response(self, response: Dict[str, Any]) -> Image.Image:
        """
        Process InvokeAI API response and extract the image.
        
        Args:
            response: JSON response from InvokeAI API
            
        Returns:
            PIL Image object
            
        Raises:
            ValueError: If the response format is invalid or image cannot be decoded
        """
        try:
            # InvokeAI v3 response format
            if "items" in response and len(response["items"]) > 0:
                # Multiple images response
                item = response["items"][0]
                image_data = self._extract_image_from_item(item)
            elif "image" in response:
                # Single image response (base64 encoded)
                image_data = base64.b64decode(response["image"])
            elif "images" in response and len(response["images"]) > 0:
                # Array of base64 images
                image_data = base64.b64decode(response["images"][0])
            else:
                raise ValueError(f"Unexpected InvokeAI response format: {response.keys()}")
            
            image = Image.open(io.BytesIO(image_data))
            logging.debug(f"Successfully processed InvokeAI image: {image.size}")
            return image
            
        except (KeyError, IndexError, base64.binascii.Error) as e:
            error_msg = f"Failed to process InvokeAI response: {str(e)}"
            logging.error(error_msg)
            raise ValueError(error_msg) from e
    
    def _extract_image_from_item(self, item: Dict[str, Any]) -> bytes:
        """Extract image data from an InvokeAI response item."""
        if "image" in item:
            return base64.b64decode(item["image"])
        elif "image_url" in item:
            # Image URL provided - would need to fetch separately
            raise ValueError("Image URL response not yet implemented - requires separate fetch")
        elif "image_name" in item:
            # Image name provided - would need to fetch via image endpoint
            raise ValueError("Image name response not yet implemented - requires separate fetch")
        else:
            raise ValueError("No image data found in response item")
    
    def get_options_endpoint(self) -> str:
        """Return the app config endpoint URL."""
        return f"{self.get_base_url()}/api/v1/app/config"
    
    def get_models_endpoint(self) -> str:
        """Return the models endpoint URL."""
        return f"{self.get_base_url()}/api/v1/models/"
    
    def get_refresh_models_endpoint(self) -> Optional[str]:
        """InvokeAI models are auto-refreshed, no explicit endpoint needed."""
        return None
    
    def parse_current_model(self, options: Dict[str, Any]) -> Optional[str]:
        """
        Extract the current model from app config.
        
        Args:
            options: App config dictionary from the API
            
        Returns:
            Current model name, or None if not found
        """
        # InvokeAI stores model info in different locations depending on version
        if "model" in options:
            return options["model"].get("model_name")
        # Try to find in active model
        models = options.get("models", {})
        if "main" in models:
            return models["main"].get("model_name")
        return None
    
    def create_model_switch_payload(self, model_name: str) -> Dict[str, Any]:
        """
        Create the payload for switching models.
        
        Note: InvokeAI v3 uses a different approach for model management.
        Models are typically specified per-generation or via the model manager.
        """
        # InvokeAI handles model switching differently
        # This is a placeholder for the concept
        return {"model_name": model_name}
    
    def parse_models_list(self, models_data: Any) -> List[str]:
        """
        Parse the models list response and return model names.
        
        Args:
            models_data: Raw models data from the API
            
        Returns:
            List of model names
        """
        try:
            if isinstance(models_data, list):
                # Direct list of models
                return [model.get("model_name", model.get("name", "")) for model in models_data]
            elif isinstance(models_data, dict):
                # Paginated or categorized response
                if "models" in models_data:
                    models = models_data["models"]
                    return [m.get("model_name", m.get("name", "")) for m in models]
                elif "items" in models_data:
                    items = models_data["items"]
                    return [item.get("model_name", item.get("name", "")) for item in items]
            return []
        except Exception as e:
            logging.error(f"Failed to parse InvokeAI models list: {e}")
            return []
    
    def get_queue_endpoint(self) -> str:
        """Return the queue endpoint URL."""
        return f"{self.get_base_url()}/api/v1/queue/default/enqueue_batch"
    
    def get_sessions_endpoint(self) -> str:
        """Return the sessions endpoint URL for creating generation sessions."""
        return f"{self.get_base_url()}/api/v1/sessions"
    
    def get_session_status_endpoint(self, session_id: str) -> str:
        """Return the session status endpoint URL."""
        return f"{self.get_base_url()}/api/v1/sessions/{session_id}"
    
    def get_image_by_name_endpoint(self, image_name: str) -> str:
        """Return the endpoint for retrieving an image by name."""
        return f"{self.get_base_url()}/api/v1/images/{image_name}/data"
