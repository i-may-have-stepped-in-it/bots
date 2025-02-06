import logging
import asyncio
import torch
import torchaudio
import nltk
nltk.download('punkt')
nltk.download('punkt_tab')
from nltk.tokenize import sent_tokenize
import discord
from discord.ext import voice_recv
import io
from openai import AsyncOpenAI
import textwrap
import re
from silero import *
from discord.ext.voice_recv.extras import *
import sys
sys.path.insert(0, './utils/')  # Add this path to system paths for Python to be able to find modules in it.
from utils import *
from utils.utility_functions import config, generate_response
import concurrent.futures

class VoiceRecvClient(voice_recv.VoiceRecvClient):
	# Initialize the TTS model as a class attribute
	from silero.tts_utils import apply_tts
	language = 'en'
	model_id = 'v3_en'
	device = torch.device ("cuda" if torch.cuda.is_available() else "cpu")
	try:
		silero_model, _ = torch.hub.load(repo_or_dir='snakers4/silero-models',
								model='silero_tts',
								language=language,
								speaker=model_id
								)
		silero_model.to(device)
	except Exception as e:
		print(f"Error loading Silero model: {e}")
		silero_model = None

	tts_queue = asyncio.Queue()
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		# Capture the current event loop at initialization for use in callbacks
		self.loop = asyncio.get_event_loop()
		
	def handle_audio_processing(self, ctx):
		def on_speech_recognized(user, text):
			bot_name = config["Name"].lower()
			logging.info(f"Speech recognized : {text}")
			if bot_name in text.lower():
				# Use the captured loop to ensure the correct event loop is used
				asyncio.run_coroutine_threadsafe(self.process_recognized_speech(text, ctx), self.loop)

		sink = SpeechRecognitionSink(default_recognizer=config["recognizer"], text_cb=on_speech_recognized)
		self.listen(sink)	

	@classmethod
	async def process_recognized_speech(cls, text:  str, message):
		try:
			global config
			user = None
			response_chunks = await generate_response(config, message.author.id, str(message.author.display_name), {}, message=None, prompt=text)
			if response_chunks:
				concatenated_response = ''
				for chunk in response_chunks:
					await cls.text_to_speech(chunk)
					audio_bytes_list = await cls.tts_queue.get()
					logging.info(f"Response audio: {type(audio_bytes_list)} ")
					if audio_bytes_list:
						member = message.author
						if member.voice:
							voice_client = member.voice.channel.guild.voice_client
							if voice_client:
								for audio_bytes in audio_bytes_list:
									audio_source = discord.FFmpegPCMAudio(io.BytesIO(audio_bytes), pipe=True)
									# Correct way to handle after callback:
									playback_finished = asyncio.Future()

									def set_playback_finished(error): # No self here!
										if error:
											print(f"Playback error: {error}")
										playback_finished.set_result(None)  # Resolve the future

									voice_client.play(audio_source, after=set_playback_finished)
									await playback_finished

									concatenated_response += chunk  # Concatenate the chunk to the response
									
									# Split concatenated response into chunks of at most 2000 characters, respecting sentence end and newlines
									max_length = 1900
									chunks = []
									lines = concatenated_response.split('\n')
									for line in lines:
										# Wrap the line into chunks of approximately 1900 characters
										wrapped_lines = textwrap.wrap(line, width=max_length, break_long_words=False)
										for wrapped_line in wrapped_lines:
											chunks.append(wrapped_line.strip())
									
									# Send the chunks as separate messages
									# for chunk in chunks:
										await message.channel.send(chunk)
										
					else:
						logging.error("No response text generated.")

		except Exception as e:
			await message.channel.send("Sorry, I'm having trouble processing your request.")
			logging.error(e)

	@classmethod
	async def text_to_speech(cls, text):
		if not text:
			logging.warning("Received empty or None text for TTS.")
			return None

		try:
			loop = asyncio.get_running_loop()  # Get the current event loop
			with concurrent.futures.ThreadPoolExecutor() as pool:
				audio_bytes_list = await loop.run_in_executor(
					pool,  # Use the thread pool
					cls._text_to_speech_blocking,  # Call the blocking function
					text, config.get('SileroSpeaker') # Pass arguments
				)

			cls.tts_queue.put_nowait(audio_bytes_list)
			logging.info("TTS Conversion Completed")
		except ValueError as ve:
			logging.error(f"ValueError in text_to_speech: {ve}")
		except Exception as e:
			logging.error(f"Error in text_to_speech: {e}")
			# Optionally, raise the exception to propagate it further
			raise
		return None
	
	@classmethod
	def _text_to_speech_blocking(cls, text, speaker):  # New blocking function
		# This function now runs in a separate thread		
		try:
			sample_rate = 48000
			speaker = config.get('SileroSpeaker')
			if not speaker:
				raise ValueError("SileroSpeaker configuration not found")

			put_accent = True
			put_yo = True

			chunks = textwrap.wrap(text, width=950, break_long_words=False)
			

			# Convert each chunk to speech
			audio_bytes_list = []
			for chunk in chunks:
				# logging.info(f"Chunks to be synthesized: {chunks}")

				audio = cls.silero_model.apply_tts(text=chunk, speaker=speaker, sample_rate=sample_rate,
													put_accent=put_accent, put_yo=put_yo)

				# Assuming audio is a list of tensors, handling single text input
				audio_tensor = audio.unsqueeze(0)

				# Convert the generated audio tensor to bytes
				audio_bytes_io = io.BytesIO()
				torchaudio.save(audio_bytes_io, src=audio_tensor, sample_rate=sample_rate, format="wav")
				audio_bytes = audio_bytes_io.getvalue()

				audio_bytes_list.append(audio_bytes)
			
			# Return the list of audio bytes
			return audio_bytes_list # return the generated audio
			logging.info("TTS Conversion Completed")
		except ValueError as ve:
			logging.error(f"ValueError in text_to_speech: {ve}")
		except Exception as e:
			logging.error(f"Error in text_to_speech: {e}")
			# Optionally, raise the exception to propagate it further
			raise
		return None