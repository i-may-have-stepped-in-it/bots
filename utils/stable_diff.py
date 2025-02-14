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

    Raises:
        aiohttp.ClientError: If there's an error communicating with the
                             Stable Diffusion API.
        KeyError, IndexError, aiohttp.ContentTypeError: If the API response is
                                                       in an unexpected format.
    """
    sd_api_url = os.environ.get("SD_API_URL")+"/sdapi/v1/txt2img"

    positive_prompt = os.environ.get("SD_POSITIVE_PROMPT", "")
    negative_prompt = os.environ.get("SD_NEGATIVE_PROMPT", "")
    steps = int(os.environ.get("SD_STEPS", 20))
    width = int(os.environ.get("SD_WIDTH", 512))
    height = int(os.environ.get("SD_HEIGHT", 512))
    sampler = os.environ.get("SD_SAMPLER", "Euler a")
    scheduler = os.environ.get("SD_SCHEDULER", "Euler")
    cfg_scale = float(os.environ.get("SD_CFG_SCALE", 7.0))
    sd_model = os.environ.get("SD_MODEL")
    clip_skip = int(os.environ.get("SD_CLIP_SKIP", 1))

    json_payload = {
        "prompt": positive_prompt + prompt,
        "steps": steps,
        "width": width,
        "height": height,
        "negative_prompt": negative_prompt,
        "sampler_index": sampler,
        "scheduler": scheduler,
        "cfg_scale": cfg_scale,
         "override_settings": {
            "sd_model_checkpoint": sd_model,
            "CLIP_stop_at_last_layers": clip_skip
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(sd_api_url, json=json_payload) as response:
                if response.status != 200:
                    return f"Error: API returned status code {response.status}"

                try:
                    response_data = await response.json()
                    image_data = response_data["images"][0]
                    image_base64 = image_data.replace("data:image/png;base64,", "")
                    return image_base64
                except (KeyError, IndexError, aiohttp.ContentTypeError) as e:
                    print(f"Unexpected response: {e}")
                    return "Error: Unexpected response from API"

    except aiohttp.ClientError as e:
        print(f"Error communicating with Stable Diffusion API: {e}")
        return f"Error: {e}"

sd_tool = client.tools.create_from_function(
    func=generate_image_with_sd,
)

print(f"Created tool {sd_tool.name}")
