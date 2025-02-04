from functools import cache
from openai import AsyncOpenAI
import logging
import asyncio
from io import BytesIO
import sys
import discord
import json
from threading import Thread
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
from logging.handlers import TimedRotatingFileHandler
import aiohttp
from discord.ext.voice_recv.extras import *
import os
import aiofiles
import docker
from letta_client import AsyncLetta, MessageCreate

discord.opus._load_default()
# Define a function to load the config
def load_config(config_path):
	try:
		with open(config_path, "r") as file:
			config = json.load(file)
			return config
	except FileNotFoundError:
		logging.error("Config file not found. Please check the file path.")
	except PermissionError:
		logging.error("Permission denied. Unable to open Config file.")
	except Exception as e:
		logging.error("An error occurred while loading config: " + str(e))
	return None
# Define a class to handle file system events
class ConfigFileHandler(FileSystemEventHandler):
	def __init__(self, config_path, on_change):
		super().__init__()
		self.config_path = config_path
		self.on_change = on_change

	def on_modified(self, event):
		if event.src_path == self.config_path:
			logging.info("Config file has been modified. Reloading config...")
			reload_config()
			log_setup(config)
		else:
			logging.debug("Detected modification in a file, but it is not the config file.")

# Define a function to observe config changes
def observe_config_changes():
	# Create a FileSystemEventHandler to watch the config file
	handler = ConfigFileHandler(config_path, reload_config)
	# Start observing the config file
	observer = PollingObserver()
	observer.schedule(handler, config_path, recursive=False)
	observer.start()

	try:
		while True:
			observer.join()
	except  KeyboardInterrupt:
		observer.stop()
		observer.join()


# Define a function to reload the config
def reload_config():
	global config
	config = load_config(config_path)
	client= docker.from_env()
	try:
		container = client.containers.get({config["Name"]})
		container.restart()
		logging.info("Container restarted")
	except docker.errors.APIError as e:
		logging.error(f"Failed to restart container: {e}")

	logging.info(f"Config file successfully loaded with content: {config}")

# Define the config path
config_path = "./config/config.json"

# Load the config initially
config = load_config(config_path)

# Start file system observer in a separate thread
observer_thread = Thread(target=observe_config_changes, daemon=True)
observer_thread.start()

def log_setup(config):
	# Assuming "LogLevel" is a key in the config dictionary
	log_level = config.get("LogLevel", "INFO")  # Default to INFO if LogLevel is not present

	logging.basicConfig(
		level=log_level,
		format="%(asctime)s [%(levelname)s] %(message)s",
		handlers=[
			TimedRotatingFileHandler("app.log", when="midnight", backupCount=7, encoding='utf-8'),
			logging.StreamHandler(sys.stdout)
		]
	)

async def generate_response(config, user_id, discord_username, user_message_histories, message=None, additional_instructions=None, prompt=None):
	try:
		client=None
		response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid=False, use_memgpt=True)
		if response: # Successful response from MemGPT
			return response
	except Exception as e:
		logging.error(f"An error occurred during MemGPT API call: {str(e)}")

	# If MemGPT fails, try OpenAI as the secondary client
	try:
		openai_valid=True
		if config["OpenAPIEndpoint"] and config["OpenAPIKey"]:
			client = AsyncOpenAI(base_url=config["OpenAPIEndpoint"], api_key=config["OpenAPIKey"])
			response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid, use_memgpt=False)
			if response:
				return response
	except Exception as e:
		logging.error(f"An error occurred during OpenAI API call: {str(e)}")
		try:
			openai_valid=False
			if config["SecondaryOpenAPIEndpoint"] and config["SecondaryOpenAPIKey"]:
				client = AsyncOpenAI(base_url=config["SecondaryOpenAPIEndpoint"], api_key=config["SecondaryOpenAPIKey"])
				response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid, use_memgpt=False)
				if response:
					return response
		except Exception as e:
			logging.error(f"An error occurred during second OpenAI API call: {str(e)}")
		if message:
			await message.channel.send("I can't talk right now please try back later.")
	raise  # Re-raise the exception if both MemGPT and OpenAI fail


