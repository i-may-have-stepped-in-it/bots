import asyncio
import base64
import io
import logging
import os

import aiohttp
from PIL import Image

from integrations.image_generation import (
    ComfyUIAdapter,
    InvokeAIAdapter,
    PromptFormatter,
    create_adapter,
)


async def generate_image_with_sd(prompt: str) -> str:
    """
    Generates an image using a remote Stable Diffusion API.

    Retrieves Stable Diffusion parameters from environment variables.  These
    environment variables should be set by the calling agent.

    Args:
        prompt (str): The text prompt to be appended to the base
                       positive prompt configured for the tool.

    Returns:
        str: A base64 encoded string of the generated image.
             Returns an error message string if image generation fails
             or if the API returns an unexpected response.


    Environment Variables:
        SD_API_URL: The URL of the Stable Diffusion API.
        SD_POSITIVE_PROMPT: The base positive prompt.
        SD_NEGATIVE_PROMPT: The negative prompt.
        SD_STEPS: The number of steps for image generation.
        SD_WIDTH: The width of the generated image.
        SD_HEIGHT: The height of the generated image.
        SD_SAMPLER: The sampler to use.
        SD_SCHEDULER: The scheduler to use.
        SD_CFG_SCALE: The Classifier-Free Guidance scale.
        SD_MODEL: The Stable Diffusion model checkpoint to use.
        SD_CLIP_SKIP: The number of CLIP layers to skip.
        SD_BACKEND: The backend to use (automatic1111, comfyui, invokeai).
                    Defaults to automatic1111.
    """
    # Build config from environment variables
    config = {
        "SDURL": os.environ.get("SD_API_URL", ""),
        "SDPositivePrompt": os.environ.get("SD_POSITIVE_PROMPT", ""),
        "SDNegativePrompt": os.environ.get("SD_NEGATIVE_PROMPT", ""),
        "SDSteps": int(os.environ.get("SD_STEPS", 20)),
        "SDWidth": int(os.environ.get("SD_WIDTH", 512)),
        "SDHeight": int(os.environ.get("SD_HEIGHT", 512)),
        "SDSampler": os.environ.get("SD_SAMPLER", "DPM++ 2M"),
        "SDScheduler": os.environ.get("SD_SCHEDULER", "automatic"),
        "SDConfig": float(os.environ.get("SD_CFG_SCALE", 7.0)),
        "SDmodel": os.environ.get("SD_MODEL", ""),
        "SDClipSkip": int(os.environ.get("SD_CLIP_SKIP", 0)),
        "SDBackend": os.environ.get("SD_BACKEND", "automatic1111"),
    }

    sd_api_url = config["SDURL"]
    if not sd_api_url:
        return "Error: SD_API_URL environment variable not set"

    try:
        # Create adapter and formatter
        backend = config.get("SDBackend", "automatic1111")
        adapter = create_adapter(backend, config)
        formatter = PromptFormatter(adapter)

        # Prepare payload using the formatter
        json_payload = formatter.format_prompt(prompt, upscale=False)

    except Exception as e:
        error_msg = f"Error preparing request: {str(e)}"
        logging.error(error_msg)
        return f"Error: {error_msg}"

    try:
        # Handle different backend types
        if isinstance(adapter, ComfyUIAdapter):
            image = await _generate_comfyui(adapter, json_payload)
        elif isinstance(adapter, InvokeAIAdapter):
            image = await _generate_invokeai(adapter, json_payload)
        else:
            image = await _generate_automatic1111(adapter, json_payload)

        if image is None:
            return "Error: Failed to generate image"

        # Convert image to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        image_base64 = base64.b64encode(buffered.getvalue()).decode()

        return image_base64

    except Exception as e:
        error_msg = f"Error during image generation: {str(e)}"
        logging.error(error_msg)
        return f"Error: {error_msg}"


async def _generate_automatic1111(adapter, json_payload):
    """Generate image using Automatic1111 API."""
    url = adapter.get_generation_endpoint()

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=json_payload, timeout=aiohttp.ClientTimeout(total=300)) as response:
            if response.status != 200:
                raise ValueError(f"API returned status code {response.status}")

            response_data = await response.json()
            return adapter.process_response(response_data)


async def _generate_comfyui(adapter, json_payload):
    """Generate image using ComfyUI async workflow system."""
    base_url = adapter.get_base_url()

    async with aiohttp.ClientSession() as session:
        # Step 1: Queue the prompt
        prompt_url = adapter.get_generation_endpoint()

        async with session.post(prompt_url, json=json_payload) as response:
            response.raise_for_status()
            queue_response = await response.json()

        prompt_id = queue_response.get("prompt_id")
        if not prompt_id:
            raise ValueError("No prompt_id returned from ComfyUI")

        logging.info(f"ComfyUI workflow queued with prompt_id: {prompt_id}")

        # Step 2: Poll for completion
        history_url = adapter.get_history_endpoint(prompt_id)
        max_attempts = 300

        for attempt in range(max_attempts):
            await asyncio.sleep(1)

            async with session.get(history_url) as response:
                if response.status == 200:
                    history = await response.json()

                    if prompt_id in history:
                        logging.info(f"ComfyUI workflow completed after {attempt + 1} seconds")
                        result = history[prompt_id]
                        break
        else:
            raise TimeoutError("ComfyUI workflow timed out")

        # Step 3: Extract and fetch the image
        outputs = result.get("outputs", {})
        if not outputs:
            raise ValueError("No outputs in ComfyUI result")

        image_filename = None
        image_subfolder = ""

        for node_id, node_output in outputs.items():
            if "images" in node_output:
                for image_info in node_output["images"]:
                    image_filename = image_info.get("filename")
                    image_subfolder = image_info.get("subfolder", "")
                    break
                if image_filename:
                    break

        if not image_filename:
            raise ValueError("No image found in ComfyUI outputs")

        # Step 4: Fetch the image
        image_url = adapter.get_image_endpoint(image_filename, image_subfolder)

        async with session.get(image_url) as response:
            response.raise_for_status()
            image_data = await response.read()
            return Image.open(io.BytesIO(image_data))


async def _generate_invokeai(adapter, json_payload):
    """Generate image using InvokeAI API."""
    url = adapter.get_generation_endpoint()

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=json_payload, timeout=aiohttp.ClientTimeout(total=300)) as response:
            if response.status != 200:
                raise ValueError(f"API returned status code {response.status}")

            response_data = await response.json()
            return adapter.process_response(response_data)


