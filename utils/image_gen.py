import asyncio
import logging
import re
import io
import discord
import aiohttp
import base64
import copy
from utils.utility_functions import (
    generate_response,
    try_generate_response,
)
from utils.model_router import detect_uncensored_content
from PIL import Image
from utils.ssl_config import SSLConfigManager
from integrations.image_generation import create_adapter_from_config, PromptFormatter, ComfyUIAdapter, InvokeAIAdapter
from core.tracing import get_tracer, SpanStatus
from core.service_health import ServiceRegistry
from utils.rate_limiter import RateLimiterManager

tracer = get_tracer()
_rate_manager = RateLimiterManager()


async def handle_image_generation(config, message, user_message_histories, bot, draw_msg):
	try:
		channel = message.channel
		user_id = message.author.id

		# --- Service health gate ---
		sd_health = ServiceRegistry.get("sd_backend")
		if not sd_health.is_available:
			wait = sd_health.wait_seconds()
			await draw_msg.edit(
				content=f"Image generation is temporarily unavailable. Please try again in ~{wait:.0f}s."
			)
			logging.warning("SD backend unavailable, skipping image generation")
			return

		# --- Per-user rate limiting (power users bypass) ---
		is_power_user = hasattr(config, 'is_power_user') and config.is_power_user(user_id)
		if not is_power_user:
			rate_limit = getattr(getattr(config, 'video', None), 'rate_limit_per_minute', None) or config.get("VideoRateLimit", 3)
			bucket = _rate_manager.get_user_limiter(user_id, rate_limit)
			if not bucket.consume(1):
				wait = _rate_manager.wait_seconds_for_user(user_id, rate_limit)
				await draw_msg.edit(
					content=f"You're generating images too quickly. Please try again in ~{wait:.0f}s."
				)
				logging.info(f"Image rate-limited for user {user_id}")
				return

		async with channel.typing():
			logging.info(f"Running image generation for message: {message.content}")
			bot_name = config["Name"]
			prompt, upscale, additional_instructions = parse_prompt(message.content, bot_name, config)

			logging.info("Parsed prompt in handle_image_generation:")
			logging.debug(prompt)

			# Check and load the current model
			sd_model_checkpoint = await check_current_model(config, message, draw_msg)

			if sd_model_checkpoint:
				# Generate response using OpenAI API
				openai_response = await generate_openai_response(config, user_id, user_message_histories, message, prompt, upscale, additional_instructions)
				logging.debug(openai_response)

				# Generate image
				image = await generate_image(config, openai_response, upscale)

				# Send image response
				await send_image_response(message, image, openai_response, draw_msg, prompt=prompt)
				sd_health.mark_success()
			else:
				await draw_msg.edit("Failed to fetch the model. Please try again later.")
				logging.error("Failed to fetch the model. Skipping image generation.")
	except Exception as e:
		logging.error("An error occurred during image generation: " + str(e))
		ServiceRegistry.get("sd_backend").mark_failure(str(e))
		await draw_msg.edit(content="I'm sorry, I was not able to do that for you. Please try again")
		pass

def parse_prompt(prompt, bot_name, config):
	try:
		# Log the original prompt
		logging.debug("Original Prompt:")
		logging.debug(prompt)
		
		# Remove "send" and/or "draw" from the prompt
		# prompt = prompt.replace("send", "").replace("draw", "").strip()

		# Check if "--upscale" is present
		upscale = "--upscale" in prompt

		# Remove "--upscale" from the prompt
		prompt = prompt.replace("--upscale", "").strip()

		sd_instruction = config.get("SDOpenAI", "")

		prompt = re.sub(r'\b{}\b'.format(re.escape(bot_name)), '', prompt, flags=re.IGNORECASE).strip()
		logging.debug("Prompt after removing bot's name: %s", prompt)

		logging.info("Prompt parsed successfully.")

		# Prepend SD instruction as plain text so the LLM receives it as natural context
		if sd_instruction:
			prompt = sd_instruction + prompt

		logging.info(prompt)
		return prompt, upscale, []
	except Exception as e:
		logging.error("An error occurred during prompt parsing: " + str(e))
		return "", upscale, []  # Return an empty list for additional_instructions


