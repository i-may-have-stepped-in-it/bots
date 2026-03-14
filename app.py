import discord
import json
import time
import logging
import asyncio
import os
import sys
import aiohttp
import tracemalloc

from utils import *
from discord import VoiceState
from openai import AsyncOpenAI
from openai import OpenAI
from math import log
from discord.errors import *
from collections import namedtuple
from utils.voice_recv_class import *
from utils.utility_functions import *
from utils.image_gen import handle_image_generation
from utils.image_gen import print_available_models
from utils.interactions import handle_message_processing, save_message_histories
from watchdog.observers.polling import PollingObserver
from utils.config_gen import load_config, config_path, log_setup, handle_config_change, ConfigFileHandler
import yt_dlp as youtube_dl

sys.path.insert(0, './utils/')
tracemalloc.start()

# Define a named tuple for message processing tasks.
Task = namedtuple('Task', 'config, message, user_message_histories, bot, history_file_name')
# Define a named tuple for image generation tasks.
Draw_Task = namedtuple('Draw_Task', 'config, message, user_message_histories, bot, draw_msg')

config = load_config(config_path)  # Loads the bot's configuration from a file.
if config is None:
	sys.exit(1)  # Exits if the configuration file could not be loaded.

observer = None  # Initializes a file system observer to None.

image_queue = asyncio.Queue()  # Creates a queue for image generation tasks.
message_queue = asyncio.Queue()  # Creates a queue for message processing tasks.
active_users = {}  # Changed to dict to store last interaction time (user_id: last_interaction_time)
music_players = {}  # guild_id: MusicPlayer

youtube_dl.utils.bug_report_message = lambda: ''

ytdl_format_options = {
	'format': 'bestaudio/best',
	'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
	'restrictfilenames': True,
	'noplaylist': True,
	'nocheckcertificate': True,
	'ignoreerrors': False,  # Changed to False to raise errors
	'logtostderr': False,
	'quiet': True,
	'no_warnings': True,
	'default_search': 'auto',
	'source_address': '0.0.0.0',  # Bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
	'options': '-vn',  # Disable video
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

async def worker(image_queue):
	# Image generation worker function.
	while True:
		# Get the image_queue
		config, message, user_message_histories, bot, draw_msg = await image_queue.get()
		try:
			await handle_image_generation(config, message, user_message_histories, bot, draw_msg)
		except Exception as e:
			logging.error("An error occurred in image generation queue: " + str(e))
		finally:
			image_queue.task_done()

async def worker2(message_queue):
	# Message processing worker function.
	while True:
		config, message, user_message_histories, history_file_name, bot = await message_queue.get()
		try:
			await handle_message_processing(config, message, user_message_histories, history_file_name)
		except Exception as e:
			logging.error("An error occurred in message processing queue: " + str(e))
		finally:
			message_queue.task_done()

class MusicPlayer:
	def __init__(self, channel, bot):
		self.bot = bot
		self.channel = channel
		self.queue = asyncio.Queue()
		self.now_playing = None
		self.loop = False  # loop the current song
		self.volume = 0.5  # Volume level
		self.voice_client = None  # The voice client

	async def safe_disconnect(self):
		# Safely disconnect from voice
		try:
			if self.voice_client:
				await self.voice_client.disconnect()
				self.voice_client = None
		except Exception as e:
			logging.error(f"Error during disconnect: {e}")

	async def join(self, channel: discord.VoiceChannel):
		"""Joins a voice channel."""
		try:
			if self.voice_client and self.voice_client.is_connected():
				await self.voice_client.move_to(channel)
			else:
				self.voice_client = await channel.connect()

		except Exception as e:
			logging.error(f"Error joining voice channel: {e}")
			raise

	async def disconnect(self):
		# Disconnect from the voice channel
		await self.safe_disconnect()

	def is_playing(self):
		# Checks is anything is playing
		return self.voice_client and self.voice_client.is_playing()

	async def enqueue(self, url):
		# Add a song to the queue
		await self.queue.put(url)

	async def play_next(self):
		# Plays the next song in the queue
		if self.voice_client is None:
			logging.warning("Voice client not initialized, cannot play next.")
			return

		if self.queue.empty():
			self.now_playing = None
			await self.channel.send("Queue is empty.  Leaving voice channel.")  # Send via the channel
			await self.safe_disconnect()
			return

		url = await self.queue.get()
		try:
			loop = asyncio.get_event_loop()
			data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
		except Exception as e:
			await self.channel.send(f"There was an error when processing this song. {e}")  # Send via the channel
			return

		# Check if 'entries' key exists. If not, treat 'data' as a single video
		if 'entries' in data:
			# take first item from a playlist
			if data['entries']: # Check that the entries list isn't empty
				data = data['entries'][0]
			else:
				await self.channel.send("Playlist is empty.")
				return # stop processing this track.
		# data is now the video entry.

		filename = data['url']
		self.now_playing = data['title']

		self.voice_client.volume = self.volume
		source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(filename, **ffmpeg_options))
		self.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop))
		await self.channel.send(f"Now playing: {self.now_playing}")  # Send via the channel

	async def set_volume(self, volume):
		# Sets the volume of the player
		self.volume = volume
		if self.voice_client and self.voice_client.source:
			self.voice_client.source.volume = volume

	async def stop(self):
		# Stops the player
		if self.voice_client and self.voice_client.is_playing():
			self.voice_client.stop()
			self.now_playing = None
			await self.channel.send("Playback stopped.")  # Send via the channel

	async def skip(self):
		# Skips the currently playing song
		if self.voice_client and self.voice_client.is_playing():
			self.voice_client.stop()
			await self.channel.send("Song skipped.")  # Send via the channel
		else:
			await self.channel.send("Nothing is playing to skip.")  # Send via the channel

