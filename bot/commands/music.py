"""
Music player functionality extracted from monolithic app.py.
Handles voice channel music playback with queue management.
"""

import asyncio
import logging
from typing import Optional

import discord
import yt_dlp as youtube_dl

logger = logging.getLogger(__name__)

# Suppress yt-dlp bug reports
youtube_dl.utils.bug_report_message = lambda: ""

YTDL_FORMAT_OPTIONS = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}

FFMPEG_OPTIONS = {
    "options": "-vn",  # Disable video
}

ytdl = youtube_dl.YoutubeDL(YTDL_FORMAT_OPTIONS)


class MusicPlayer:
    """Manages music playback for a guild."""
    
    def __init__(self, channel: discord.TextChannel, bot: discord.Client):
        self.bot = bot
        self.channel = channel
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.now_playing: Optional[str] = None
        self.loop = False
        self.volume = 0.5
        self.voice_client: Optional[discord.VoiceClient] = None
    
    async def safe_disconnect(self):
        """Safely disconnect from voice channel."""
        try:
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect()
                self.voice_client = None
                logger.info("Disconnected from voice channel")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
    
    async def join(self, channel: discord.VoiceChannel):
        """Join a voice channel."""
        try:
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.move_to(channel)
                logger.info(f"Moved to voice channel: {channel.name}")
            else:
                self.voice_client = await channel.connect()
                logger.info(f"Joined voice channel: {channel.name}")
        except Exception as e:
            logger.error(f"Error joining voice channel: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from voice channel."""
        await self.safe_disconnect()
    
    def is_playing(self) -> bool:
        """Check if anything is playing."""
        return (
            self.voice_client is not None 
            and self.voice_client.is_playing()
        )
    
    async def enqueue(self, url: str):
        """Add a song to the queue."""
        await self.queue.put(url)
        logger.info(f"Enqueued: {url}")
    
    async def play_next(self):
        """Play the next song in the queue."""
        if self.voice_client is None:
            logger.warning("Voice client not initialized, cannot play")
            return
        
        if self.queue.empty():
            self.now_playing = None
            await self.channel.send("Queue is empty. Leaving voice channel.")
            await self.safe_disconnect()
            return
        
        url = await self.queue.get()
        
        try:
            # Extract info in executor to avoid blocking
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, 
                lambda: ytdl.extract_info(url, download=False)
            )
        except Exception as e:
            logger.error(f"Error extracting video info: {e}")
            await self.channel.send(f"Error processing song: {e}")
            return
        
        # Handle playlists
        if "entries" in data:
            if data["entries"]:
                data = data["entries"][0]
            else:
                await self.channel.send("Playlist is empty.")
                return
        
        filename = data["url"]
        self.now_playing = data.get("title", "Unknown")
        
        # Create audio source with volume control
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS),
            volume=self.volume,
        )
        
        def after_playing(error):
            if error:
                logger.error(f"Playback error: {error}")
            # Schedule next song
            asyncio.run_coroutine_threadsafe(
                self.play_next(), 
                self.bot.loop
            )
        
        self.voice_client.play(source, after=after_playing)
        
        # Use run_coroutine_threadsafe since we're in a callback context
        asyncio.run_coroutine_threadsafe(
            self.channel.send(f"🎵 Now playing: **{self.now_playing}**"),
            self.bot.loop
        )
        
        logger.info(f"Started playing: {self.now_playing}")
    
    async def set_volume(self, volume: float):
        """Set playback volume (0.0 to 1.0)."""
        self.volume = max(0.0, min(1.0, volume))
        
        if self.voice_client and self.voice_client.source:
            self.voice_client.source.volume = self.volume
        
        logger.info(f"Volume set to {self.volume:.2f}")
    
    async def stop(self):
        """Stop playback and clear queue."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            self.now_playing = None
            
            # Clear queue
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            
            await self.channel.send("⏹️ Playback stopped and queue cleared.")
            logger.info("Playback stopped")
    
    async def skip(self):
        """Skip current song."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()  # This triggers after callback
            await self.channel.send("⏭️ Song skipped.")
            logger.info("Song skipped")
        else:
            await self.channel.send("Nothing is playing to skip.")
    
    async def pause(self):
        """Pause playback."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            await self.channel.send("⏸️ Paused.")
    
    async def resume(self):
        """Resume playback."""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            await self.channel.send("▶️ Resumed.")
    
    def get_queue_list(self) -> list[str]:
        """Get list of queued URLs (for display)."""
        return list(self.queue._queue)


# Guild music player registry
music_players: dict[int, MusicPlayer] = {}


def get_player(guild_id: int, channel: discord.TextChannel, bot: discord.Client) -> MusicPlayer:
    """Get or create music player for guild."""
    if guild_id not in music_players:
        music_players[guild_id] = MusicPlayer(channel, bot)
    return music_players[guild_id]


def remove_player(guild_id: int):
    """Remove music player for guild."""
    if guild_id in music_players:
        del music_players[guild_id]


async def cleanup_empty_voice_channels(bot: discord.Client):
    """Background task to disconnect from empty voice channels."""
    while True:
        await asyncio.sleep(30)  # Check every 30 seconds
        
        for guild_id, player in list(music_players.items()):
            if (
                player.voice_client 
                and player.voice_client.is_connected()
                and len(player.voice_client.channel.members) == 1
                and bot.user in player.voice_client.channel.members
            ):
                logger.info(f"Auto-disconnecting from empty channel in guild {guild_id}")
                await player.safe_disconnect()
                remove_player(guild_id)