async def generate_openai_response(config, user_id, user_message_histories, message, prompt, upscale, additional_instructions):
	try:
		# Check if prompt contains NSFW content
		prompt_text = str(prompt) if prompt else ""
		is_nsfw = detect_uncensored_content(prompt_text)
		
		if is_nsfw:
			logging.info("Explicit content detected in image prompt — routing to uncensored model for SD prompt generation")
			# Create a copy of config to avoid modifying the original
			config_copy = copy.deepcopy(config)
			# Get uncensored model from config or use default
			router_config = config.get("model_router")
			# model_router may be a ModelRouterConfig Pydantic object or a plain dict
			if hasattr(router_config, 'uncensored_model'):
				uncensored_model = router_config.uncensored_model or "venice/venice-uncensored-role-play"
			elif isinstance(router_config, dict):
				uncensored_model = router_config.get("uncensored_model", "venice/venice-uncensored-role-play")
			else:
				uncensored_model = "venice/venice-uncensored-role-play"
			# Force use of uncensored model for SD prompt generation
			config_copy["OpenClawmodel"] = uncensored_model
			config_copy["OpenClawAgent"] = ""  # Use default agent
			config_copy["_nsfw_mode"] = True  # Signal to system prompt builder
			use_config = config_copy
		else:
			use_config = config
		
		# Construct the message for generate_response
		message_dict = {'role': 'user', 'content': message.content} if message else None  # Create the message dictionary
		
		# Generate response using OpenAI API with additional instructions
		response = await generate_response(use_config, user_id, message.author.display_name, user_message_histories, message,additional_instructions=additional_instructions, prompt=prompt)
		logging.info("OpenAI response generated successfully in generate_openai_response.")
		logging.debug(response)
		
		return response
	except Exception as e:
		logging.error("An error occurred during OpenAI response generation in generate_openai_response: " + str(e))
		if message:
			await message.channel.send("Your image request has been sent without additional processing.")
		return None


async def generate_image(config, prompt, upscale):
	try:
		image = await stable_diffusion_generate_image(config, prompt, upscale=upscale)
		if image is None:
			raise ValueError("Failed to generate image in generate_image.")
		logging.info("Image generated successfully in generate_image.")
		return image
	except Exception as e:
		logging.error("An error occurred during image generation in generate_image: " + str(e))
		raise  # Re-raise the exception to propagate it back to the caller


async def send_image_response(message, image, openai_response, draw_msg, prompt=""):
	try:
		if openai_response:
			prompt += " " + " ".join(openai_response)
			logging.debug("OpenAi Prompt in send_image_response: %s", prompt)

		if image is None:
			raise ValueError("Image object is NoneType in send_image_response.")

		image_bytes = io.BytesIO()
		image.save(image_bytes, format='PNG')
		image_bytes.seek(0)
		file = discord.File(image_bytes, filename='output.png')

		if openai_response:
			if isinstance(message.channel, discord.DMChannel):
				await draw_msg.add_files(file)
				await draw_msg.edit(content=openai_response[0])
				# await message.author.send(openai_response[0])
			else:
				await draw_msg.add_files(file)
				await draw_msg.edit(content=openai_response[0])
				# await message.channel.send(openai_response[0])
		else:
			if isinstance(message.channel, discord.DMChannel):
				await draw_msg.add_files(file)
				await draw_msg.edit(content=[])
			else:
				await draw_msg.add_files(file)
				await draw_msg.edit(content=[])
		logging.info("Image response sent successfully in send_image_response.")
	except Exception as e:
		logging.error("An error occurred during sending image response in send_image_response: " + str(e))
		raise  # Re-raise the exception to propagate it back