# Command Handler
import re

async def handle_command(message, config, user_message_histories, bot, history_file_name):
	"""Handles commands starting with '!'."""
	bot_name = config["Name"]
	full_message = message.content  # Keep original case for arguments
	interaction_timeout = config.get("InteractionTimeout", 60)  # Default timeout in seconds
	user_id = message.author.id #Grab User ID

	# Extract the command using regex or simple strip
	match = re.match(rf"^{re.escape(bot_name)}[^\w\s]*\s*(!\S+.*)", full_message, re.IGNORECASE)
	if match:
		command = match.group(1).strip()  # Extract the command after the bot name
	else:
		command = full_message.strip()
	
	logging.info(f"Processing command: '{command}'")
	command_lower = command.lower()

	# Check if the bot should process the command (mention, active user, etc.)
	is_triggered = bot_name.lower() in full_message.lower() or bot.user in message.mentions or user_id in active_users
	is_active = user_id in active_users and (time.time() - active_users[user_id]) <= interaction_timeout

	# Always update active_users upon receiving a command, if previously triggered
	if is_triggered:
		active_users[user_id] = time.time()  # Record the new interaction time

	# Prioritize DM channels for command handling without checks
	if message.channel.type == discord.ChannelType.private:
		# Commands to execute in a DM channel
		if command_lower.startswith("!draw") or command_lower.startswith("!send"):
			draw_msg = await message.channel.send("Hang on while I get that for you...")
			image_queue.put_nowait(Draw_Task(config, message, user_message_histories, bot, draw_msg))
			return
		elif command_lower.startswith("!txt2vid"):
			if message.author.id in config["Power_Users"]:
				draw_msg = await message.channel.send("Hang on while I get that for you...")
				await txt2vid(config, draw_msg, config["Name"])
				return
			else:
				await message.channel.send("I'm sorry, you do not have permission to run this command.")
				return
		elif command_lower == "!check models":
			if message.author.id in config["Power_Users"]:
				await print_available_models(config, message)
				return
			else:
				await message.channel.send("I'm sorry, you do not have permission to run this command.")
				return
		elif command_lower.startswith("!teamviewer"):
			await print_available_models(config, message)
			return
		elif command_lower.startswith("!load model"):
			if message.author.id in config["Power_Users"]:
				try:
					load_msg = await message.channel.send(f"Loading model {command[12:].strip()}.")  # Corrected index and use command
					await load_model(config, message)
					await load_msg.edit(content=load_msg.content + "\n" + "Model loaded successfully.")
					return
				except Exception as e:
					logging.error(f"Error loading model: {e}")
					await load_msg.edit(content="I am sorry there is a problem with my camera.")
					return
			else:
				await message.channel.send("I'm sorry, you do not have permission to run this command.")
				return
		elif command_lower.startswith("!change model"):
			model_name = command[13:].strip()
			if model_name:
				try:
					from openclaw import change_openclaw_model
					success = await change_openclaw_model(config, message.author.id, model_name)
					if success:
						config["OpenClawmodel"] = model_name
						from utils.config_gen import save_config, config_path
						save_config(config_path, config)
						await message.channel.send(f"Model changed to {model_name} successfully. My brain is rebooting to apply changes...")
					else:
						await message.channel.send(f"Failed to change model to {model_name}.")
					return
				except Exception as e:
					await message.channel.send(f"Error changing model: {e}")
					return
			else:
				await message.channel.send("Please specify a model name.")
				return
		elif command_lower == "!new session":
			try:
				from openclaw import start_openclaw_new_session
				success = await start_openclaw_new_session(config, message.author.id)
				# Also clear local history
				if str(message.author.id) in user_message_histories:
					user_message_histories[str(message.author.id)] = []
					save_message_histories(history_file_name, user_message_histories)
				
				if success:
					await message.channel.send("New session started successfully.")
				else:
					await message.channel.send("Failed to start new session on Gateway, but local history cleared.")
				return
			except Exception as e:
				logging.error(f"Error starting new session: {e}")
				await message.channel.send(f"Error starting new session: {e}")
				return
		elif command_lower == "!recreate agent":
			try:
				load_msg = await message.channel.send("Recreating agent.")
				# Clear local history first
				if str(message.author.id) in user_message_histories:
					user_message_histories[str(message.author.id)] = []
					save_message_histories(history_file_name, user_message_histories)
				
				from openclaw import delete_openclaw_agent
				await delete_openclaw_agent(config, message.author.id, message.author.display_name)
				
				logging.info("Restarting process...")
				os.execv(sys.executable, [sys.executable] + sys.argv)
				return
			except Exception as e:
				logging.exception(f"Error recreating agent: {e}")
				await load_msg.edit(content=f"I am sorry there is a problem recreating the agent: {e}")
				return
		elif command_lower == "!reset agent":
			try:
				# Clear local history
				if str(message.author.id) in user_message_histories:
					user_message_histories[str(message.author.id)] = []
					save_message_histories(history_file_name, user_message_histories)
				
				from openclaw import reset_openclaw_messages
				await reset_openclaw_messages(config, message.author.id)
				
				await message.channel.send("Messages reset successfully.")
				return
			except Exception as e:
				logging.error(f"Error resetting agent: {e}")
				await message.channel.send("I am sorry there is a problem with resetting the messages.")
				return
		elif command_lower == "!join_vc":
			if message.author.voice:
				try:
					voice_channel_id = message.author.voice.channel.id
					await join_voice_channel(message, voice_channel_id)
					await message.add_reaction("👍")  # Add thumbs up reaction
					return
				except Exception as e:
					logging.error(f"Error joining voice channel via command: {e}")
					await message.channel.send("Failed to join your voice channel.  Check permissions and try again.")
					return
			else:
				await message.channel.send("You must be in a voice channel to use this command.")
				return
		elif command_lower == "!leave_vc":
			if message.guild.voice_client:
				try:
					await message.guild.voice_client.disconnect()
					await message.channel.send("Leaving voice channel.")
					await message.add_reaction("👋")  # Add wave reaction
					return
				except Exception as e:
					logging.error(f"Error leaving voice channel: {e}")
					await message.channel.send("Failed to leave the voice channel.")
					return
			else:
				await message.channel.send("I am not currently in a voice channel.")
				return
		elif command_lower == "!help" or command_lower == "!commands":
			help_msg = await message.channel.send("Here are the commands you can use:")
			help_msg = await message.channel.send("`!join_vc` - Join the voice channel")
			help_msg = await message.channel.send("`!leave_vc` - Leave the voice channel")
			help_msg = await message.channel.send("`!draw <prompt>` - Generate an image based on the prompt")
			help_msg = await message.channel.send("`!txt2vid` - Generate a video based on the prompt (Permissions Required)")
			help_msg = await message.channel.send("`!check models` - Check available models (Permissions Required)")
			help_msg = await message.channel.send("`!load model <model_name>` - Load a specific model (Permissions Required)")
			help_msg = await message.channel.send("`!change model <model_name>` - Change OpenClaw model")
			help_msg = await message.channel.send("`!new session` - Start a new fresh session")
			help_msg = await message.channel.send("`!recreate agent` - Recreate the agent")
			help_msg = await message.channel.send("`!reset agent` - Reset messages")
			help_msg = await message.channel.send("`!play <url>` - Play music from a URL")
			help_msg = await message.channel.send("`!skip` - Skip the current song")
			help_msg = await message.channel.send("`!stop` - Stop the music and clear the queue")
			help_msg = await message.channel.send("`!volume <0.0-1.0>` - Set the volume")
			help_msg = await message.channel.send("`!now_playing` - Shows the current song")
			help_msg = await message.channel.send("`!queue` - Shows the current songs in the queue")
			return
		else:
			await message.channel.send(f"I'm sorry, I cannot run '{command}' here.")
			return

	# Handling commands in regular channels

	if command_lower.startswith("!draw") or command_lower.startswith("!send"):
		draw_msg = await message.channel.send("Hang on while I get that for you...")
		image_queue.put_nowait(Draw_Task(config, message, user_message_histories, bot, draw_msg))
		return
	elif command_lower == "!new session":
		if message.author.id in config["Power_Users"]:
			try:
				from openclaw import start_openclaw_new_session
				success = await start_openclaw_new_session(config, message.author.id)
				# Also clear local history
				if str(message.author.id) in user_message_histories:
					user_message_histories[str(message.author.id)] = []
					save_message_histories(history_file_name, user_message_histories)
				
				if success:
					await message.channel.send("New session started successfully.")
				else:
					await message.channel.send("Failed to start new session on Gateway, but local history cleared.")
				return
			except Exception as e:
				logging.error(f"Error starting new session: {e}")
				await message.channel.send(f"Error starting new session: {e}")
				return
		else:
			await message.channel.send("I'm sorry, you do not have permission to run this command.")
			return
	elif command_lower == "!recreate agent":
		if message.author.id in config["Power_Users"]:
			try:
				load_msg = await message.channel.send("Recreating agent.")
				# Clear local history first
				if str(message.author.id) in user_message_histories:
					user_message_histories[str(message.author.id)] = []
					save_message_histories(history_file_name, user_message_histories)
				
				from openclaw import delete_openclaw_agent
				await delete_openclaw_agent(config, message.author.id, message.author.display_name)
				
				logging.info("Restarting process...")
				os.execv(sys.executable, [sys.executable] + sys.argv)
				return
			except Exception as e:
				logging.exception(f"Error recreating agent: {e}")
				await load_msg.edit(content=f"I am sorry there is a problem recreating the agent: {e}")
				return
		else:
			await message.channel.send("I'm sorry, you do not have permission to run this command.")
			return
	elif command_lower == "!reset agent":
		if message.author.id in config["Power_Users"]:
			try:
				# Clear local history
				if str(message.author.id) in user_message_histories:
					user_message_histories[str(message.author.id)] = []
					save_message_histories(history_file_name, user_message_histories)
				
				from openclaw import reset_openclaw_messages
				await reset_openclaw_messages(config, message.author.id)
				
				await message.channel.send("Messages reset successfully.")
				return
			except Exception as e:
				logging.error(f"Error resetting agent: {e}")
				await message.channel.send("I am sorry there is a problem with resetting the messages.")
				return
		else:
			await message.channel.send("I'm sorry, you do not have permission to run this command.")
			return
	elif command_lower == "!join_vc":
		if message.author.voice:
			try:
				voice_channel_id = message.author.voice.channel.id
				await join_voice_channel(message, voice_channel_id)
				await message.add_reaction("👍")  # Add thumbs up reaction
				return
			except Exception as e:
				logging.error(f"Error joining voice channel via command: {e}")
				await message.channel.send("Failed to join your voice channel.  Check permissions and try again.")
				return
		else:
			await message.channel.send("You must be in a voice channel to use this command.")
			return
	elif command_lower == "!leave_vc":
		if message.guild.voice_client:
			try:
				await message.guild.voice_client.disconnect()
				await message.channel.send("Leaving voice channel.")
				await message.add_reaction("👋")  # Add wave reaction
				return
			except Exception as e:
				logging.error(f"Error leaving voice channel: {e}")
				await message.channel.send("Failed to leave the voice channel.")
				return
		else:
			await message.channel.send("I am not currently in a voice channel.")
			return
	elif command_lower.startswith("!play"):
		try:
			# Add checks to ensure message.guild and message.author.voice are valid
			if not message.guild:
				logging.error("message.guild is None")
				await message.channel.send("I'm sorry, this command can only be used in a server.")
				return
			if not message.author:
				logging.error("message.author is None")
				await message.channel.send("I'm sorry, I cannot determine who sent this message.")
				return

			if not message.author.voice:
				logging.error("message.author.voice is None")
				await message.channel.send("You must be in a voice channel to use this command.")
				return

			guild_id = message.guild.id

			logging.debug(f"music_players state: {music_players}")  # log the music_players dictionary

			if guild_id not in music_players:
				music_players[guild_id] = MusicPlayer(message.channel, bot)

			player = music_players[guild_id]
			if message.author.voice is None:
				await message.channel.send("You must be in a voice channel to use this command.")
				return
			channel = message.author.voice.channel
			if player.voice_client is None or not player.voice_client.is_connected():
				try:
					await player.join(channel)
				except Exception as join_error:
					logging.error(f"Error during player.join(channel): {join_error}")
					await message.channel.send(f"Failed to join the voice channel: {join_error}")
					return

			# Correctly extract the URL after removing the bot name and the command
			prefix = config["Name"].lower() + " !play"
			if message.content.lower().startswith(prefix):
				url = message.content[len(prefix):].strip()  # Extract URL
			else:  # Handle case where bot name isn't explicitly used
				url = message.content[len("!play"):].strip()  # Extract URL
				logging.warning("Bot name not explicitly used in command, using fallback extraction.")

			logging.debug(f"Extracted URL: {url}")  # ADDED: log the extracted url
			if not url:
				await message.channel.send("Please provide a URL to play.")
				return

			await player.enqueue(url)
			if not player.is_playing():
				await player.play_next()
			return
		except Exception as e:
			logging.exception(f"Error processing play command: {e}")
			await message.channel.send(f"I am sorry. There was a problem. {e}")
			return
	elif command_lower == "!skip":
		try:
			guild_id = message.guild.id
			if guild_id in music_players:
				player = music_players[guild_id]
				await player.skip()
				await message.add_reaction("👍")
				return
			else:
				await message.channel.send("I am not currently in a voice channel.")
				return
		except Exception as e:
			logging.error(f"Error processing skip command: {e}")
			await message.channel.send(f"I am sorry. There was a problem. {e}")
			return
	elif command_lower == "!stop":
		try:
			guild_id = message.guild.id
			if guild_id in music_players:
				player = music_players[guild_id]
				await player.stop()
				await message.add_reaction("🛑")
				return
			else:
				await message.channel.send("I am not currently in a voice channel.")
				return
		except Exception as e:
			logging.error(f"Error processing stop command: {e}")
			await message.channel.send(f"I am sorry. There was a problem. {e}")
			return
	elif command_lower.startswith("!volume"):
		try:
			guild_id = message.guild.id
			if guild_id in music_players:
				player = music_players[guild_id]
				try:
					volume = float(message.content.split(" ", 1)[1])
					if 0.0 <= volume <= 1.0:
						await player.set_volume(volume)
						await message.channel.send(f"Volume set to {volume:.2f}")
						await message.add_reaction("🔊")
						return

					else:
						await message.channel.send("Volume must be between 0.0 and 1.0.")
						return
				except ValueError:
					await message.channel.send("Invalid volume level. Please use a number between 0.0 and 1.0.")
					return
			else:
				await message.channel.send("I am not currently in a voice channel.")
				return
		except Exception as e:
			logging.error(f"Error processing volume command: {e}")
		await message.channel.send(f"I am sorry. There was a problem. {e}")
		return
	elif command_lower == "!now_playing":
		try:
			guild_id = message.guild.id
			if guild_id in music_players:
				player = music_players[guild_id]
				if player.now_playing:
					await message.channel.send(f"Now playing: {player.now_playing}")
					return
				else:
					await message.channel.send("Nothing is currently playing.")
					return
			else:
				await message.channel.send("I am not currently in a voice channel.")
				return
		except Exception as e:
			logging.error(f"Error processing now_playing command: {e}")
		await message.channel.send(f"I am sorry. There was a problem. {e}")
		return
	elif command_lower == "!queue":
		try:
			guild_id = message.guild.id
			if guild_id in music_players:
				player = music_players[guild_id]
				if not player.queue.empty():
					queue_list = list(player.queue._queue)
					queue_string = "\n".join([f"{i + 1}. {song}" for i, song in enumerate(queue_list)])
					await message.channel.send(f"**Song queue:**\n{queue_string}")
					return
				else:
					await message.channel.send("The song queue is empty.")
					return
			else:
				await message.channel.send("I am not currently in a voice channel.")
				return
		except Exception as e:
			logging.error(f"Error processing queue command: {e}")
		await message.channel.send(f"I am sorry. There was a problem. {e}")
		return

