from functools import cache
from openai import AsyncOpenAI
import logging
import asyncio
from io import BytesIO
import sys
import discord
import json
import aiohttp
from discord.ext.voice_recv.extras import *
import os
import aiofiles
import docker
from letta_client import AsyncLetta, MessageCreate, TerminalToolRule

discord.opus._load_default()


async def generate_response(config, user_id, discord_username, user_message_histories, message=None, additional_instructions=None, prompt=None):
	try:
		client = None
		response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid=False, use_memgpt=True)
		if response:
			return response
	except Exception as e:
		logging.error(f"An error occurred during MemGPT API call: {str(e)}")

	if config.get("OpenAPIEndpoint") and config["OpenAPIEndpoint"].lower() != "disabled" and config.get("OpenAPIKey"):
		try:
			client = AsyncOpenAI(base_url=config["OpenAPIEndpoint"], api_key=config["OpenAPIKey"])
			response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid=True, use_memgpt=False)
			if response:
				return response
		except Exception as e:
			logging.error(f"An error occurred during OpenAI API call: {str(e)}")
	
	if config.get("SecondaryOpenAPIEndpoint") and config["SecondaryOpenAPIEndpoint"].lower != "disabled" and config.get("SecondaryOpenAPIKey"):
		try:
			client = AsyncOpenAI(base_url=config["SecondaryOpenAPIEndpoint"], api_key=config["SecondaryOpenAPIKey"])
			response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid=False, use_memgpt=False)
			if response:
				return response
		except Exception as e:
				logging.error(f"An error occurred during second OpenAI API call: {str(e)}")
	
	if message:
		await message.channel.send("I can't talk right now please try back later.")
	raise


async def try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid, use_memgpt):
		try:
			recent_message_content = ""
			if user_id in user_message_histories and user_message_histories[user_id]:
				recent_message_content = user_message_histories[user_id][-2]['content'] if len(user_message_histories[user_id]) > 1 else ""
			logging.debug(f"Recent message content: {recent_message_content}")

			messages = []

			if not (use_memgpt or prompt):
				personality_command = f"You are {config['Personality']}."
				messages.append({'role': 'system', 'content': personality_command})
				logging.info("Included personality message.")

			if not use_memgpt and recent_message_content and (message is None or recent_message_content != message.content) and prompt is None:
				messages.append({'role': 'user', 'content': recent_message_content})
				logging.info("Included recent user message.")

			if message and isinstance(message.content, str) and prompt is None:
				messages.append({'role': 'user', 'content': message.content})
				logging.info("Included message content from provided message.")

			if isinstance(prompt, str)and prompt != None:
				logging.info("Using provided prompt:")
				logging.debug(prompt)
				messages.append({'role': 'user', 'content': prompt})

			logging.info(f"Sending data to {'MemGPT' if use_memgpt else 'OpenAI'}: {messages}")

			if use_memgpt:
				response = await send_request_to_memgpt(config, messages, user_id, discord_username, message)
				if response:
					logging.info(f"MemGPT Response: {response}")
					if isinstance(response, str):
						response = "".join(response)

						if len(response) > 2000:
							chunks = [response[i:i + 2000] for i in range(0, len(response), 2000)]
							return chunks
						else:
							return [response]
					else:
						logging.warning("MemGPT did not return a response.")
					return None
			else:
				if openai_valid:
					response = await client.chat.completions.create(
						messages=messages,
						model=config["OpenaiModel"],
					)
				if not openai_valid:
					response = await client.chat.completions.create(
						model=config["SecondaryOpenaiModel"],
						messages=messages,
		)
				logging.info("API response received.")
				logging.debug(response)
				response_text = response.choices[0].message.content
				if len(response_text) > 2000:
					chunks = [response_text[i:i + 2000] for i in range(0, len(response_text), 2000)]
					return chunks
				else:
					return [response_text]

		except Exception as e:
			logging.error("An error occurred during API call in try_generate_response: " + str(e))
			raise

USER_DATA_FILE = "/app/config/memgpt_user_data.json"

if os.path.exists(USER_DATA_FILE):
	with open(USER_DATA_FILE, "r") as f:
		discord_to_memgpt_user = json.load(f)
else:
	discord_to_memgpt_user = {}

async def get_or_create_memgpt_agent(config, user_id, discord_username, message):
	discord_user_id = str(user_id)
	if discord_user_id in discord_to_memgpt_user:
		return discord_to_memgpt_user[discord_user_id]

	client = AsyncLetta(base_url=config["MemGPTEndpoint"])

	async def create_memgpt_agent(discord_username, message):
		from utils.stable_diff import sd_tool
		agent_data = {
			"memory_blocks": [
				{"label": "human", "value": f"The human's name is {discord_username}"},
				{"label": "persona", "value": config["MemGPTPersonality"]}
			],
			"system": config["MemGPTSystemPrompt"],
			"llm_config": {
				"model": config["MemGPTmodel"],
				"context_window": config.get("MemGPTContextWindow", 8192),
				"model_endpoint_type": config.get("MemGPTModelEndpointType", "openai"),
				"model_endpoint": config.get("MemGPTModelEndpoint")
			},
			"embedding_config": {
				"embedding_model": config.get("MemGPTEmbedding", "text-embedding-ada-002"),
				"embedding_dim": config.get("MemGPTEmbeddingDim", 1536),
				"embedding_endpoint_type": config.get("MemGPTEmbeddingEndpointType", "openai"),
				"embedding_endpoint": config.get("MemGPTEmbeddingEndpoint")
			},
		}

		# For logging only, use a custom encoder:
		from pydantic.json import pydantic_encoder
		logging.debug("Agent creation data: " + json.dumps(agent_data, indent=2, default=pydantic_encoder))
		
		try:
			response = await client.agents.create(**agent_data)
			agent_id = response.id
			logging.debug(f"MemGPT Agent Created with ID: {agent_id}")
			return agent_id
		except Exception as e:
			logging.error(f"MemGPT agent creation failed: {e}")
			raise Exception(f"Failed to create MemGPT agent: {e}")

	memgpt_agent_id = await create_memgpt_agent(discord_username, message)

	discord_to_memgpt_user[discord_user_id] = {'agent_id': memgpt_agent_id}
	logging.info(f"Storing agent ID: {memgpt_agent_id}")
	await save_user_data()
	return discord_to_memgpt_user[discord_user_id]


