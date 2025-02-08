from letta_client import Tool, TerminalToolRule
from image_gen import stable_diffusion_generate_image
from config_gen import load_config

async def generate_image_with_sd(prompt: str, upscale: bool = False):
    """
    Generates an image based on a given text prompt using Stable Diffusion. 
    
    
    
    Returns:
       Image: The generated image.
    
    """

    config = load_config()
    from utils.image_gen import stable_diffusion_generate_image  # Import inside function
    image = await stable_diffusion_generate_image(config, prompt, upscale)
    return image

sd_tool = Tool(
    name="generate_stable_diffusion_image",
    description="Generates an image based on a given text prompt using Stable Diffusion.",
    function=generate_image_with_sd,
    parameters=[
        {"name": "prompt", "type": "string", "description": "Text prompt for image generation"},
        {"name": "upscale", "type": "boolean", "description": "Whether to upscale the image"}
    ]
)