async def remove_user_from_active(user_id, delay):
	#Removes the user from the active users list
	await asyncio.sleep(delay) #Sleeps to await the action
	if user_id in active_users: #If the user id is in the list
		del active_users[user_id] #Will remove the user from the list
		logging.info(f"User {user_id} removed from active users list.")

async def join_voice_channel(ctx, voice_channel_id: int):
	# Joins a specified voice channel.
	try:
		channel = ctx.guild.get_channel(voice_channel_id) # Gets the voice channel.
		vc = await channel.connect(cls=VoiceRecvClient) # Connects to the voice channel with a custom client.
		logging.info(f"Joined voice channel: {channel}")
		is_listening = vc.is_listening()
		logging.info(f"Initial listening state: {is_listening}")
		vc.handle_audio_processing(ctx) # Handles audio processing in the voice channel.
	except discord.errors.ClientException as e:
		logging.error(f"Error joining voice channel: {e}")
		await  ctx.channel.send("I do not have permission to join that voice channel. Please check my permissions.")
	except discord.errors.InvalidData as e:
		logging.error(f"Error joining voice channel: {e}")
		await ctx.channel.send("Invalid voice channel ID. Please provide a valid ID.")
	except Exception as e:
		logging.error(f"Error joining voice channel: {e}")
		await ctx.channel.send("Unable to join the voice channel. Check my permissions.")
		raise e

