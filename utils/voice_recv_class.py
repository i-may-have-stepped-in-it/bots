"""
Voice recognition and TTS client for Jennifer.
"""

import asyncio
import concurrent.futures
import io
import logging
import textwrap

import discord
import nltk
import torch
import torchaudio
from discord.ext import voice_recv
from discord.ext.voice_recv.extras import *
from silero import *

# Download NLTK data quietly
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)

logger = logging.getLogger(__name__)


class VoiceRecvClient(voice_recv.VoiceRecvClient):
    """Voice client with TTS/STT capabilities."""

    def __init__(self, bot_config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = bot_config
        self.loop = asyncio.get_event_loop()
        self.tts_queue = asyncio.Queue()

        # Initialize Silero model
        self.language = 'en'
        self.model_id = 'v3_en'
        self.device = torch.device("cpu")
        self.silero_model = None
        self._load_silero_model()

    def _load_silero_model(self):
        """Lazy-load Silero model."""
        try:
            self.silero_model, _ = torch.hub.load(
                repo_or_dir='snakers4/silero-models',
                model='silero_tts',
                language=self.language,
                speaker=self.model_id,
                trust_repo=True
            )
            self.silero_model.to(self.device)
            logger.info("Silero TTS model loaded successfully")
        except Exception as e:
            logger.error(f"Error loading Silero model: {e}")
            self.silero_model = None

    def handle_audio_processing(self, ctx):
        """Handle audio processing with speech recognition."""
        def on_speech_recognized(user, text):
            bot_name = self.config.get("Name", "Jennifer").lower()
            logger.info(f"Speech recognized: {text}")
            if bot_name in text.lower():
                asyncio.run_coroutine_threadsafe(
                    self.process_recognized_speech(text, ctx),
                    self.loop
                )

        recognizer = self.config.get("recognizer", "whisper")
        sink = SpeechRecognitionSink(
            default_recognizer=recognizer,
            text_cb=on_speech_recognized
        )
        self.listen(sink)

    async def process_recognized_speech(self, text: str, message):
        """Process recognized speech and generate response."""
        # Import here to avoid circular dependency
        from utils.utility_functions import generate_response

        try:
            response_chunks = await generate_response(
                self.config,
                message.author.id,
                message.author.display_name,
                {},
                message=None,
                prompt=text
            )

            if not response_chunks:
                logger.warning("No response generated for speech input")
                return

            concatenated_response = ''
            for chunk in response_chunks:
                await self.text_to_speech(chunk)
                audio_bytes_list = await self.tts_queue.get()

                if audio_bytes_list:
                    member = message.author
                    if member.voice:
                        voice_client = member.voice.channel.guild.voice_client
                        if voice_client:
                            for audio_bytes in audio_bytes_list:
                                audio_source = discord.FFmpegPCMAudio(
                                    io.BytesIO(audio_bytes),
                                    pipe=True
                                )
                                playback_finished = asyncio.Future()

                                def set_playback_finished(error):
                                    if error:
                                        logger.error(f"Playback error: {error}")
                                    playback_finished.set_result(None)

                                voice_client.play(audio_source, after=set_playback_finished)
                                await playback_finished

                            concatenated_response += chunk

            if concatenated_response:
                await self._send_chunks(message.channel, concatenated_response)
            else:
                logger.warning("No audio was played")

        except Exception:
            logger.exception("Error processing speech")
            await message.channel.send("Sorry, I'm having trouble processing your request.")

    async def _send_chunks(self, channel, text: str):
        """Send text in Discord-sized chunks."""
        max_length = 1900
        lines = text.split('\n')
        chunks = []

        for line in lines:
            wrapped = textwrap.wrap(line, width=max_length, break_long_words=False)
            chunks.extend(wrapped)

        for chunk in chunks:
            await channel.send(chunk)

    async def text_to_speech(self, text: str):
        """Convert text to speech."""
        if not text:
            logger.warning("Received empty text for TTS")
            return

        try:
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                audio_bytes_list = await loop.run_in_executor(
                    pool,
                    self._text_to_speech_blocking,
                    text
                )

            if audio_bytes_list:
                self.tts_queue.put_nowait(audio_bytes_list)
                logger.info("TTS conversion completed")
        except Exception:
            logger.exception("TTS conversion failed")
            raise

    def _text_to_speech_blocking(self, text: str):
        """Blocking TTS conversion (runs in thread pool)."""
        if self.silero_model is None:
            raise RuntimeError("Silero model not loaded")

        sample_rate = 48000
        speaker = self.config.get('SileroSpeaker', 'en_107')

        if not speaker:
            raise ValueError("SileroSpeaker not configured")

        put_accent = True
        put_yo = True

        chunks = textwrap.wrap(text, width=950, break_long_words=False)
        audio_bytes_list = []

        for chunk in chunks:
            audio = self.silero_model.apply_tts(
                text=chunk,
                speaker=speaker,
                sample_rate=sample_rate,
                put_accent=put_accent,
                put_yo=put_yo
            )

            audio_tensor = audio.unsqueeze(0)
            audio_bytes_io = io.BytesIO()
            torchaudio.save(
                audio_bytes_io,
                src=audio_tensor,
                sample_rate=sample_rate,
                format="wav"
            )
            audio_bytes_list.append(audio_bytes_io.getvalue())

        logger.debug(f"Generated {len(audio_bytes_list)} audio chunks")
        return audio_bytes_list
