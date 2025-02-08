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
from utils.interactions import handle_message_processing
from watchdog.observers.polling import PollingObserver
from utils.config_gen import load_config, config_path, log_setup, handle_config_change, ConfigFileHandler



sys.path.insert(0, './utils/')
tracemalloc.start()

Task = namedtuple('Task','config, message, user_message_histories, bot, history_file_name')
Draw_Task = namedtuple('Draw_Task','config, message, user_message_histories, bot, draw_msg')

config = load_config(config_path)
if config is None:
	sys.exit(1)

observer = None

image_queue = asyncio.Queue()
message_queue = asyncio.Queue()

async def worker(image_queue):
	while True:
		config, message, user_message_histories, bot, draw_msg = await image_queue.get()
		try:
			await handle_image_generation(config, message, user_message_histories, bot, draw_msg)
		except Exception as e:
			logging.error("An error occurred in image generation queue: " + str(e))
		finally:
			image_queue.task_done()

async def worker2(message_queue):
	while True:
		config, message, user_message_histories, history_file_name, bot = await message_queue.get()
		try:
			await handle_message_processing(config, message, user_message_histories, history_file_name)
		except Exception as e:
			logging.error("An error occurred in message processing queue: " + str(e))
		finally:
			message_queue.task_done()


async def join_voice_channel(ctx, voice_channel_id: int):
	try:
		channel = ctx.guild.get_channel(voice_channel_id)
		vc = await channel.connect(cls=VoiceRecvClient)
		logging.info(f"Joined voice channel: {channel}")
		is_listening = vc.is_listening()
		logging.info(f"Initial listening state: {is_listening}")
		vc.handle_audio_processing(ctx)
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
	voice_client = guild.voice_client
	if voice_client and voice_client.is_connected():
		if len(voice_client.channel.members) == 1:
					await voice_client.disconnect()


async def start_bot():
	global observer
	try:
		log_setup(config)
		history_file_name = config["Name"] + "_message_histories.json"

		def load_message_histories(history_file_name):
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
		user_message_histories = load_message_histories(history_file_name)

		intents = discord.Intents.all()
		bot = discord.AutoShardedClient(intents=intents)
		
		asyncio.create_task(worker(image_queue))
		asyncio.create_task(worker2(message_queue))
		
		@bot.event
		async def on_ready():
			logging.info('Logged in as {0.user}'.format(bot))
			
		@bot.event
		async def on_message(message):
			try:
				if message.author.bot:
					return
				await handle_messages(config, message, user_message_histories, history_file_name, bot, message_queue,image_queue)
				
			except Exception as e:
				logging.error("An error occurred during message handling: %s", str(e))

		@bot.event
		async def on_voice_state_update(member, before, after):
			voice_client = member.guild.voice_client
			if voice_client and voice_client.is_connected():
				if before.channel is None and after.channel is not None:
					print(f"{member.name} joined the voice channel")
				elif before.channel is not None and after.channel is None:
					print(f"{member.name} left the voice channel")
					await check_and_leave_voice_channel(member.guild)


		observer = PollingObserver()
		handler = ConfigFileHandler(config_path, handle_config_change)
		observer.schedule(handler, os.path.dirname(config_path), recursive=False)
		observer.start()

		await bot.start(config["DiscordToken"])

	except Exception as e:
		logging.critical('Failed to start bot due to exception: %s', str(e))
		if observer:
			observer.stop()
			observer.join()
		raise