async def check_and_leave_voice_channel (guild):
	# Checks if the bot should leave the voice channel.
	voice_client = guild.voice_client # Gets the voice client for the guild.
	if voice_client and voice_client.is_connected():
		if len(voice_client.channel.members) == 1: # Checks if only the bot is in the voice channel.
			await voice_client.disconnect() # Disconnects from the voice channel.

async def start_bot():
	# Starts the Discord bot.
	global observer
	try:
		log_setup(config)  # Sets up logging based on the configuration.
		history_file_name = config["Name"] + "_message_histories.json"  # Sets the name of the message history file.

		def load_message_histories(history_file_name):
			# Loads message histories from a file.
			try:
				if os.path.exists(history_file_name):
					with open(history_file_name, 'r') as file:
						message_histories = json.load(file)
						return message_histories if message_histories is not None else {}
				else:
					logging.info("Message history file not found. Creating a new one.")
					with open(history_file_name, 'w') as file:
						json.dump({}, file)
					return {}
			except Exception as e:
				logging.error("An error occurred while loading message histories: " + str(e))
				return {}

		user_message_histories = load_message_histories(history_file_name)  # Loads user message histories.

		intents = discord.Intents.all()  # Enables all Discord intents.
		bot = discord.AutoShardedClient(intents=intents)  # Creates the Discord bot client.

		asyncio.create_task(worker(image_queue))  # Starts the image generation worker task.
		asyncio.create_task(worker2(message_queue))  # Starts the message processing worker task.

		@bot.event
		async def on_ready():
			# Event handler for when the bot is ready.
			logging.info('Logged in as {0.user}'.format(bot))

		def contains_trigger(message, bot, bot_name, active_users):
			"""
			Checks if the message meets the criteria to be processed.
			"""
			return (
				bot.user in message.mentions or
				(message.reference and message.reference.message_id and (message.channel.type != discord.ChannelType.private)) or  # Ensure this isnt a DM as well
				bot_name.lower() in message.content.lower() or
				message.author.id in active_users
			)

		@bot.event
		async def on_message(message):
			# Event handler for when a message is received.
			try:
				if message.author.bot:
					return  # Ignores messages from other bots.
				await handle_messages(config, message, user_message_histories, history_file_name, bot,message_queue,image_queue)  # Handles the received message.

			except Exception as e:
				logging.error("An error occurred during message handling: %s", str(e))

		@bot.event
		async def on_voice_state_update(member, before, after):
			# Event handler for when a user's voice state changes.
			voice_client = member.guild.voice_client

			if voice_client and voice_client.is_connected():
				if before.channel is None and after.channel is not None:
					print(f"{member.name} joined the voice channel")
				elif before.channel is not None and after.channel is None:
					print(f"{member.name} left the voice channel")
					guild_id = member.guild.id

					if len(voice_client.channel.members) == 1 and bot.user in voice_client.channel.members:  # Only the bot is left
						print("Last user left, disconnecting the bot.")
						if guild_id in music_players:
							player = music_players[guild_id]
							await player.safe_disconnect()  # Use the player's safe disconnect function.
							del music_players[guild_id]  # Delete player

						await check_and_leave_voice_channel(member.guild)  # Use your existing function

		observer = PollingObserver()  # Creates a file system observer.
		handler = ConfigFileHandler(config_path, handle_config_change)  # Creates a file system event handler.
		observer.schedule(handler, os.path.dirname(config_path), recursive=False)  # Schedules the handler to observe the configuration file.
		observer.start()  # Starts the file system observer.

		await bot.start(config["DiscordToken"])  # Starts the Discord bot with the token from the configuration.

	except Exception as e:
		logging.critical('Failed to start bot due to exception: %s', str(e))
		if observer:
			observer.stop()
			observer.join()
		raise