async def try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, openai_valid, use_memgpt):
	try:
			# Determine recent message content
			recent_message_content = ""
			if user_id in user_message_histories and user_message_histories[user_id]:
				recent_message_content = user_message_histories[user_id][-2]['content'] if len(user_message_histories[user_id]) > 1 else ""
			logging.debug(f"Recent message content: {recent_message_content}")

			# Construct messages
			messages = []

			# Include personality message
			if not (use_memgpt or prompt):
				personality_command = f"You are {config['Personality']}."
				messages.append({'role': 'system', 'content': personality_command})
				logging.info("Included personality message.")

			if not use_memgpt and recent_message_content and (message is None or recent_message_content != message.content) and prompt is None:
				messages.append({'role': 'user', 'content': recent_message_content})
				logging.info("Included recent user message.")

			# Include message content if provided and if prompt is None
			if message and isinstance(message.content, str) and prompt is None:
				messages.append({'role': 'user', 'content': message.content})
				logging.info("Included message content from provided message.")

			# Include prompt if provided and not None
			if isinstance(prompt, str)and prompt != None:
				logging.info("Using provided prompt:")
				logging.debug(prompt)
				messages.append({'role': 'user', 'content': prompt})

			logging.info(f"Sending data to {'MemGPT' if use_memgpt else 'OpenAI'}: {messages}")

			# Send request to OpenAI or MemGPT based on use_memgpt flag
			if use_memgpt:
				response = await send_request_to_memgpt(config, messages, user_id, discord_username, message)
				if response:
					logging.info(f"MemGPT Response: {response}")
					# Chunk if needed
					if len(response) > 2000:
						chunks = [response[i:i + 2000] for i in range(0, len(response), 2000)]
						return chunks
					else:
						return response
				else:
					logging.warning("MemGPT did not return a response.")
					# Handle cases where MemGPT didn't return a response
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
				# Chunk if needed
				response_text = response.choices[0].message.content
				if len(response_text) > 2000:
					chunks = [response_text[i:i + 2000] for i in range(0, len(response_text), 2000)]
					return chunks
				else:
					return [response_text]

	except Exception as e:
		logging.error("An error occurred during API call in try_generate_response: " + str(e))
		raise  # Re-raise the exception to propagate it back to the caller

# File path to store user data
USER_DATA_FILE = "/app/config/memgpt_user_data.json"

# Dictionary to store Discord ID to MemGPT user data
# Load from file if it exists
if os.path.exists(USER_DATA_FILE):
	with open(USER_DATA_FILE, "r") as f:
		discord_to_memgpt_user = json.load(f)
else:
	discord_to_memgpt_user = {}

#Call save_user_data whenever you modify the dictionary
async def get_or_create_memgpt_agent(config, user_id, discord_username, message):
	"""Gets or creates a MemGPT agent for the given Discord ID."""
	discord_user_id = str(user_id)
	if discord_user_id in discord_to_memgpt_user:
		return discord_to_memgpt_user[discord_user_id]

	client = AsyncLetta(base_url=config["MemGPTEndpoint"])  # Letta Client

	async def create_memgpt_agent(discord_username, message):
		await message.channel.send("Creating a personalized agent for you. Please wait a moment.")

		agent_data = {
				"memory_blocks": # Updated memory structure
				[
					{
					 "label": "human",
					 "value": f"The human's name is {discord_username}"
					},

					{"label": "persona",
					"value": config["MemGPTPersonality"]
					}
				],
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
			}

		}

		logging.debug(f"Agent creation data: {json.dumps(agent_data, indent=2)}")

		try:
			response = await client.agents.create(**agent_data) # Use Letta client
			agent_id = response.id # Extract agent ID from response
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

# Function to save user data to JSON file
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
	"""Loads a Stable Diffusion model and updates the config file with the new model name."""
	async with message.channel.typing():
		sd_model = message.content
		# Send another POST request to the specified URL with the specified JSON payload
		async with aiohttp.ClientSession() as session1:
		# Refresh checkpoints
			url1 = config["SDURL"] + "/sdapi/v1/refresh-checkpoints"
			async with session1.post(url1) as response1:
				response1.raise_for_status()
				status1 = await response1.text()
				logging.info("Refreshed checkpoints")

		# Construct the JSON payload for the POST request
		json_payload = {
			"sd_model_checkpoint": sd_model.replace("load model ", "")
		}
		# Send the POST request to load the model
		async with aiohttp.ClientSession()  as session:
			async with session.post(url=config["SDURL"] + "/sdapi/v1/options", json=json_payload) as response:
				response.raise_for_status()

		# Update the config file with the new model name
		with open("config/config.json", "r") as f:
			config = json.load(f)

		config["SDmodel"] = sd_model.replace("load model ", "")

		with open("config/config.json", "w") as f:
			json.dump(config, f, indent=4)
			f.flush()
		logging.info ("Model loaded.")

async def txt2vid(message,bot_name):
	# Check if the message contains a prompt
	if message.content.startswith("txt2vid"):
		prompt = message.content.replace("txt2vid", "").strip()
		prompt = prompt.content.replace(bot_name,  "").strip()
	else:
		prompt = None

	# Set the size for the txt2vid request
	size = "512x512"

	# Construct the JSON payload for the txt2vid request
	data = {
		"prompt": prompt,
		"size": size,
		"model": "txt2vid",
	}

	# Send the POST request to the txt2vid API
	async with aiohttp.ClientSession() as session:
		async with session.post(config["SecondaryOpenAPIEndpoint"] + "/images/generations", json=data) as response:
			response.raise_for_status()
			response_data = await response.json()

			# Process the response from the txt2vid API
			image_url = response_data["candidates"][0]["url"]
			logging.info(f"Generated image URL: {image_url}")
			await message.channel.send(image_url)

