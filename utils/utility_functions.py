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

async def generate_response(config, user_id, discord_username, user_message_histories, message=None, additional_instructions=None, prompt=None, include_personality=True, upscale=False):
	try:
		# Attempt to use MemGPT as the primary client
		client = AsyncOpenAI(
			base_url=config.get("MemGPTEndpoint", config["OpenAPIEndpoint"]),  # Use MemGPTEndpoint if available, fallback to OpenAPIEndpoint
			api_key=config.get("MemGPTBearer", config["OpenAPIKey"])  # Use MemGPTBearer if available, fallback to OpenAPIKey
		)
		response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, include_personality, use_memgpt=True)
		if response: # Successful response from MemGPT
			return response
	except Exception as e:
		logging.error(f"An error occurred during MemGPT API call: {str(e)}")

	# If MemGPT fails, try OpenAI as the secondary client
	try:
		if config["SecondaryOpenAPIEndpoint"] and config["SecondaryOpenAPIKey"]:
			client = AsyncOpenAI(base_url=config["SecondaryOpenAPIEndpoint"], api_key=config["SecondaryOpenAPIKey"])
			response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, include_personality, use_memgpt=False)
			if response:
				return response
	except Exception as e:
		logging.error(f"An error occurred during second OpenAI API call: {str(e)}")
		if message:	
			await message.channel.send("I can't talk right now please try back later.")		
	raise  # Re-raise the exception if both MemGPT and OpenAI fail
async def try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, include_personality, use_memgpt):
	try:
			# Determine recent message content
			recent_message_content = ""
			if user_id in user_message_histories and user_message_histories[user_id]:
				recent_message_content = user_message_histories[user_id][-2]['content'] if len(user_message_histories[user_id]) > 1 else ""
			logging.debug(f"Recent message content: {recent_message_content}")

			# Construct messages
			messages = []

			# Include additional instructions
			if additional_instructions:
				messages.extend(additional_instructions)
				logging.info("Included additional instructions.")

			# Include personality message
			if include_personality and not use_memgpt:
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
			if isinstance(prompt, str):
				logging.info("Using provided prompt:")
				logging.debug(prompt)
				messages.append({'role': 'user', 'content': prompt})

			# Wrap the messages in a list if it's not already
			if not isinstance(messages, list):
				messages = [messages]

			logging.info(f"Sending data to {'MemGPT' if use_memgpt else 'OpenAI'}: {messages}")


			# Send request to OpenAI or MemGPT based on use_memgpt flag

			if use_memgpt:
				response_data = await send_request_to_memgpt(config, messages, user_id, discord_username)
				response_text = response_data.get('assistant_message', '')  # Extract assistant message

				# Chunking (adjust if necessary based on MemGPT's response structure)
				if len(response_text) > 2000:
					chunks = [response_text[i:i + 2000] for i in range(0, len(response_text), 2000)]
					return chunks
				else:
					return [response_text]
			else:
				response = await client.chat.completions.create(
					messages=messages,
					model=config["OpenaiModel"],
				)

			logging.info("API response received.")
			logging.debug(response)

			# Check the length of the response
			response_text = response.choices[0].message.content
			if isinstance(response, str) and len(response_text) > 2000: 
				# Split the response into chunks of 2000 characters
				chunks = [response_text[i:i + 2000] for i in range(0, len(response_text), 2000)]
				return chunks
			else:
				return [response_text]

	except Exception as e:
		logging.error("An error occurred during OpenAI API call: " + str(e))
		raise  # Re-raise the exception to propagate it back to the caller

# File path to store user data
USER_DATA_FILE = "memgpt_user_data.json"

# Dictionary to store Discord ID to MemGPT user data
# Load from file if it exists
if os.path.exists(USER_DATA_FILE):
	with open(USER_DATA_FILE, "r") as f:
		discord_to_memgpt_user = json.load(f)
else:
	discord_to_memgpt_user = {}  