# Generate image using Stable Diffusion API
async def stable_diffusion_generate_image(config, prompt, upscale):
	"""
	Generate image using the configured backend with tracing.
	
	Supports Automatic1111, ComfyUI, and InvokeAI backends.
	"""
	span_id = tracer.start_span("sd_generate_image", "image_gen", 
	                            attributes={"backend": config.get("SDBackend", "unknown"), 
	                                       "upscale": upscale})
	
	try:
		tracer.add_event("creating_adapter")
		adapter = create_adapter_from_config(config)
		tracer.add_attribute("actual_backend", adapter.name)
		
		formatter = PromptFormatter(adapter)
		
		tracer.add_event("formatting_prompt")
		json_payload = formatter.format_prompt(prompt, upscale=upscale)
		
		if not json_payload:
			raise ValueError("Failed to prepare JSON payload")
		
		tracer.add_event("sending_request", {"backend": adapter.name})
		logging.info(f"JSON Payload complete, Making API Call to {adapter.name} backend.")
		
		# Handle different backend types
		if isinstance(adapter, ComfyUIAdapter):
			tracer.add_event("using_comfyui_workflow")
			image = await _generate_image_comfyui(adapter, config, json_payload)
		elif isinstance(adapter, InvokeAIAdapter):
			tracer.add_event("using_invokeai")
			image = await _generate_image_invokeai(adapter, config, json_payload)
		else:
			tracer.add_event("using_automatic1111")
			response = await _make_api_call_automatic1111(adapter, config, json_payload)
			if response:
				image = adapter.process_response(response)
			else:
				raise ValueError("Failed to get response from API")
		
		if image is None:
			raise ValueError("Failed to generate image")
		
		tracer.add_event("image_generated", {"size": image.size if image else None})
		tracer.end_span(span_id, SpanStatus.SUCCESS)
		return image
		
	except Exception as e:
		tracer.add_event("generation_error", {"error": str(e)})
		tracer.end_span(span_id, SpanStatus.ERROR, str(e))
		logging.error("An error occurred during image generation in stable_diffusion_generate_image: " + str(e))
		raise


async def _make_api_call_automatic1111(adapter, config, json_payload):
	"""
	Make API call for Automatic1111-style backends.
	
	Args:
		adapter: The image generation adapter
		config: Configuration dictionary
		json_payload: The payload to send
		
	Returns:
		API response dictionary or None on error
	"""
	try:
		async with aiohttp.ClientSession() as session:
			url = adapter.get_generation_endpoint()
			ssl_context = SSLConfigManager.get_ssl_context(url)
			
			logging.info(f"Sending request to {url}")
			async with session.post(url=url, json=json_payload, ssl=ssl_context, timeout=aiohttp.ClientTimeout(total=300)) as response:
				response.raise_for_status()
				return await response.json()
					
	except aiohttp.ClientError as e:
		logging.error(f"HTTP error occurred: {e}")
		ServiceRegistry.get("sd_backend").mark_failure(str(e))
		return None
	except asyncio.TimeoutError:
		logging.error("Timeout waiting for image generation")
		ServiceRegistry.get("sd_backend").mark_failure("timeout")
		return None
	except Exception as e:
		logging.error(f"An error occurred: {e}")
		return None


