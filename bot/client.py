"""
Discord bot client setup and event handlers.
Refactored from monolithic app.py
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any

import discord
from discord.ext import tasks

from core.config import JenniferConfig, watch_config
from core.logging_config import setup_logging
from core.persistent_queue import PersistentQueue, Task, TaskManager
from core.tracing import get_tracer, SpanStatus
from bot.commands.handlers import (
    handle_command,
    handle_messages as process_message,
    active_users,
    image_queue as global_image_queue,
    video_queue as global_video_queue,
    message_queue as global_message_queue,
)
from bot.commands.music import cleanup_empty_voice_channels

logger = logging.getLogger(__name__)
tracer = get_tracer()


class JenniferBot(discord.AutoShardedClient):
    """Jennifer Discord Bot - Refactored version."""
    
    def __init__(self, config: JenniferConfig, config_path: str = "config/config.json", **kwargs):
        # Enable all intents
        intents = discord.Intents.all()

        super().__init__(
            intents=intents,
            **kwargs
        )

        self.config = config
        self._config_path = config_path
        self.user_message_histories: Dict[str, Any] = {}
        self.history_file_name = config.get_history_file_name()

        # Task queues
        self.task_manager = TaskManager(data_dir="/app/data")
        self.image_queue: PersistentQueue = self.task_manager.get_queue("image")
        self.video_queue: PersistentQueue = self.task_manager.get_queue("video")
        self.message_queue: PersistentQueue = self.task_manager.get_queue("message")

        # Set global references for command handlers
        global global_image_queue, global_video_queue, global_message_queue
        import bot.commands.handlers as handlers
        handlers.image_queue = self.image_queue
        handlers.video_queue = self.video_queue
        handlers.message_queue = self.message_queue

        # Background tasks
        self._cleanup_task = None
        self._config_watcher_task = None
        self._queue_workers = []
    
    async def setup_hook(self):
        """Called when bot is starting up."""
        # Initialize databases
        await self.task_manager.initialize_all()
        
        # Load message histories
        self._load_message_histories()
        
        # Create health check file
        try:
            Path('/app/healthy').touch()
            logger.info("Health check file created")
        except Exception as e:
            logger.warning(f"Could not create health check file: {e}")
        
        # Start background tasks
        self._cleanup_task = self.loop.create_task(cleanup_empty_voice_channels(self))
        self._queue_workers.append(self.loop.create_task(self._image_worker()))
        self._queue_workers.append(self.loop.create_task(self._video_worker()))
        self._queue_workers.append(self.loop.create_task(self._message_worker()))

        # Start live config watcher
        self._config_watcher_task = self.loop.create_task(
            watch_config(self._config_path, self._on_config_reload)
        )

        # Start periodic cleanup
        self._cleanup_old_data.start()

        logger.info("Bot setup complete")

    def _on_config_reload(self, new_config: JenniferConfig) -> None:
        """Called by watch_config() whenever config.json changes.

        Hot-reloadable fields: everything except discord_token (requires
        reconnect) and queue worker settings (require restart).
        """
        old_log_level = self.config.log_level
        self.config = new_config

        # Re-apply log level if it changed
        if new_config.log_level != old_log_level:
            setup_logging(
                log_level=new_config.log_level,
                log_dir="/app/logs",
                use_json=True,
                app_name=new_config.name,
            )
            logger.info(f"Log level changed to {new_config.log_level}")

        logger.info(
            f"Config reloaded live — name={new_config.name}, "
            f"log_level={new_config.log_level}, "
            f"only_when_called={new_config.only_when_called}"
        )
    
    def _load_message_histories(self):
        """Load user message histories from file."""
        try:
            if os.path.exists(self.history_file_name):
                with open(self.history_file_name, 'r', encoding='utf-8') as f:
                    self.user_message_histories = json.load(f)
                    if self.user_message_histories is None:
                        self.user_message_histories = {}
                logger.info(f"Loaded message histories for {len(self.user_message_histories)} users")
            else:
                logger.info("No existing history file, starting fresh")
                self.user_message_histories = {}
                self._save_message_histories()
        except Exception as e:
            logger.error(f"Error loading message histories: {e}")
            self.user_message_histories = {}
    
    def _save_message_histories(self):
        """Save user message histories to file."""
        try:
            with open(self.history_file_name, 'w', encoding='utf-8') as f:
                json.dump(self.user_message_histories, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving message histories: {e}")
    
    async def _image_worker(self):
        """Worker for processing image generation tasks with tracing."""
        logger.info("Image worker started")
        
        while not self.is_closed():
            try:
                task = await self.image_queue.get()
                task_trace = tracer.start_trace(
                    "image_generation_task",
                    attributes={
                        "task_id": task.id,
                        "user_id": task.user_id,
                        "queue_time": task.created_at,
                    }
                )
                
                logger.info(f"Processing image task {task.id} for user {task.user_id}")
                tracer.add_event("task_dequeued", {"wait_time_ms": (time.time() - task.created_at) * 1000})
                
                try:
                    await self._process_image_task(task)
                    await self.image_queue.mark_done(task)
                    tracer.add_event("task_completed")
                    tracer.end_trace(task_trace)
                    
                except Exception as e:
                    logger.exception(f"Error processing image task: {e}")
                    tracer.add_event("task_failed", {"error": str(e)})
                    tracer.end_trace(task_trace)
                    await self.image_queue.mark_failed(task, str(e))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Unexpected error in image worker: {e}")
                await asyncio.sleep(1)
        
        logger.info("Image worker stopped")
    
    async def _process_image_task(self, task: Task):
        """Process a single image generation task with tracing."""
        payload = task.payload
        proc_span = tracer.start_span("process_image_task", "image_gen")
        
        try:
            # Get channel and message
            channel = self.get_channel(payload["channel_id"])
            if not channel:
                logger.error(f"Channel {payload['channel_id']} not found")
                tracer.add_event("channel_not_found")
                tracer.end_span(proc_span, SpanStatus.ERROR, "Channel not found")
                return
            
            tracer.add_attribute("channel_id", payload["channel_id"])
            
            try:
                draw_msg = await channel.fetch_message(payload["message_id"])
            except discord.NotFound:
                logger.error(f"Message {payload['message_id']} not found")
                tracer.add_event("message_not_found")
                tracer.end_span(proc_span, SpanStatus.ERROR, "Message not found")
                return
            
            # Get the original message that triggered the draw command
            try:
                original_message = await channel.fetch_message(payload.get("original_message_id", payload["message_id"]))
            except discord.NotFound:
                original_message = draw_msg
            
            tracer.add_event("messages_loaded")
            
            # Process with typing indicator
            async with channel.typing():
                gen_span = tracer.start_span("generate_image", "image_gen", parent_id=proc_span)
                
                # Import and call image generation
                from utils.image_gen import handle_image_generation
                await handle_image_generation(
                    self.config,
                    original_message,
                    self.user_message_histories,
                    self,
                    draw_msg,
                )
                
                tracer.end_span(gen_span)
                tracer.end_span(proc_span)
                
        except Exception as e:
            tracer.end_span(proc_span, SpanStatus.ERROR, str(e))
            raise
    
    async def _video_worker(self):
        """Worker for processing video generation tasks."""
        logger.info("Video worker started")
        
        while not self.is_closed():
            try:
                task = await self.video_queue.get()
                logger.info(f"Processing video task {task.id} for user {task.user_id}")
                
                try:
                    await self._process_video_task(task)
                    await self.video_queue.mark_done(task)
                except Exception as e:
                    logger.exception(f"Error processing video task: {e}")
                    await self.video_queue.mark_failed(task, str(e))
                    
                    # Notify user of failure
                    await self._notify_video_failure(task, str(e))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Unexpected error in video worker: {e}")
                await asyncio.sleep(1)
        
        logger.info("Video worker stopped")
    
    async def _process_video_task(self, task: Task):
        """Process a single video generation task."""
        payload = task.payload
        
        # Get channel and message
        channel = self.get_channel(payload["channel_id"])
        if not channel:
            logger.error(f"Channel {payload['channel_id']} not found")
            return
        
        try:
            vid_msg = await channel.fetch_message(payload["message_id"])
        except discord.NotFound:
            logger.error(f"Message {payload['message_id']} not found")
            return
        
        # Update status
        await vid_msg.edit(content=f"{vid_msg.content}\n\n⏳ Generating video... This may take a few minutes.")
        
        # Generate video
        from utils.video_gen import VideoGenerator
        
        generator = VideoGenerator(self.config.video)
        
        try:
            video_path = await generator.generate(
                prompt=payload["prompt"],
                output_dir="/app/data/videos",
                user_id=task.user_id,
                image_path=payload.get("image_path"),
            )
            
            # Send the video
            await channel.send(
                f"🎬 Here's your video, {payload['user_name']}:",
                file=discord.File(video_path)
            )
            
            # Delete the status message
            await vid_msg.delete()
            
        except Exception as e:
            logger.exception(f"Video generation failed: {e}")
            await vid_msg.edit(content=f"{vid_msg.content}\n\n❌ Video generation failed: {str(e)[:200]}")
    
    async def _notify_video_failure(self, task: Task, error: str):
        """Notify user that video generation failed."""
        try:
            payload = task.payload
            channel = self.get_channel(payload["channel_id"])
            if channel:
                await channel.send(
                    f"❌ Sorry {payload['user_name']}, video generation failed: {error[:100]}"
                )
        except Exception as e:
            logger.error(f"Failed to send failure notification: {e}")
    
    async def _message_worker(self):
        """Worker for processing chat message tasks."""
        logger.info("Message worker started")
        
        while not self.is_closed():
            try:
                task = await self.message_queue.get()
                logger.debug(f"Processing message task {task.id} for user {task.user_id}")
                
                try:
                    from utils.interactions import handle_message_processing
                    
                    # Reconstruct message context
                    await self._process_message_task(task)
                    await self.message_queue.mark_done(task)
                    
                except Exception as e:
                    logger.exception(f"Error processing message task: {e}")
                    await self.message_queue.mark_failed(task, str(e))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Unexpected error in message worker: {e}")
                await asyncio.sleep(1)
        
        logger.info("Message worker stopped")
    
    async def _process_message_task(self, task: Task):
        """Process a single chat message task."""
        from utils.interactions import handle_message_processing
        
        payload = task.payload
        channel = self.get_channel(payload["channel_id"])
        if not channel:
            return
        
        try:
            message = await channel.fetch_message(payload["message_id"])
        except discord.NotFound:
            return
        
        await handle_message_processing(
            self.config,
            message,
            self.user_message_histories,
            self.history_file_name,
        )
    
    @tasks.loop(hours=1)
    async def _cleanup_old_data(self):
        """Periodic cleanup of old data."""
        try:
            # Clean old completed tasks
            for queue in [self.image_queue, self.video_queue, self.message_queue]:
                await queue.cleanup_old_tasks(max_age_hours=24)
            
            # Clean old video files (keep for 7 days)
            try:
                video_dir = Path("/app/data/videos")
                if video_dir.exists():
                    import time
                    now = time.time()
                    for file in video_dir.glob("*.mp4"):
                        if now - file.stat().st_mtime > 7 * 24 * 3600:
                            file.unlink()
                            logger.debug(f"Cleaned old video: {file}")
            except Exception as e:
                logger.warning(f"Error cleaning video files: {e}")
            
            logger.info("Periodic cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    @_cleanup_old_data.before_loop
    async def _before_cleanup(self):
        await self.wait_until_ready()
    
    # =======================================================================
    # Discord Event Handlers
    # =======================================================================
    
    async def on_ready(self):
        """Called when bot is fully connected."""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guilds")
        logger.info(f"Queue stats: {await self.task_manager.get_all_stats()}")
    
    async def on_message(self, message: discord.Message):
        """Handle incoming messages with tracing."""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Start trace for this message
        trace_id = tracer.start_trace(
            "discord_message",
            attributes={
                "user_id": message.author.id,
                "user_name": message.author.display_name,
                "channel_id": message.channel.id,
                "message_id": message.id,
                "content_preview": message.content[:100],
                "is_dm": isinstance(message.channel, discord.DMChannel),
            }
        )
        
        try:
            tracer.add_event("message_received")
            await self._process_incoming_message(message)
            tracer.end_trace(trace_id)
        except Exception as e:
            tracer.add_event("message_error", {"error": str(e)})
            tracer.end_trace(trace_id)
            logger.exception(f"Error processing message: {e}")
    
    async def _process_incoming_message(self, message: discord.Message):
        """Process a single incoming message with detailed tracing."""
        span_id = tracer.start_span("process_message", "discord")
        
        try:
            # Check ignored users
            if self.config.is_ignored_user(message.author.id):
                tracer.add_event("ignored_user")
                logger.info(f"Ignoring message from ignored user {message.author.id}")
                tracer.end_span(span_id)
                return
            
            # Check ignored words
            if any(word.lower() in message.content.lower() for word in self.config.ignored_words):
                tracer.add_event("ignored_words")
                logger.info("Message contains ignored words, skipping")
                tracer.end_span(span_id)
                return
            
            # Check allowed channels
            if (
                not isinstance(message.channel, (discord.DMChannel, discord.Thread))
                and not self.config.is_allowed_channel(message.channel.id)
            ):
                tracer.add_event("non_allowed_channel", {"channel_id": message.channel.id})
                logger.debug(f"Message in non-allowed channel {message.channel.id}")
                tracer.end_span(span_id)
                return
            
            tracer.add_event("filters_passed")
            logger.debug(f"Processing message from {message.author}: {message.content[:50]}...")
            
            # Extract command if present
            from bot.commands.handlers import extract_prefixed_command
            parsed_command = extract_prefixed_command(
                message.content.strip(),
                self.config.name,
                self.user.id
            )
            
            # Handle commands
            if parsed_command:
                tracer.add_event("command_detected", {"command": parsed_command})
                cmd_span = tracer.start_span("handle_command", "discord", parent_id=span_id)
                
                handled = await handle_command(
                    message=message,
                    config=self.config,
                    user_message_histories=self.user_message_histories,
                    bot=self,
                    history_file_name=self.history_file_name,
                    parsed_command=parsed_command,
                )
                
                tracer.end_span(cmd_span, SpanStatus.SUCCESS if handled else SpanStatus.ERROR)
                if handled:
                    tracer.end_span(span_id)
                    return
            
            # Handle natural language
            tracer.add_event("handling_conversation")
            conv_span = tracer.start_span("handle_conversation", "discord", parent_id=span_id)
            await self._handle_conversation(message)
            tracer.end_span(conv_span)
            tracer.end_span(span_id)
            
        except Exception as e:
            tracer.end_span(span_id, SpanStatus.ERROR, str(e))
            raise
    
    async def _handle_conversation(self, message: discord.Message):
        """Handle natural language conversation."""
        # DM handling
        if isinstance(message.channel, discord.DMChannel):
            if not self.config.allow_dm_responses and message.author.id not in self.config.allowed_dm_users:
                await message.channel.send("I can't respond to DMs. Please use a server channel.")
                return
            
            # Queue for processing
            await self._queue_message(message)
            return
        
        # Check for active conversation
        user_id = message.author.id
        current_time = time.time()
        
        if user_id in active_users:
            last_time = active_users[user_id]
            if current_time - last_time <= self.config.interaction_timeout:
                # Continue conversation
                active_users[user_id] = current_time
                await self._queue_message(message)
                return
        
        # Check for mentions or name
        bot_mentioned = self.user in message.mentions
        bot_named = self.config.name.lower() in message.content.lower()
        replying_to_bot = (
            message.reference 
            and message.reference.message_id
            and message.reference.resolved
            and message.reference.resolved.author.id == self.user.id
        )
        
        if bot_mentioned or bot_named or replying_to_bot:
            # Start new conversation
            active_users[user_id] = current_time
            await self._queue_message(message)
            return
        
        # Only respond if OnlyWhenCalled is False
        if not self.config.only_when_called:
            await self._queue_message(message)
    
    async def _queue_message(self, message: discord.Message):
        """Queue a message for processing."""
        task = Task(
            id=None,
            type="message",
            payload={
                "channel_id": message.channel.id,
                "message_id": message.id,
                "user_id": message.author.id,
                "user_name": message.author.display_name,
                "content": message.content,
            },
            user_id=message.author.id,
            created_at=time.time(),
        )
        
        await self.message_queue.put(task)
        
        # Show typing indicator
        async with message.channel.typing():
            pass  # Typing will continue until response is sent
    
    async def on_voice_state_update(
        self, 
        member: discord.Member, 
        before: discord.VoiceState, 
        after: discord.VoiceState
    ):
        """Handle voice state changes."""
        # Log joins/leaves
        if before.channel is None and after.channel is not None:
            logger.info(f"{member.name} joined voice channel {after.channel.name}")
        elif before.channel is not None and after.channel is None:
            logger.info(f"{member.name} left voice channel {before.channel.name}")
        
        # Auto-disconnect handled by cleanup task
    
    async def on_disconnect(self):
        """Called when bot disconnects."""
        logger.warning("Disconnected from Discord")
    
    async def on_resumed(self):
        """Called when bot resumes connection."""
        logger.info("Resumed connection to Discord")
    
    async def close(self):
        """Clean shutdown."""
        logger.info("Shutting down...")
        
        # Remove health check file
        try:
            if os.path.exists('/app/healthy'):
                os.remove('/app/healthy')
                logger.info("Health check file removed")
        except Exception as e:
            logger.warning(f"Could not remove health check file: {e}")
        
        # Cancel background tasks
        if self._cleanup_task:
            self._cleanup_task.cancel()

        if self._config_watcher_task:
            self._config_watcher_task.cancel()

        for worker in self._queue_workers:
            worker.cancel()
        
        # Save data
        self._save_message_histories()
        
        # Wait for workers to finish
        await asyncio.gather(*self._queue_workers, return_exceptions=True)
        
        await super().close()


async def start_bot(config: JenniferConfig, config_path: str = "config/config.json"):
    """Main entry point to start the bot."""
    # Setup logging
    setup_logging(
        log_level=config.log_level,
        log_dir="/app/logs",
        use_json=True,
        app_name=config.name,
    )

    logger.info(f"Starting {config.name} bot...")

    # Create and start bot
    bot = JenniferBot(config, config_path=config_path)

    try:
        await bot.start(config.discord_token)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        await bot.close()
