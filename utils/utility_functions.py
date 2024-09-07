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

async def generate_response(config, user_id, discord_username, user_message_histories, use_memgpt, message=None, additional_instructions=None, prompt=None, include_personality=True, upscale=False):
	try:
		client=None
		# Attempt to use MemGPT as the primary client
		# client = AsyncOpenAI(
		# 	base_url=config.get("MemGPTEndpoint", config["OpenAPIEndpoint"]),  # Use MemGPTEndpoint if available, fallback to OpenAPIEndpoint
		# 	api_key=config.get("MemGPTBearer", config["OpenAPIKey"])  # Use MemGPTBearer if available, fallback to OpenAPIKey
		# )
		response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, use_memgpt, message, additional_instructions, prompt, include_personality)
		if response: # Successful response from MemGPT
			return response
	except Exception as e:
		logging.error(f"An error occurred during MemGPT API call: {str(e)}")

	# If MemGPT fails, try OpenAI as the secondary client
	try:
		if config["SecondaryOpenAPIEndpoint"] and config["SecondaryOpenAPIKey"]:
			client = AsyncOpenAI(base_url=config["SecondaryOpenAPIEndpoint"], api_key=config["SecondaryOpenAPIKey"])
			response = await try_generate_response(client, config, user_id, discord_username, user_message_histories, message, additional_instructions, prompt, include_personality,use_memgpt=False)
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
			if isinstance(prompt, str)and prompt != None:
				logging.info("Using provided prompt:")
				logging.debug(prompt)
				messages.append({'role': 'user', 'content': prompt})
			else:
				logging.warning(f"Invalid prompt type: expected string, received {type(prompt)}")

			logging.info(f"Sending data to {'MemGPT' if use_memgpt else 'OpenAI'}: {messages}")

			# Send request to OpenAI or MemGPT based on use_memgpt flag
			if use_memgpt:
				response = await send_request_to_memgpt(config, messages, user_id, discord_username)
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
				response = await client.chat.completions.create(
					messages=messages,
					model=config["OpenaiModel"],
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


# Call save_user_data whenever you modify the dictionary
async def get_or_create_memgpt_agent_and_user(config, user_id, message, discord_username):
	"""Gets or creates a MemGPT agent and user for the given Discord ID."""
	discord_user_id = str(user_id)  # Convert to string for consistency
	if discord_user_id in discord_to_memgpt_user:
		return discord_to_memgpt_user[discord_user_id]

	headers = {
		'accept': 'application/json',
		'authorization': f'Bearer {config["MemGPTBearer"]}',
		'content-type': 'application/json'
	}
	
	async def create_memgpt_user():
		url = f"{config['MemGPTEndpoint']}/admin/users"
		async with aiohttp.ClientSession() as session:
			async with session.post(url, headers=headers, json={}) as resp:
				logging.info(f"MemGPT User Creation Response Status: {resp.status}")
				logging.info(f"MemGPT User Creation Response Body: {await resp.text()}")
				if resp.status == 200:  # Successful user creation
					response_data = await resp.json() 
					logging.info(f"MemGPT User Creation Response Body: {response_data}") 

					# Instead of returning a tuple, return a dictionary
					return {
						'user_id': response_data['user_id'], 
						'api_key': response_data['api_key']
					} 
				else:
					error_text = await resp.text()
					logging.error(f"MemGPT user creation failed: {error_text}")
					raise Exception(f"Failed to create MemGPT user: {error_text}")

	async def create_memgpt_agent(user_api_key,discord_username, config):
		url = f"{config['MemGPTEndpoint']}/api/agents"
		agent_data = {
			"description": "An agent created for Discord user",  # You can customize this
			"user_id": user_api_key,
			"config": {
				"name": f"Agent-{discord_username}",
				"preset": "memgpt_chat", 
				"human": discord_username,
				"persona": "jennifer"
			},
			# "message_ids": [],  # You can add message IDs if needed
			# "memory": {
			# 	"memory": {
			# 		"messages": {
			# 			"value": [],
			# 			"limit": 100  # Or another appropriate limit
			# 		}
			# 	},
			# 	"prompt_template": "{% for section, block in memory.items() %}<{{ section }} characters=\"{{ block.value|length }}/{{ block.limit }}\">"
			# 	"{{ block.value }}"
			# 	"</{{ section }}>{% if not loop.last %}"
			# 	"{% endif %}{% endfor %}"  # A basic prompt template
			# },
			# "tools": [],  # Add tools if necessary
			"system": config["MemGPTPersonality"],  # Customize this
			"llm_config": {
				"model": config["MemGPTmodel"],  # Or your desired model
				"model_endpoint_type": "openai",  # Or your desired endpoint type
				"model_endpoint": config["MemGPTModelEndpoint"],  # If necessary, specify the endpoint
				"context_window": 8192  # Or your desired context window
			},
			"embedding_config": {
				"embedding_endpoint_type": "openai",  # Or your desired endpoint type
				"embedding_model": "text-embedding-ada-002",  # Or your desired embedding model
				"embedding_dim": 1536,  # Or your desired embedding dimension
				"embedding_chunk_size": 300,  # Or your desired chunk size
			}
		}
		headers = {
			'authorization': f'Bearer {user_api_key}' 
		}
		logging.info(f"Agent Data being sent: {agent_data}")
		async with aiohttp.ClientSession() as session:
			async with session.post(url, headers=headers, json=agent_data) as resp:
				try:
					resp.raise_for_status()  # Raise an exception for bad status codes
					response_data = await resp.json()
					logging.info(f"MemGPT Agent Creation Response Data: {response_data}")
					return response_data['agent_state']['id']
				except (aiohttp.ClientError, KeyError, json.JSONDecodeError) as e:
					error_text = await resp.text()
					logging.error(f"MemGPT agent creation failed: {error_text}, Status: {resp.status}, Exception: {e}")
					return None  # or raise a more informative exception 


	# Create user and agent
	memgpt_user_data = await create_memgpt_user() 
	memgpt_agent_id = await create_memgpt_agent(memgpt_user_data['api_key'],discord_username,config)  # Use the API key for the new user

	# Store user and agent data
	discord_to_memgpt_user[discord_user_id] = {
		'user_id': memgpt_user_data['user_id'],
		'api_key': memgpt_user_data['api_key'],  # Store the correct API key
		'agent_id': memgpt_agent_id
	}
	logging.info(f"Storing user data: {memgpt_user_data['user_id']}, {memgpt_agent_id}")
	await save_user_data()
	return discord_to_memgpt_user[discord_user_id]

# Function to save user data to JSON file
async def save_user_data():
	logging.info(f"Saving user data")
	async with aiofiles.open(USER_DATA_FILE, "w") as f:
		await f.write(json.dumps(discord_to_memgpt_user, indent=4))
			

async def send_request_to_memgpt(config, messages, user_id, discord_username):
	memgpt_user_data = await get_or_create_memgpt_agent_and_user(config, user_id, messages, discord_username)
	logging.info(f"MemGPT User Data: {memgpt_user_data}")

	# Correctly extract values from the dictionary
	api_key = memgpt_user_data['api_key']
	agent_id = memgpt_user_data['agent_id'] 
	
	logging.info(f"MemGPT API Key: {api_key}")
	logging.info(f"Using agent_id: {agent_id}")

	
	message_content = messages[0]['content']
	headers = {
		'accept': 'application/json',
		'authorization': f'Bearer {api_key}',
		'content-type': 'application/json'
	}
	# Construct the data payload according to MemGPT's API
	data = {
		"message": message_content,
		'name': discord_username,
		'stream': False,
		"run_async": False,
		"stream_steps": False,
		"stream_tokens": False,
		"return_message_object": False
	}
	url = f"{config['MemGPTEndpoint']}/api/agents/{agent_id}/messages"
	logging.info(f"Sending data to MemGPT: {data}")
	async with aiohttp.ClientSession() as session:
		async with session.post(url, headers=headers, json=data) as resp:
			if resp.status == 200:
				response_data = await resp.json()
				logging.info(f"MemGPT response: {response_data}")

				messages = response_data.get('messages', [])
				if messages:
					for message in messages:
						if 'function_call' in message:
							function_call = message['function_call']
							if 'arguments' in function_call:
								arguments = json.loads(function_call['arguments'])
								if 'message' in arguments:
									assistant_reply = arguments['message']
									logging.info(f"Assistant reply: {assistant_reply}")
									return assistant_reply
				# 				else:
				# 					print("No 'message' found in function_call arguments.")
				# 		else:
				# 			print("No 'function_call' found in message.")
				# else:
				# 	print("No messages found in response.")
			else:
				error_text = await resp.text()
				logging.error(f"MemGPT API request failed: {error_text}")
				raise Exception(f"MemGPT API request failed: {error_text}")

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