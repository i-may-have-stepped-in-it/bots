import logging

import discord
from openai import AsyncOpenAI

from utils.openclaw import generate_openclaw_response

__all__ = [
    "generate_response",
    "try_generate_response",
]

discord.opus._load_default()


async def generate_response(config, user_id, discord_username, user_message_histories=None, message=None, additional_instructions=None, prompt=None):
	try:
		client = None
		response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid=False, use_openclaw=True)
		if response:
			return response
	except Exception as e:
		logging.error(f"An error occurred during OpenClaw API call: {str(e)}")

	if config.get("OpenAPIEndpoint") and config["OpenAPIEndpoint"].lower() != "disabled" and config.get("OpenAPIKey"):
		try:
			client = AsyncOpenAI(base_url=config["OpenAPIEndpoint"], api_key=config["OpenAPIKey"])
			response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid=True, use_openclaw=False)
			if response:
				return response
		except Exception as e:
			logging.error(f"An error occurred during OpenAI API call: {str(e)}")

	if config.get("SecondaryOpenAPIEndpoint") and config["SecondaryOpenAPIEndpoint"].lower() != "disabled" and config.get("SecondaryOpenAPIKey"):
		try:
			client = AsyncOpenAI(base_url=config["SecondaryOpenAPIEndpoint"], api_key=config["SecondaryOpenAPIKey"])
			response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid=False, use_openclaw=False)
			if response:
				return response
		except Exception as e:
				logging.error(f"An error occurred during second OpenAI API call: {str(e)}")

	if message:
		await message.channel.send("I can't talk right now please try back later.")
	return None


async def try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid, use_openclaw):
		try:
			user_id_str = str(user_id)
			messages = []

			# Retrieve history for the user (fallback to HistoryManager)
			if user_message_histories is not None:
				history = user_message_histories.get(user_id_str, [])
			else:
				from core.history import history_manager
				history = await history_manager.get_history(user_id_str)

			# Check cache if it's a direct prompt (not a complex conversation)
			if prompt:
				from core.cache import cache_manager
				cached = await cache_manager.get({"prompt": prompt, "model": config.get("OpenaiModel")})
				if cached:
					return [cached]

			if not (use_openclaw or prompt):
				personality_command = f"You are {config['Personality']}."
				messages.append({'role': 'system', 'content': personality_command})
				logging.info("Included personality message.")

			# Include historical messages with timestamps
			if prompt is None:
				# Add historical messages with timestamps
				for entry in history[:-1]: # All but the last one
					entry_role = entry.get('role', 'user')
					entry_content = entry.get('content', '')
					entry_timestamp = entry.get('timestamp', '')

					formatted_content = f"[{entry_timestamp}] {entry_content}" if entry_timestamp else entry_content
					messages.append({'role': entry_role, 'content': formatted_content})
				logging.info(f"Included {len(history)-1} historical messages.")

			# Current message or prompt
			if isinstance(prompt, str) and prompt:
				logging.info("Using provided prompt:")
				logging.debug(prompt)
				messages.append({'role': 'user', 'content': prompt})
			elif message and isinstance(message.content, str):
				# Get timestamp for current message if it exists in history
				current_timestamp = ""
				if history:
					current_timestamp = history[-1].get('timestamp', '')

				content = message.content
				formatted_content = f"[{current_timestamp}] {content}" if current_timestamp else content
				messages.append({'role': 'user', 'content': formatted_content})
				logging.info("Included current message with timestamp.")

			logging.info(f"Sending data to {'OpenClaw' if use_openclaw else 'OpenAI'}: {messages}")
			if use_openclaw:
				response = await generate_openclaw_response(config, user_id, discord_username, messages)
				if response:
					logging.info(f"OpenClaw Response: {response}")
					if isinstance(response, str):
						response = "".join(response)

						if len(response) > 2000:
							chunks = [response[i:i + 2000] for i in range(0, len(response), 2000)]
							return chunks
						else:
							return [response]
					else:
						logging.warning("OpenClaw did not return a string response.")
					return None
			else:
				# Use the unified TextAIProvider
				from integrations.text_generation.openai_provider import OpenAITextProvider
				
				if openai_valid:
					provider = OpenAITextProvider(
						base_url=config.get("OpenAPIEndpoint"),
						api_key=config.get("OpenAPIKey"),
						default_model=config.get("OpenaiModel")
					)
				else:
					provider = OpenAITextProvider(
						base_url=config.get("SecondaryOpenAPIEndpoint"),
						api_key=config.get("SecondaryOpenAPIKey"),
						default_model=config.get("SecondaryOpenaiModel")
					)

				try:
					ai_response = await provider.chat(messages=messages)
					response_text = ai_response.content
				except Exception as circuit_error:
					logging.error(f"Provider error or Circuit Breaker open: {circuit_error}")
					return ["I'm currently experiencing high load or my backend is unavailable. Please try again later."]

				logging.info("API response received.")
				logging.debug(response_text)

				# Cache successful response
				if prompt:
					from core.cache import cache_manager
					await cache_manager.set({"prompt": prompt, "model": provider.default_model}, response_text)
				if len(response_text) > 2000:
					chunks = [response_text[i:i + 2000] for i in range(0, len(response_text), 2000)]
					return chunks
				else:
					return [response_text]

		except Exception as e:

			logging.error("An error occurred during API call in try_generate_response: " + str(e), exc_info=True)
			raise