# Call save_user_data whenever you modify the dictionary
async def get_or_create_memgpt_user(config, user_id, message):
	"""Gets or creates a MemGPT user for the given Discord ID."""
	discord_user_id = user_id
	if discord_user_id in discord_to_memgpt_user:
		return discord_to_memgpt_user[discord_user_id]

	headers = {
		'accept': 'application/json',
		'authorization': f'Bearer {config["MemGPTBearer"]}',  # Admin Bearer token
		'content-type': 'application/json'
	}

	url = f"{config['MemGPTEndpoint']}/admin/users"

	async with aiohttp.ClientSession() as session:
		async with session.post(url, headers=headers, json={}) as resp: # <--- Change from get to post, remove params=data
			logging.info(f"MemGPT User Creation Response Status: {resp.status}")
			logging.info(f"MemGPT User Creation Response Headers: {resp.headers}")
			logging.info(f"MemGPT User Creation Response Body: {await resp.text()}") 
			if resp.status == 200:  # Successful user creation
				response_data = await resp.json()

				# Store user_id and api_key
				discord_to_memgpt_user[discord_user_id] = {
					'user_id': response_data['user_id'],
					'api_key': response_data['api_key']
				}
				await save_user_data()
				return discord_to_memgpt_user[discord_user_id]
			else:
				error_text = await resp.text()
				logging.error(f"MemGPT user creation failed: {error_text}")
				raise Exception(f"Failed to create MemGPT user: {error_text}")

async def send_request_to_memgpt(config, messages, user_id, discord_username):
	"""Sends the chat request to MemGPT using the pre-defined agent."""

	memgpt_user_data = await get_or_create_memgpt_user(config, user_id, messages)
	memgpt_api_key = memgpt_user_data['api_key']
	memgpt_agent_id = config["MemGPTAgent"]
	message_content = messages[0]['content']

	headers = {
		'accept': 'application/json',
		'authorization': f'Bearer {memgpt_api_key}',
		'content-type': 'application/json'
	}

	# Construct the data payload according to MemGPT's API
	data = {
		"message": message_content,  # Send as a single string
		'stream': False,
		"run_async": False,
		"stream_steps": False,
		"stream_tokens": False,
		"return_message_object": False
	}

	url = f"{config['MemGPTEndpoint']}/api/agents/{memgpt_agent_id}/messages"

	logging.info(f"Sending data to MemGPT: {data}")

	async with aiohttp.ClientSession() as session:
		async with session.post(url, headers=headers, json=data) as resp:
			if resp.status == 200:
				response_data = await resp.json()
				logging.info(f"MemGPT response: {response_data}")

				# Accessing the response data
				messages = response_data.get('messages', [])
				if messages: 
					first_message = messages[0]
					assistant_reply = first_message.get('text', '')
					print(f"MemGPT Assistant Reply: {assistant_reply}") 

					# Access other fields like this:
					message_id = first_message.get('id', [''])[0]
					created_at = first_message.get('created_at')
			else:
				error_text = await resp.text()
				logging.error(f"MemGPT API request failed: {error_text}")
				raise Exception(f"MemGPT API request failed: {error_text}")

# Function to save user data to JSON file
async def save_user_data():
	with open(USER_DATA_FILE, "w") as f:
		json.dump(discord_to_memgpt_user, f, indent=4)
			
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

async def teamviewer(config,message):
	import pexpect
	# Create a Pexpect object for the SSH connection
	ssh_conn = pexpect.spawn('ssh bot@192.168.128.134')
	if ssh_conn.expect('yes/no/fingerprint:'):
		ssh_conn.sendline('yes')

	# Expect the SSH password prompt
	if ssh_conn.expect('password:'):
		# Send the SSH password
		ssh_conn.sendline('password')

	# Expect the SSH command prompt
	ssh_conn.expect('[$#]')

	# Send the command to run the update.sh script
	ssh_conn.sendline('sudo /usr/local/bin/teamviewer.sh')