async def _generate_image_comfyui(adapter, config, json_payload):
	"""
	Generate image using ComfyUI's async workflow system with tracing.
	"""
	span_id = tracer.start_span("comfyui_generate", "comfyui",
	                            attributes={"base_url": adapter.get_base_url()})
	
	import aiohttp
	
	base_url = adapter.get_base_url()
	ssl_context = SSLConfigManager.get_ssl_context(base_url)
	
	try:
		async with aiohttp.ClientSession() as session:
			# Step 1: Queue the prompt
			prompt_url = adapter.get_generation_endpoint()
			tracer.add_event("queueing_prompt", {"url": prompt_url})
			logging.info(f"Queueing ComfyUI workflow at {prompt_url}")
			
			async with session.post(prompt_url, json=json_payload, ssl=ssl_context) as response:
				response.raise_for_status()
				queue_response = await response.json()
				
			prompt_id = queue_response.get("prompt_id")
			if not prompt_id:
				raise ValueError("No prompt_id returned from ComfyUI")
			
			tracer.add_attribute("prompt_id", prompt_id)
			tracer.add_event("prompt_queued", {"prompt_id": prompt_id})
			logging.info(f"ComfyUI workflow queued with prompt_id: {prompt_id}")
			
			# Step 2: Poll for completion
			history_url = adapter.get_history_endpoint(prompt_id)
			tracer.add_event("polling_for_completion", {"max_attempts": 300})
			
			poll_span = tracer.start_span("comfyui_poll", "comfyui", parent_id=span_id)
			max_attempts = 300
			
			for attempt in range(max_attempts):
				await asyncio.sleep(1)
				
				async with session.get(history_url, ssl=ssl_context) as response:
					if response.status == 200:
						history = await response.json()
						
						if prompt_id in history:
							tracer.add_event("workflow_completed", {"attempts": attempt + 1})
							logging.info(f"ComfyUI workflow completed after {attempt + 1} seconds")
							result = history[prompt_id]
							break
			else:
				tracer.end_span(poll_span, SpanStatus.ERROR, "Timeout")
				raise TimeoutError("ComfyUI workflow timed out")
			
			tracer.end_span(poll_span)
			
			# Step 3: Extract and fetch the image
			fetch_span = tracer.start_span("comfyui_fetch_image", "comfyui", parent_id=span_id)
			
			outputs = result.get("outputs", {})
			if not outputs:
				raise ValueError("No outputs in ComfyUI result")
			
			# Find the saved image node
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
			
			tracer.add_attribute("image_filename", image_filename)
			
			# Step 4: Fetch the image
			image_url = adapter.get_image_endpoint(image_filename, image_subfolder)
			logging.info(f"Fetching ComfyUI result image from {image_url}")
			
			async with session.get(image_url, ssl=ssl_context) as response:
				response.raise_for_status()
				image_data = await response.read()
				image = Image.open(io.BytesIO(image_data))
				
			tracer.add_event("image_fetched", {"size_bytes": len(image_data)})
			tracer.end_span(fetch_span)
			tracer.end_span(span_id, SpanStatus.SUCCESS)
			
			return image
			
	except Exception as e:
		tracer.add_event("comfyui_error", {"error": str(e)})
		tracer.end_span(span_id, SpanStatus.ERROR, str(e))
		raise


async def _generate_image_invokeai(adapter, config, json_payload):
	"""
	Generate image using InvokeAI API.
	
	InvokeAI can work in two modes:
	1. Direct generation via /api/v1/images/generate
	2. Session-based generation for more complex workflows
	
	This function uses the direct generation approach.
	
	Args:
		adapter: InvokeAIAdapter instance
		config: Configuration dictionary
		json_payload: Generation payload
		
	Returns:
		PIL Image object
	"""
	try:
		# Use the standard API call
		response = await _make_api_call_automatic1111(adapter, config, json_payload)
		
		if not response:
			raise ValueError("No response from InvokeAI API")
		
		# Process the response
		return adapter.process_response(response)
		
	except Exception as e:
		logging.error(f"InvokeAI generation failed: {e}")
		raise


async def make_api_call_with_adapter(adapter, config, json_payload):
	"""
	Make API call using the adapter's endpoint configuration.
	
	Args:
		adapter: The image generation adapter
		config: Configuration dictionary
		json_payload: The payload to send
		
	Returns:
		API response dictionary or None on error
	"""
	try:
		async with aiohttp.ClientSession() as session:
			url = adapter.get_generation_endpoint()
			ssl_context = SSLConfigManager.get_ssl_context(url)
			
			async with session.post(url=url, json=json_payload, ssl=ssl_context) as response:
				response.raise_for_status()
				return await response.json()
	except aiohttp.ClientError as e:
		logging.error(f"HTTP error occurred: {e}")
		return None
	except Exception as e:
		logging.error(f"An error occurred: {e}")
		return None


