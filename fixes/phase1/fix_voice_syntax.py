#!/usr/bin/env python3
"""
Fix script for voice_recv_class.py syntax errors.
Run this to automatically fix the critical syntax issues.
"""

import shutil
from pathlib import Path

FIXED_CONTENT = '''import logging
import asyncio
import torch
import torchaudio
import nltk
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)
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
import os
import concurrent.futures


class VoiceRecvClient(voice_recv.VoiceRecvClient):
    """Voice client with TTS/STT capabilities."""
    
    language = 'en'
    model_id = 'v3_en'
    device = torch.device("cpu")
    tts_queue = asyncio.Queue()
    silero_model = None
    
    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        self.loop = asyncio.get_event_loop()
        self._load_silero_model()
        
    def _load_silero_model(self):
        """Lazy-load Silero model."""
        try:
            VoiceRecvClient.silero_model, _ = torch.hub.load(
                repo_or_dir='snakers4/silero-models',
                model='silero_tts',
                language=self.language,
                speaker=self.model_id,
                trust_repo=True
            )
            VoiceRecvClient.silero_model.to(self.device)
        except Exception as e:
            logging.error(f"Error loading Silero model: {e}")
            VoiceRecvClient.silero_model = None
        
    def handle_audio_processing(self, ctx):
        def on_speech_recognized(user, text):
            bot_name = self.config.get("Name", "Jennifer").lower()
            logging.info(f"Speech recognized : {text}")
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

    @classmethod
    async def process_recognized_speech(cls, text: str, message):
        try:
            # Import here to avoid circular dependency
            from utils.utility_functions import generate_response
            
            config = message.channel.guild.voice_client.config if hasattr(
                message.channel.guild.voice_client, 'config'
            ) else {}
            
            response_chunks = await generate_response(
                config, message.author.id, message.author.display_name, {}, 
                message=None, prompt=text
            )
            
            if not response_chunks:
                logging.error("No response text generated.")
                return
                
            concatenated_response = ''
            for chunk in response_chunks:
                await cls.text_to_speech(chunk)
                audio_bytes_list = await cls.tts_queue.get()
                if audio_bytes_list:
                    member = message.author
                    if member.voice:
                        voice_client = member.voice.channel.guild.voice_client
                        if voice_client:
                            for audio_bytes in audio_bytes_list:
                                audio_source = discord.FFmpegPCMAudio(
                                    io.BytesIO(audio_bytes), pipe=True
                                )
                                playback_finished = asyncio.Future()

                                def set_playback_finished(error):
                                    if error:
                                        print(f"Playback error: {error}")
                                    playback_finished.set_result(None)

                                voice_client.play(audio_source, after=set_playback_finished)
                                await playback_finished

                            concatenated_response += chunk
                            
            if concatenated_response:
                max_length = 1900
                chunks = []
                lines = concatenated_response.split('\\n')
                for line in lines:
                    wrapped_lines = textwrap.wrap(
                        line, width=max_length, break_long_words=False
                    )
                    for wrapped_line in wrapped_lines:
                        chunks.append(wrapped_line.strip())
                
                for chunk in chunks:
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
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                audio_bytes_list = await loop.run_in_executor(
                    pool,
                    cls._text_to_speech_blocking,
                    text
                )

            cls.tts_queue.put_nowait(audio_bytes_list)
            logging.info("TTS Conversion Completed")
        except ValueError as ve:
            logging.error(f"ValueError in text_to_speech: {ve}")
        except Exception as e:
            logging.error(f"Error in text_to_speech: {e}")
            raise
        return None
    
    @classmethod
    def _text_to_speech_blocking(cls, text):
        try:
            sample_rate = 48000
            
            if cls.silero_model is None:
                raise ValueError("Silero model not loaded")
            
            speaker = "en_107"
            put_accent = True
            put_yo = True

            chunks = textwrap.wrap(text, width=950, break_long_words=False)
            
            audio_bytes_list = []
            for chunk in chunks:
                audio = cls.silero_model.apply_tts(
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
                audio_bytes = audio_bytes_io.getvalue()

                audio_bytes_list.append(audio_bytes)
            
            return audio_bytes_list
            
        except ValueError as ve:
            logging.error(f"ValueError in text_to_speech: {ve}")
            raise
        except Exception as e:
            logging.error(f"Error in text_to_speech: {e}")
            raise
'''


def fix_voice_syntax():
    """Apply the voice syntax fix."""
    target = Path("utils/voice_recv_class.py")
    backup = Path("utils/voice_recv_class.py.bak")
    
    if not target.exists():
        print(f"ERROR: {target} not found!")
        return False
    
    # Create backup
    shutil.copy2(target, backup)
    print(f"Created backup: {backup}")
    
    # Write fixed content
    with open(target, 'w') as f:
        f.write(FIXED_CONTENT)
    
    print(f"Fixed {target}")
    
    # Verify syntax
    try:
        import py_compile
        py_compile.compile(str(target), doraise=True)
        print("✅ Syntax check passed!")
        return True
    except py_compile.PyCompileError as e:
        print(f"❌ Syntax error: {e}")
        # Restore backup
        shutil.copy2(backup, target)
        print("Restored backup")
        return False


if __name__ == "__main__":
    fix_voice_syntax()