async def save_user_data():
	logging.info(f"Saving user data")
	async with aiofiles.open(USER_DATA_FILE, "w") as f:
		await f.write(json.dumps(discord_to_memgpt_user, indent=4))
		logging.info(f"Saved User Config")

async def send_request_to_memgpt(config, messages, user_id, discord_username, message):
	memgpt_agent_data = await get_or_create_memgpt_agent(config, user_id, discord_username, message)
	agent_id = memgpt_agent_data['agent_id']
	client = AsyncLetta(base_url=config["MemGPTEndpoint"], timeout=300)
	message_content = messages[0]['content']

	try:
		response = await client.agents.messages.create(
			agent_id=agent_id,
			messages=[MessageCreate(role="user", content=message_content)],
			use_assistant_message=False
		)

		logging.info(f"MemGPT raw response: {response}")

		if response and hasattr(response, 'messages') and isinstance(response.messages, list):
			return_message = ""
			for msg in response.messages:
				if hasattr(msg, 'reasoning') and msg.reasoning:
					logging.info(f"Agent reasoning: {msg.reasoning}")

				if hasattr(msg, 'message_type') and msg.message_type == 'assistant_message':
					if hasattr(msg, "function_call") and msg.function_call:
						try:
							arguments = json.loads(msg.function_call.arguments or '{}')

							# Check if a function call name is present and is send_message
							if msg.function_call.name == "send_message":
								return_message = arguments.get('message', '')
								break
							else:
								logging.info(f"Function Call with name {msg.function_call.name} was not send_message.")
						except json.JSONDecodeError:
							logging.error("Failed to decode tool call arguments from MemGPT")
							# return_message = "I'm having trouble processing the tool call response."
							break
					elif hasattr(msg, 'content') and msg.content:
						return_message = msg.content
						break
					else:
						logging.info("Message type is assistant_message, but no content or function call was found.")

				elif hasattr(msg, "tool_call") and msg.tool_call:
					try:
						arguments = json.loads(msg.tool_call.arguments)
						return_message = arguments.get('message', '')
						break
					except json.JSONDecodeError:
						logging.error("Failed to decode tool call arguments from MemGPT")
						# return_message = "I'm having trouble processing the tool call response."
						break
				elif hasattr(msg, "status") and msg.status:
					logging.info(f"Tool response information: {msg.status}")
			return return_message
		else:
			logging.error(f"Unexpected response format from MemGPT: {response}")
	except Exception as e:  # Catch any Letta client exceptions
		logging.error(f"MemGPT API request failed: {e}")
		raise Exception(f"MemGPT API request failed: {e}")
	
async def load_model(config, message):
	async with message.channel.typing():
		sd_model = message.content
		async with aiohttp.ClientSession() as session1:
			url1 = config["SDURL"] + "/sdapi/v1/refresh-checkpoints"
			async with session1.post(url1) as response1:
				response1.raise_for_status()
				status1 = await response1.text()
				logging.info("Refreshed checkpoints")

		json_payload = {
			"sd_model_checkpoint": sd_model.replace("load model ", "")
		}
		async with aiohttp.ClientSession()  as session:
			async with session.post(url=config["SDURL"] + "/sdapi/v1/options", json=json_payload) as response:
				response.raise_for_status()

		with open("config/config.json", "r") as f:
			config = json.load(f)

		config["SDmodel"] = sd_model.replace("load model ", "")

		with open("config/config.json", "w") as f:
			json.dump(config, f, indent=4)
			f.flush()
		logging.info ("Model loaded.")

async def txt2vid(config,message,bot_name):
	if message.content.startswith("txt2vid"):
		prompt = message.content.replace("txt2vid", "").strip()
		prompt = prompt.content.replace(bot_name,  "").strip()
	else:
		prompt = None

	size = "512x512"

	data = {
		"prompt": prompt,
		"size": size,
		"model": "txt2vid",
	}

	async with aiohttp.ClientSession() as session:
		async with session.post(config["SecondaryOpenAPIEndpoint"] + "/images/generations", json=data) as response:
			response.raise_for_status()
			response_data = await response.json()

			image_url = response_data["candidates"][0]["url"]
			logging.info(f"Generated image URL: {image_url}")
			await message.channel.send(image_url)