async def handle_messages(config, message, user_message_histories, history_file_name, bot,message_queue,image_queue):
	ignored_users = config.get("IgnoredUsers", [])
	ignored_words = config.get("IgnoredWords", [])

	try:
		if message.content.startswith('!'):
			logging.debug("Message starts with '!'. Ignoring message.")
			return
		
		logging.info(f"Received message from {message.author} in channel {message.channel}")
		logging.debug(f"message content: {message.content}")

		if not isinstance(message.channel, (discord.Thread, discord.DMChannel)):
			if message.channel.id not in config["AllowedChannels"]:
				logging.info("Message not in an allowed channel. Ignoring message.")
				return
		
		logging.info(f"Received message: {message.content}")

		if message.channel.type == discord.ChannelType.private:
			if message.author.id in config["AllowedDMUsers"]:
				pass
			elif not config["AllowDMResponses"]:
				await message.channel.send("I Cannot talk here. Please try a regular Channel.")
				logging.info("Message is from a DM.")
				return

		if message.author.id in config["bot_user"]:
			logging.info(f"Message author is ignored. Ignoring message.")
			return	

		if message.author.id in ignored_users and not config["bot_user"]:
			logging.info("Message is from an ignored user. Ignoring message.")
			await message.channel.send("I'm sorry, I cannot talk to you.")
			return
		
		if any(word.lower() in message.content.lower() for word in ignored_words):
			logging.info("Message contains ignored words. Ignoring message.")
			return
		
		bot_name = config["Name"]
		if not message.channel.type == discord.ChannelType.private:
			if config.get("OnlyWhenCalled") and bot_name.lower() not in message.content.lower():
				logging.info("Message does not contain bot name. Ignoring message.")
				return
		else:
			logging.info("Message contains bot name or bot is configured to respond without mention.")

		logging.debug(f"Received message: {message.content}")
		

		if "draw" in message.content.lower() or "send" in message.content.lower():
			draw_msg = await message.channel.send("Hang on while I get that for you...")
			image_queue.put_nowait(Draw_Task(config, message, user_message_histories, bot, draw_msg))
		elif "txt2vid" in message.content.lower():
			draw_msg = await message.channel.send("Hang on while I get that for you...")
			await txt2vid(config,draw_msg,bot_name)
		elif "check models" in message.content.lower():
			if message.channel.type == discord.ChannelType.private:
				await print_available_models(config,message)
			else: 
				await message.channel.send("I'm sorry, I cannot run that here.")
				return
		elif "teamviewer" in message.content.lower():
			if message.channel.type == discord.ChannelType.private:
				await print_available_models(config,message)
			else: 
				await message.channel.send("I'm sorry, I cannot run that here.")
				return
		elif "load model" in message.content.lower():
			if message.channel.type == discord.ChannelType.private:
				try:
					load_msg = await message.channel.send(f"Loading model {message.content[10:]}.")
					await load_model(config,message)
					await load_msg.edit(content=load_msg.content + "\n" + "Model loaded successfully.")
					return
				except:
					await load_msg.edit(content= "I am sorry there is a problem with my camera.")
			else:
				await message.channel.send("I'm sorry, I cannot run that here.")
		elif "join_vc" in message.content.lower() or "join-vc" in message.content.lower():
			if message.author.voice:
				try:
					await join_voice_channel(message, message.author.voice.channel.id)
				except Exception as e:
					logging.error(f"Error occurred while joining voice channel: {e}")
					return
				await message.add_reaction("👍")
				await message.channel.send("Joined voice channel")
			else:
				await message.channel.send('You need to be in a voice channel to use this command')
				return
		elif "leave_vc" in message.content.lower() or "leave-vc" in message.content.lower():
			if message.author.voice:
				voice_client = message.guild.voice_client
				if voice_client and voice_client.is_connected():
					await voice_client.disconnect()
					await message.add_reaction("👋")
					await message.channel.send("Left voice channel")
			else:			
				await message.channel.send('You need to be in a voice channel to use this command')
				return		
		elif message.guild:
			voice_client = message.guild.voice_client
			if voice_client and voice_client.is_connected() and message.author.voice:
				if message.author.voice.channel == voice_client.channel:
					async with message.channel.typing():
						await VoiceRecvClient.process_recognized_speech(message.content, message)
				else:
					await message.channel.send("You must be in the same voice channel as me to use this feature.")
			else:
				if message.channel.type == discord.ChannelType.private:
					message_queue.put_nowait(Task(config, message, user_message_histories, history_file_name, bot))
				else:
					message_queue.put_nowait(Task(config, message, user_message_histories, history_file_name, bot))
		else:
			message_queue.put_nowait(Task(config, message, user_message_histories, history_file_name, bot))

	except Exception as e:
		logging.error("An error occurred during bot startup: " + str(e))

if __name__ == "__main__":
	try:
		asyncio.run(start_bot())
	except KeyboardInterrupt:
		if observer:
			observer.stop()
			observer.join()
		logging.info("Exiting...")