async def fetch_options(config):
	"""
	Fetch options from the configured backend.
	
	Args:
		config: Configuration dictionary
		
	Returns:
		Options dictionary from the backend
	"""
	try:
		adapter = create_adapter_from_config(config)
		
		async with aiohttp.ClientSession() as session:
			url = adapter.get_options_endpoint()
			ssl_context = SSLConfigManager.get_ssl_context(url)
			async with session.get(url, ssl=ssl_context) as response:
				response.raise_for_status()
				options = await response.json()
				logging.info(f"Options fetched successfully from {adapter.name} backend.")
				return options
	except aiohttp.ClientError as e:
		logging.error(f"HTTP error occurred: {e}, url={url}")
		raise
	except Exception as e:
		logging.error(f"An error occurred while fetching options: {e}")
		raise


async def check_current_model(config, message, draw_msg):
	"""
	Check the current model and switch if necessary.
	
	Args:
		config: Configuration dictionary
		message: Discord message object
		draw_msg: Message to edit for status updates
		
	Returns:
		Tuple of (current_model, configured_model) or None on error
	"""
	try:
		adapter = create_adapter_from_config(config)
		
		# Skip model checking for backends that don't have global model state
		if isinstance(adapter, ComfyUIAdapter):
			logging.info("ComfyUI backend detected - skipping global model check (model specified per-workflow)")
			configured_model = config.get("SDmodel")
			return configured_model, configured_model
		
		options = await fetch_options(config)
		
		# Use adapter to parse current model
		sd_model_checkpoint = adapter.parse_current_model(options)
		configured_model_checkpoint = config.get("SDmodel")
		
		if sd_model_checkpoint is None:
			logging.warning("Could not parse current model from options")
			# Return configured model to allow generation to proceed
			return configured_model_checkpoint, configured_model_checkpoint
		
		if sd_model_checkpoint != configured_model_checkpoint:
			logging.warning("Loaded model does not match configured model.")
			if message:
				logging.warning("Sending message to notify about model mismatch...")
				if isinstance(message.channel, discord.DMChannel):
					await draw_msg.edit(content=draw_msg.content + "\n" + "Please wait, switching models...")
				else:
					await draw_msg.edit(content=draw_msg.content + "\n" + "It may take me a bit of time to do that. Please be patient")
			
			# Create model switch payload using adapter
			json_payload = adapter.create_model_switch_payload(configured_model_checkpoint)
			
			# Skip if adapter returns empty payload (backend doesn't support model switching)
			if not json_payload:
				logging.info(f"{adapter.name} backend does not support global model switching")
				return configured_model_checkpoint, configured_model_checkpoint
			
			# Send the POST request to load the model
			async with aiohttp.ClientSession() as session:
				ssl_context = SSLConfigManager.get_ssl_context(adapter.get_base_url())
				async with session.post(
					url=adapter.get_options_endpoint(), 
					json=json_payload, 
					timeout=aiohttp.ClientTimeout(total=120),
					ssl=ssl_context
				) as response:
					response.raise_for_status()
					logging.info(f"Model loaded successfully on {adapter.name} backend.")
		else:
			logging.info("Loaded model matches configured model.")
		
		return sd_model_checkpoint, configured_model_checkpoint
			
	except Exception as e:
		logging.error(f"An error occurred in check_current_model: {e}")
		# Return configured model to allow generation to proceed despite error
		configured_model = config.get("SDmodel")
		return configured_model, configured_model


async def check_models(config):
	"""
	Check available models from the configured backend.
	
	Args:
		config: Configuration dictionary
		
	Returns:
		List of available model names
	"""
	adapter = create_adapter_from_config(config)
	
	async def fetch_models():
		async with aiohttp.ClientSession() as session:
			# Refresh checkpoints if supported
			refresh_url = adapter.get_refresh_models_endpoint()
			if refresh_url:
				try:
					ssl_context = SSLConfigManager.get_ssl_context(refresh_url)
					async with session.post(refresh_url, ssl=ssl_context) as response:
						response.raise_for_status()
						logging.info("Refreshed checkpoints")
				except Exception as e:
					logging.warning(f"Could not refresh checkpoints: {e}")
			
			# Fetch models
			url = adapter.get_models_endpoint()
			ssl_context = SSLConfigManager.get_ssl_context(url)
			async with session.get(url, ssl=ssl_context) as response:
				response.raise_for_status()
				available_models_data = await response.json()
				logging.info("Models fetched successfully.")
				return available_models_data

	try:
		available_models_data = await fetch_models()
		# Use adapter to parse models list
		available_models = adapter.parse_models_list(available_models_data)
		return available_models
	except Exception as e:
		error_message = f"An error occurred while checking available models: {str(e)}"
		logging.error(error_message)
		raise RuntimeError(error_message) from e