async def handle_messages(config, message, user_message_histories, history_file_name, bot,message_queue,image_queue):
	# Handles incoming messages, determines if the bot should respond.
	global active_users
	ignored_users = config.get("IgnoredUsers", []) # Gets a list of ignored user IDs from the configuration.
	ignored_words = config.get("IgnoredWords", []) # Gets a list of ignored words from the configuration.
	respond_to_mentions = config.get("RespondToMentions", True) #Gets setting to check if the bot should respond to mentions and replies
	interaction_timeout = config.get("InteractionTimeout", 60) # Default timeout in seconds

	try:

		logging.info(f"Received message from {message.author} in channel {message.channel}")
		logging.debug(f"message content: {message.content}")

		if not isinstance(message.channel, (discord.Thread, discord.DMChannel)): # Checks if the channel is a thread or DM.
			if message.channel.id not in config["AllowedChannels"]: # Checks if the channel is allowed.
				logging.info("Message not in an allowed channel. Ignoring message.")
				return
		if message.author.id in config["bot_user"]: # Checks if the message author is the bot.
			logging.info(f"Message author is ignored. Ignoring message.")
			return

		if message.author.id in ignored_users and not config["bot_user"]: # Checks if the message author is an ignored user.
			logging.info("Message is from an ignored user. Ignoring message.")
			await message.channel.send("I'm sorry, I cannot talk to you.")
			return

		if any(word.lower() in message.content.lower() for word in ignored_words): # Checks if the message contains ignored words.
			logging.info("Message contains ignored words. Ignoring message.")
			return

		logging.info(f"Received message: {message.content}")
		import re

		stripped_message = message.content.strip()

		bot_name = config["Name"]

		# Check for bot's name in the message, or a mention, or active user
		is_triggered = bot_name.lower() in stripped_message.lower() or bot.user in message.mentions or message.author.id in active_users
		if is_triggered or message.channel.type == discord.ChannelType.private:
			#Robust command detection: prioritize '!', handle whitespace variations, case-insensitive
			is_command = stripped_message.startswith("!") or re.search(r"\s*!\s*\S+", stripped_message, re.IGNORECASE)

			if is_command:
				await handle_command(message, config, user_message_histories, bot, history_file_name)
				logging.info("Message is a command. Ignoring for OpenClaw processing.")
				return #This return statement is crucial; it prevents further processing
				
		#If the message is a dm, has AllowDMResponse enabled, let it action regardless of OnlyWhenCalled
		if message.channel.type == discord.ChannelType.private and (config["AllowDMResponses"] or message.author.id in config["AllowedDMUsers"]):
			logging.info(f"Responding to DM in private channel and AllowDMResponses is enabled")
			async with message.channel.typing():
				message_queue.put_nowait(Task(config, message, user_message_histories, history_file_name, bot))
				return #End Message Cycle

		# Checks if the message is a DM.
		if message.channel.type == discord.ChannelType.private and not config["AllowDMResponses"]: # Checks if the bot is allowed to respond to DMs.
			await message.channel.send("I Cannot talk here. Please try a regular Channel.")
			logging.info("Message is from a DM.")
			return

		bot_name = config["Name"]

		# Check for active user and if within interaction timeout period, BEFORE OnlyWhenCalled
		if message.author.id in active_users and (time.time() - active_users[message.author.id]) <= interaction_timeout:
			logging.info(f"Continuing interaction with active user {message.author.name}.")
			async with message.channel.typing():
				# Update last interaction time
				active_users[message.author.id] = time.time()
				# Schedule removal after timeout
				asyncio.create_task(remove_user_from_active(message.author.id, interaction_timeout))
				message_queue.put_nowait(Task(config, message, user_message_histories, history_file_name, bot))
			return #End this cycle

		# Modified to use mentions or replies
		#If we don't have respond to replies set to true, then this will end the message cycle.
		if respond_to_mentions and (bot.user in message.mentions or (message.reference and message.reference.message_id)):
			#Check is the message a reply and is it a reply to the bot
			if message.reference and message.reference.message_id:
				try:
					referenced_message = await message.channel.fetch_message(message.reference.message_id)
					if referenced_message.author.id != bot.user.id:
						logging.info(f"Ignoring reply to another user in {message.channel}.")
						return #End if it is not a reply to the bot
				except discord.NotFound:
					logging.warning("Referenced message not found, cannot determine if reply to bot.")

				
				# Add user to active_users and record last interaction time
				active_users[message.author.id] = time.time()
				# Schedule removal after timeout
				asyncio.create_task(remove_user_from_active(message.author.id, interaction_timeout))
				# Send to the message queue
				message_queue.put_nowait(Task(config, message, user_message_histories, history_file_name, bot)) #Adds the task to the queue
				return  #End this message cycle after adding
			#If it is a reply or a mention lets process this.
			logging.info(f"📩 Received message from {message.author.name}: {message.content}")

			async with message.channel.typing(): #Shows the bot is typing.
				msg_content = message.content #Sets the messages content

				# If it's a reply, fetch the original message
				if message.reference and message.reference.message_id: #Checks the message ID
					try:
						original_message = await message.channel.fetch_message(message.reference.message_id) #Gets the message.
						msg_content = f"[Replying to previous message: \"{original_message.content}\"] {msg_content}" #Appends the two messages
					except discord.NotFound:
						logging.warning("Referenced message not found, cannot include in reply context.")
				# Add user to active_users and record last interaction time
				active_users[message.author.id] = time.time()
				# Schedule removal after timeout
				asyncio.create_task(remove_user_from_active(message.author.id, interaction_timeout))
				# Send to the message queue
				message_queue.put_nowait(Task(config, message, user_message_histories, history_file_name, bot)) #Adds the task to the queue
			return  #End This block
		if any(cmd in message.content.lower() for cmd in ["!join_vc", "!leave_vc", "!play", "!skip", "!stop", "!volume", "!now_playing", "!queue"]):
				async with message.channel.typing():
					active_users[message.author.id] = time.time()
					# Schedule removal after timeout
					asyncio.create_task(remove_user_from_active(message.author.id, interaction_timeout))
					await handle_command(message, config, user_message_histories, bot, history_file_name) #Processes the command
				return

		# Only enforce OnlyWhenCalled if the user is NOT in active_users.
		if config.get("OnlyWhenCalled") and bot_name.lower() not in message.content.lower():
			logging.info("Message does not contain bot name and user is not active. Ignoring message.")
			#Check if the message contains the bot name and a command. If so, process it.
			return

		logging.debug(f"Received message: {message.content}") #Logs the message context

		if message.guild:
			#If the message is in a guild
			voice_client = message.guild.voice_client #Checks to see if the message is in a guild
			if voice_client and voice_client.is_connected() and message.author.voice: #Checks if the voice client exists and is connected and if the author is in the channel
				if message.author.voice.channel == voice_client.channel: #If the author is in the voice channel
					async with message.channel.typing():
						await VoiceRecvClient.process_recognized_speech(message.content, message) #Processes the speech
				else:
					await message.channel.send("You must be in the same voice channel as me to use this feature.") #If not in the channel, will reply with this
			else:
				if message.channel.type == discord.ChannelType.private: #If in a private channel, will continue the checks
					message_queue.put_nowait(Task(config, message, user_message_histories, history_file_name, bot)) #If the previous checks pass, will add the task to the queue
				else:
					message_queue.put_nowait(Task(config, message, user_message_histories, history_file_name, bot)) #If the previous checks pass, will add the task to the queue
		else:
			# Add user to active_users and record last interaction time
			active_users[message.author.id] = time.time()
			# Schedule removal after timeout
			asyncio.create_task(remove_user_from_active(message.author.id, interaction_timeout))
			message_queue.put_nowait(Task(config, message, user_message_histories, history_file_name, bot)) #If the message isn't a guild, will add the task to the queue

	except Exception as e:
		logging.error("An error occurred during bot startup: " + str(e))

async def remove_user_from_active(user_id, delay):
	#Removes the user from the active users list
	await asyncio.sleep(delay) #Sleeps to await the action
	if user_id in active_users: #If the user id is in the list
		del active_users[user_id] #Will remove the user from the list
		logging.info(f"User {user_id} removed from active users list.")


if __name__ == "__main__":
	# Runs the bot
	try:
		asyncio.run(start_bot())  # Awaits the start bots function to run
	except KeyboardInterrupt:  # If there is an interrupt, will log that and exit
		if observer:
			observer.stop()
			observer.join()
		logging.info("Exiting...")