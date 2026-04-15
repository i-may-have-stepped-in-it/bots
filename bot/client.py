"""
Discord bot client setup and event handlers.
Refactored for improved observability, architecture, and security.
"""

import asyncio
import contextlib
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

import discord
from discord.ext import tasks
from discord import app_commands

from core.config import JenniferConfig, watch_config
from core.logging_config import setup_logging
from core.persistent_queue import PersistentQueue, Task, TaskManager
from core.tracing import get_tracer, SpanStatus
from core.history import history_manager
from core.metrics import (
    MESSAGES_RECEIVED, COMMANDS_EXECUTED, ACTIVE_USERS, 
    QUEUE_DEPTH, start_metrics_server, MetricsContext
)
from core.health import monitor as health_monitor
from core.redis_client import redis_manager
from utils.sanitization import get_sanitizer

from bot.commands.handlers import (
    handle_command,
    handle_messages as process_message,
    image_queue as global_image_queue,
    video_queue as global_video_queue,
    message_queue as global_message_queue,
)
from bot.commands.music import cleanup_empty_voice_channels
from bot.commands.slash_commands import register_slash_commands

logger = logging.getLogger(__name__)
tracer = get_tracer()


class JenniferBot(discord.AutoShardedClient):
    """Jennifer Discord Bot - Production ready version."""
    
    def __init__(self, config: JenniferConfig, config_path: str = "config/config.json", **kwargs):
        # Enable all intents
        intents = discord.Intents.all()

        super().__init__(
            intents=intents,
            **kwargs
        )

        self.config = config
        self._config_path = config_path
        self.sanitizer = get_sanitizer(config)
        self.tree = app_commands.CommandTree(self)

        # Task queues
        self.task_manager = TaskManager(data_dir="data")
        self.image_queue: PersistentQueue = self.task_manager.get_queue("image")
        self.video_queue: PersistentQueue = self.task_manager.get_queue("video")
        self.message_queue: PersistentQueue = self.task_manager.get_queue("message")

        # Set global references for command handlers (Legacy compatibility)
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
        await history_manager.initialize(bot_name=self.config.name)

        
        # Start health and metrics servers
        health_monitor.bot = self
        await health_monitor.start()
        start_metrics_server(9090)
        
        # Start background tasks
        self._cleanup_task = self.loop.create_task(cleanup_empty_voice_channels(self))
        self._queue_workers.append(self.loop.create_task(self._image_worker()))
        self._queue_workers.append(self.loop.create_task(self._video_worker()))
        self._queue_workers.append(self.loop.create_task(self._message_worker()))

        # Start live config watcher
        self._config_watcher_task = self.loop.create_task(
            watch_config(self._config_path, self._on_config_reload)
        )

        # Start periodic cleanup & metrics update
        if not self._periodic_updates.is_running():
            self._periodic_updates.start()

        # Register and sync slash commands
        register_slash_commands(self)
        try:
            await self.tree.sync()
            logger.info("Slash commands synced successfully.")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")

        logger.info("Bot setup complete (Health: 8080, Metrics: 9090)")

    def _on_config_reload(self, new_config: JenniferConfig) -> None:
        """Called by watch_config() whenever config.json changes."""
        old_log_level = self.config.log_level
        self.config = new_config
        self.sanitizer = get_sanitizer(new_config)

        # Re-apply log level if it changed
        if new_config.log_level != old_log_level:
            setup_logging(
                log_level=new_config.log_level,
                log_dir="logs",
                use_json=True,
                app_name=new_config.name,
            )
            logger.info(f"Log level changed to {new_config.log_level}")

        logger.info(f"Config reloaded live - name={new_config.name}")
    
    async def _image_worker(self):
        """Worker for processing image generation tasks."""
        logger.info("Image worker started")
        while not self.is_closed():
            try:
                task = await self.image_queue.get()
                with MetricsContext("image_gen"):
                    with tracer._otel_tracer.start_as_current_span("image_worker_task") as span:
                        span.set_attribute("task_id", task.id)
                        span.set_attribute("user_id", task.user_id)
                        
                        try:
                            await self._process_image_task(task)
                            await self.image_queue.mark_done(task)
                        except Exception as e:
                            logger.exception(f"Error in image task: {e}")
                            await self.image_queue.mark_failed(task, str(e))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected image worker error: {e}")
                await asyncio.sleep(1)

    async def _process_image_task(self, task: Task):
        """Process a single image generation task."""
        payload = task.payload
        channel = await self._resolve_channel(
            payload["channel_id"], user_id=payload.get("user_id")
        )
        if not channel:
            logger.error(f"Channel {payload['channel_id']} not found")
            return
        
        try:
            draw_msg = await channel.fetch_message(payload["message_id"])
            orig_id = payload.get("original_message_id", payload["message_id"])
            original_message = await channel.fetch_message(orig_id)
        except discord.NotFound: return
        
        async with channel.typing():
            from utils.image_gen import handle_image_generation
            # Pass None for histories to trigger HistoryManager fallback in interactions.py
            await handle_image_generation(self.config, original_message, None, self, draw_msg)

    async def _video_worker(self):
        """Worker for processing video generation tasks."""
        logger.info("Video worker started")
        while not self.is_closed():
            try:
                task = await self.video_queue.get()
                with MetricsContext("video_gen"):
                    try:
                        await self._process_video_task(task)
                        await self.video_queue.mark_done(task)
                    except Exception as e:
                        logger.exception(f"Error in video task: {e}")
                        await self.video_queue.mark_failed(task, str(e))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected video worker error: {e}")
                await asyncio.sleep(1)

    async def _process_video_task(self, task: Task):
        """Process a single video generation task."""
        payload = task.payload
        channel = await self._resolve_channel(
            payload["channel_id"], user_id=payload.get("user_id")
        )
        if not channel:
            logger.error(f"Channel {payload['channel_id']} not found")
            return
        
        try:
            vid_msg = await channel.fetch_message(payload["message_id"])
        except discord.NotFound: return
        
        await vid_msg.edit(content=f"{vid_msg.content}\n\n⏳ Generating video...")
        
        from utils.video_gen import VideoGenerator
        generator = VideoGenerator(self.config.video)
        
        video_path = await generator.generate(
            prompt=payload["prompt"],
            output_dir="data/videos",
            user_id=task.user_id,
            image_path=payload.get("image_path"),
        )
        
        await channel.send(f"🎬 Done!", file=discord.File(video_path))
        await vid_msg.delete()

    async def _message_worker(self):
        """Worker for processing chat message tasks."""
        logger.info("Message worker started")
        while not self.is_closed():
            try:
                task = await self.message_queue.get()
                with MetricsContext("message_chat"):
                    try:
                        await self._process_message_task(task)
                        await self.message_queue.mark_done(task)
                    except Exception as e:
                        logger.exception(f"Error in message task: {e}")
                        await self.message_queue.mark_failed(task, str(e))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected message worker error: {e}")
                await asyncio.sleep(1)

    async def _process_message_task(self, task: Task):
        """Process a single chat message task."""
        from utils.interactions import handle_message_processing
        payload = task.payload
        channel = await self._resolve_channel(
            payload["channel_id"], user_id=payload.get("user_id")
        )
        if not channel:
            logger.error(f"Channel {payload['channel_id']} not found")
            return
        
        try:
            message = await channel.fetch_message(payload["message_id"])
        except discord.NotFound: return
        
        # Pass None for histories to trigger HistoryManager fallback
        await handle_message_processing(self.config, message, None, None)

    @tasks.loop(minutes=1)
    async def _periodic_updates(self):
        """Update metrics and cleanup data."""
        try:
            # Update Queue Metrics
            QUEUE_DEPTH.labels(queue_name="image").set(self.image_queue.qsize())
            QUEUE_DEPTH.labels(queue_name="video").set(self.video_queue.qsize())
            QUEUE_DEPTH.labels(queue_name="message").set(self.message_queue.qsize())
            
            # Active users are tracked in Redis; until we expose a count API,
            # keep this metric best-effort instead of raising NameError.
            ACTIVE_USERS.set(0)
            
            # Cleanup old tasks (keep 12 hours)
            for q in [self.image_queue, self.video_queue, self.message_queue]:
                await q.cleanup_old_tasks(max_age_hours=12)
        except Exception as e:
            logger.error(f"Periodic update error: {e}")

    # =======================================================================
    # Discord Event Handlers
    # =======================================================================
    
    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
    
    async def on_message(self, message: discord.Message):
        if message.author.bot: return
        
        MESSAGES_RECEIVED.inc()
        
        with tracer._otel_tracer.start_as_current_span("on_message") as span:
            span.set_attribute("user_id", message.author.id)
            span.set_attribute("channel_id", message.channel.id)
            
            # Safety check
            is_safe, reason = self.sanitizer.check_safety(message.content)
            if not is_safe:
                logger.warning(f"Unsafe message from {message.author.id}: {reason}")
                await message.channel.send(f"⚠️ Sorry, I can't process that message: {reason}")
                return

            await self._process_incoming_message(message)

    async def _process_incoming_message(self, message: discord.Message):
        # Filtering logic
        if self.config.is_ignored_user(message.author.id): return
        
        # Check allowed channels
        if (
            not isinstance(message.channel, (discord.DMChannel, discord.Thread))
            and not self.config.is_allowed_channel(message.channel.id)
        ):
            return
            
        from bot.commands.handlers import extract_prefixed_command
        parsed_command = extract_prefixed_command(message.content.strip(), self.config.name, self.user.id)
        
        if parsed_command:
            COMMANDS_EXECUTED.labels(command=parsed_command.split()[0], status="success").inc()
            # Note: Histories are passed as {} to maintain legacy handler signature compatibility
            await handle_command(message, self.config, {}, self, "", parsed_command)
            return

        await self._handle_conversation(message)
    
    async def _handle_conversation(self, message: discord.Message):
        user_id = message.author.id
        
        # Check if we should respond
        should_respond = False
        is_active = await redis_manager.is_user_active(user_id, self.config.name)

        if isinstance(message.channel, discord.DMChannel):
            should_respond = self.config.allow_dm_responses or user_id in self.config.allowed_dm_users
        elif is_active:
            should_respond = True
        elif self.user in message.mentions or self.config.name.lower() in message.content.lower():
            should_respond = True
        elif not self.config.only_when_called:
            should_respond = True
            
        if should_respond:
            await redis_manager.set_active_user(user_id, self.config.name, self.config.interaction_timeout)
            await self._queue_message(message)

    async def _queue_message(self, message: discord.Message):
        task = Task(id=None, type="message", payload={
            "channel_id": message.channel.id, "message_id": message.id,
            "user_id": message.author.id, "user_name": message.author.display_name,
        }, user_id=message.author.id, created_at=time.time())
        await self.message_queue.put(task)
        async with message.channel.typing(): pass

    async def _resolve_channel(
        self,
        channel_id: int,
        user_id: Optional[int] = None,
    ) -> Optional[discord.abc.Messageable]:
        """Resolve guild or DM channels for queued tasks.

        `get_channel()` only checks cache and commonly misses DM channels, so
        queued work needs API fallbacks.
        """
        channel = self.get_channel(channel_id)
        if channel is not None:
            return channel

        with contextlib.suppress(discord.NotFound, discord.Forbidden, discord.HTTPException):
            channel = await self.fetch_channel(channel_id)
            if channel is not None:
                return channel

        if user_id is None:
            return None

        user = self.get_user(user_id)
        if user is None:
            with contextlib.suppress(discord.NotFound, discord.Forbidden, discord.HTTPException):
                user = await self.fetch_user(user_id)

        if user is None:
            return None

        dm_channel = getattr(user, "dm_channel", None)
        if dm_channel is not None:
            return dm_channel

        with contextlib.suppress(discord.Forbidden, discord.HTTPException):
            return await user.create_dm()

        return None

    async def close(self):
        logger.info("Shutting down...")
        if self._cleanup_task: self._cleanup_task.cancel()
        if self._config_watcher_task: self._config_watcher_task.cancel()
        for w in self._queue_workers: w.cancel()
        if self._periodic_updates.is_running():
            self._periodic_updates.stop()
        await super().close()


async def start_bot(config: JenniferConfig, config_path: str = "config/config.json"):
    setup_logging(log_level=config.log_level, log_dir="logs", use_json=True, app_name=config.name)
    bot = JenniferBot(config, config_path=config_path)
    try:
        await bot.start(config.discord_token)
    except KeyboardInterrupt: pass
    finally: await bot.close()