async def print_available_models(config,message):
	available_models = await check_models(config)
	if available_models:
		models_available = "\n".join(available_models)
		await message.channel.send(f"Here are the available models:\n{models_available}")
	else:
		await message.channel.send("Sorry there are no models available.")


# Legacy function - kept for backward compatibility
# Use PromptFormatter.format_prompt() instead for new code
def prepare_json_payload(config, prompt, upscale):
	"""
	Prepare JSON payload for image generation (legacy function).
	
	This function is kept for backward compatibility.
	New code should use PromptFormatter.format_prompt() instead.
	
	Args:
		config: Configuration dictionary
		prompt: The image generation prompt
		upscale: Whether to enable upscaling
		
	Returns:
		Dictionary containing the API payload
	"""
	try:
		from integrations.image_generation import create_adapter_from_config, PromptFormatter
		
		adapter = create_adapter_from_config(config)
		formatter = PromptFormatter(adapter)
		
		return formatter.format_prompt(prompt, upscale=upscale)
	except Exception as e:
		error_message = f"An error occurred while preparing JSON payload: {str(e)}"
		logging.error(error_message)
		raise RuntimeError(error_message) from e


# Legacy function - kept for backward compatibility
# Use make_api_call_with_adapter() instead for new code
async def make_api_call(config, json_payload):
	"""
	Make API call to generate image (legacy function).
	
	This function is kept for backward compatibility.
	New code should use make_api_call_with_adapter() instead.
	
	Args:
		config: Configuration dictionary
		json_payload: The payload to send
		
	Returns:
		API response dictionary or None on error
	"""
	try:
		adapter = create_adapter_from_config(config)
		return await make_api_call_with_adapter(adapter, config, json_payload)
	except Exception as e:
		logging.error(f"An error occurred in make_api_call: {e}")
		return None


def process_response(response, adapter=None):
	"""
	Process API response and extract image.
	
	Args:
		response: API response dictionary
		adapter: Optional adapter instance. If not provided, attempts
			to auto-detect the response format.
		
	Returns:
		PIL Image object or None on error
	"""
	try:
		# If adapter is provided, use its process_response method
		if adapter is not None:
			return adapter.process_response(response)
		
		# Try to auto-detect the response format
		if "images" in response and isinstance(response["images"], list):
			# Automatic1111 or InvokeAI format with base64 images
			image_data = base64.b64decode(response["images"][0])
			image = Image.open(io.BytesIO(image_data))
			logging.debug("Image processed successfully (base64 format).")
			return image
		elif "prompt_id" in response:
			# ComfyUI format - requires separate image fetching
			logging.warning("ComfyUI response detected but separate image fetching required. Use _generate_image_comfyui().")
			return None
		elif "image" in response:
			# Direct base64 image
			image_data = base64.b64decode(response["image"])
			image = Image.open(io.BytesIO(image_data))
			logging.debug("Image processed successfully (direct base64 format).")
			return image
		else:
			logging.error(f"Unknown response format: {response.keys()}")
			return None
	except Exception as e:
		logging.error("An error occurred while processing API response in process_response: " + str(e))
		return None


# Check if image is generated
def image_generated(image):
	try:
		return image.size[0] > 0 and image.size[1] > 0
	except Exception as e:
		logging.error("An error occurred during image generation in image_generated: " + str(e))
		return False

async def send_message_in_thread(thread, content):
	try:
		await thread.send(content)
	except Exception as e:
		logging.error("An error occurred while sending message in thread: " + str(e))
