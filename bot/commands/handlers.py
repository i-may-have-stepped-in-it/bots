"""
Command handlers extracted from monolithic app.py.
Organized by category: image, admin, session, voice, music.
"""

import asyncio
import logging
import re
import time

import discord

from core.config import JenniferConfig
from core.persistent_queue import PersistentQueue, Task
from core.redis_client import redis_manager

from .music import get_player, music_players

logger = logging.getLogger(__name__)


# Task queues (initialized by bot)
image_queue: PersistentQueue | None = None
video_queue: PersistentQueue | None = None
message_queue: PersistentQueue | None = None

# Active user tracking for conversation timeout
active_users: dict[int, float] = {}  # user_id: last_interaction_time


# ============================================================================
# Video Command Helpers
# ============================================================================

async def _parse_video_prompt(command: str) -> tuple[str, str | None]:
    """Parse video command to extract prompt and optional image path.
    
    Supports formats:
    - !txt2vid prompt text here
    - !txt2vid prompt text here --image path/to/image.jpg
    """
    # Remove command prefix
    prompt = command[8:].strip()  # After "!txt2vid"

    image_path = None

    # Check for --image flag
    if " --image " in prompt:
        parts = prompt.split(" --image ", 1)
        prompt = parts[0].strip()
        after_flag = parts[1].strip()
        tokens = after_flag.split()
        image_path = tokens[0] if tokens else None

    return prompt, image_path


# ============================================================================
# Permission Checks
# ============================================================================

def is_super_user_or_moderator(message: discord.Message, config: JenniferConfig) -> bool:
    """Check if user has elevated permissions."""
    user_id = message.author.id

    # Power users from config
    if config.is_power_user(user_id):
        return True

    # Discord moderators/admins
    perms = message.author.guild_permissions
    if perms and (
        perms.administrator
        or perms.manage_guild
        or perms.manage_messages
        or perms.moderate_members
    ):
        return True

    return False


def is_guild_admin_command(command: str) -> bool:
    """Commands restricted to admins in guild channels."""
    admin_commands = (
        "!txt2vid",
        "!check models",
        "!load model",
        "!change model",
        "!recreate agent",
        "!teamviewer",
    )
    return any(command.lower().startswith(cmd) for cmd in admin_commands)


# ============================================================================
# Command Parsing
# ============================================================================

def extract_prefixed_command(
    message_text: str,
    bot_name: str,
    bot_user_id: int
) -> str | None:
    """
    Extract command from message.
    
    Accepted forms:
    - !command ...
    - <@bot> !command ...
    - BotName !command ...
    """
    stripped = (message_text or "").strip()
    if not stripped:
        return None

    if stripped.startswith("!"):
        return stripped

    match = re.match(
        rf"^(?:<@!?{bot_user_id}>|{re.escape(bot_name)}[^\w\s]*)\s*(!\S.*)$",
        stripped,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    return None


# ============================================================================
# Command Router
# ============================================================================

async def handle_command(
    message: discord.Message,
    config: JenniferConfig,
    user_message_histories: dict,
    bot: discord.Client,
    history_file_name: str,
    parsed_command: str | None = None,
) -> bool:
    """
    Route and handle bot commands.
    
    Returns True if command was handled, False otherwise.
    """
    bot_name = config.name
    full_message = message.content
    user_id = message.author.id

    # Use pre-parsed command or extract
    if parsed_command:
        command = parsed_command.strip()
    else:
        command = extract_prefixed_command(full_message, bot_name, bot.user.id)
        if not command:
            return False

    logger.info(f"Processing command: '{command}' from user {user_id}")
    command_lower = command.lower()

    # Update active user tracking
    await redis_manager.set_active_user(user_id, bot_name, config.interaction_timeout)

    # Guild channel admin command restriction
    if (
        message.channel.type != discord.ChannelType.private
        and is_guild_admin_command(command_lower)
        and not is_super_user_or_moderator(message, config)
    ):
        await message.channel.send(
            "🔒 That command is admin-only in servers. Please DM me or ask a moderator."
        )
        return True

    # Route to specific handler
    handlers = [
        ("!draw", handle_draw_command),
        ("!send", handle_draw_command),  # Alias
        ("!txt2vid", handle_txt2vid_command),
        ("!check models", handle_check_models_command),
        ("!load model", handle_load_model_command),
        ("!change model", handle_change_model_command),
        ("!new session", handle_new_session_command),
        ("!recreate agent", handle_recreate_agent_command),
        ("!reset agent", handle_reset_agent_command),
        ("!join_vc", handle_join_vc_command),
        ("!leave_vc", handle_leave_vc_command),
        ("!play", handle_play_command),
        ("!skip", handle_skip_command),
        ("!stop", handle_stop_command),
        ("!volume", handle_volume_command),
        ("!now_playing", handle_now_playing_command),
        ("!queue", handle_queue_command),
        ("!pause", handle_pause_command),
        ("!resume", handle_resume_command),
        ("!help", handle_help_command),
        ("!commands", handle_help_command),
        ("!status", handle_status_command),
        ("!teamviewer", handle_teamviewer_command),
    ]

    for prefix, handler in handlers:
        if command_lower.startswith(prefix):
            try:
                await handler(
                    message=message,
                    config=config,
                    command=command,
                    command_lower=command_lower,
                    user_message_histories=user_message_histories,
                    bot=bot,
                    history_file_name=history_file_name,
                )
            except Exception as e:
                logger.exception(f"Error handling command '{command}': {e}")
                await message.channel.send(f"❌ Error processing command: {str(e)[:100]}")
            return True

    # Unknown command
    await message.channel.send(f"❓ Unknown command: `{command.split()[0]}`. Use `!help` for available commands.")
    return True


# ============================================================================
# Image Commands
# ============================================================================

async def handle_draw_command(
    message: discord.Message,
    config: JenniferConfig,
    command: str,
    command_lower: str,
    **kwargs
):
    """Handle !draw and !send commands."""

    # Check permissions
    if isinstance(message.channel, discord.TextChannel):
        bot_member = message.guild.me
        if not bot_member.guild_permissions.attach_files:
            await message.channel.send("❌ I don't have permission to attach files.")
            return

    draw_msg = await message.channel.send("🎨 Hang on while I get that for you...")

    # Create task for image queue
    task = Task(
        id=None,
        type="image",
        payload={
            "message_content": command,  # Use the extracted command (not full message)
            "channel_id": message.channel.id,
            "message_id": draw_msg.id,
            "original_message_id": message.id,  # Store original message ID
            "user_id": message.author.id,
            "user_name": message.author.display_name,
        },
        user_id=message.author.id,
        created_at=time.time(),
    )

    await image_queue.put(task)
    logger.info(f"Image generation queued for user {message.author.id}")


# ============================================================================
# Admin Commands
# ============================================================================

async def handle_txt2vid_command(
    message: discord.Message,
    config: JenniferConfig,
    command: str,
    **kwargs
):
    """Handle !txt2vid command - video generation."""
    if not config.is_power_user(message.author.id):
        await message.channel.send("🚫 This command is admin-only. Please DM me or ask a moderator.")
        return

    # Check if video backend is configured
    if config.video.backend == "zai" and not config.video.zai_api_key:
        await message.channel.send("❌ Video generation not configured. Set ZaiAPIKey in config.")
        return

    # Parse prompt
    prompt, image_path = await _parse_video_prompt(command)

    if not prompt:
        await message.channel.send(
            "⚠️ Please provide a prompt.\n"
            "Usage: `!txt2vid a cat playing piano`\n"
            "Optional: `!txt2vid a cat playing --image path/to/image.jpg`"
        )
        return

    # Check permissions
    if isinstance(message.channel, discord.TextChannel):
        bot_member = message.guild.me
        if not bot_member.guild_permissions.attach_files:
            await message.channel.send("❌ I don't have permission to attach files.")
            return

    # Send initial message
    backend_info = config.video.backend.upper()
    model_info = (
        config.video.zai_model if config.video.backend == "zai"
        else config.video.framepack_model
    )
    vid_msg = await message.channel.send(
        f"🎬 Starting video generation...\n"
        f"   Backend: `{backend_info}`\n"
        f"   Model: `{model_info}`\n"
        f"   Prompt: `{prompt[:50]}{'...' if len(prompt) > 50 else ''}`"
    )

    # Create task for video queue
    task = Task(
        id=None,
        type="video",
        payload={
            "prompt": prompt,
            "image_path": image_path,
            "channel_id": message.channel.id,
            "message_id": vid_msg.id,
            "user_id": message.author.id,
            "user_name": message.author.display_name,
        },
        user_id=message.author.id,
        created_at=time.time(),
    )

    await video_queue.put(task)
    logger.info(f"Video generation queued for user {message.author.id}")


async def handle_check_models_command(
    message: discord.Message,
    config: JenniferConfig,
    **kwargs
):
    """Handle !check models command."""
    if not config.is_power_user(message.author.id):
        await message.channel.send("🚫 Permission denied.")
        return

    # Import here to avoid circular deps
    from utils.image_gen import check_models

    try:
        available_models = await check_models(config)
        if available_models:
            models_text = "\n".join(f"• {m}" for m in available_models[:20])
            if len(available_models) > 20:
                models_text += f"\n... and {len(available_models) - 20} more"
            await message.channel.send(f"**Available Models:**\n```\n{models_text}\n```")
        else:
            await message.channel.send("❌ No models available.")
    except Exception as e:
        logger.error(f"Error checking models: {e}")
        await message.channel.send(f"❌ Error: {str(e)[:200]}")


async def handle_load_model_command(
    message: discord.Message,
    config: JenniferConfig,
    command: str,
    **kwargs
):
    """Handle !load model command."""
    if not config.is_power_user(message.author.id):
        await message.channel.send("🚫 Permission denied.")
        return

    model_name = command[11:].strip()  # After "!load model"
    if not model_name:
        await message.channel.send("⚠️ Please specify a model name.")
        return

    load_msg = await message.channel.send(f"⏳ Loading model: `{model_name}`...")

    try:
        from utils.image_gen import check_current_model

        # Temporarily point config at the requested model so check_current_model
        # will detect a mismatch and issue the backend switch request.
        original_model = config.sd.model
        config.sd.model = model_name
        try:
            result = await check_current_model(config, message, load_msg)
        finally:
            # Always restore in case the switch fails partway through.
            config.sd.model = original_model if result is None else model_name

        if result:
            config.sd.model = model_name
            await load_msg.edit(content=f"✅ Model loaded: `{model_name}`")
        else:
            config.sd.model = original_model
            await load_msg.edit(content=f"❌ Failed to load model: `{model_name}` (backend returned no result)")
    except Exception as e:
        logger.exception(f"Error loading model: {e}")
        await load_msg.edit(content=f"❌ Failed to load model: {str(e)[:200]}")


async def handle_change_model_command(
    message: discord.Message,
    config: JenniferConfig,
    command: str,
    **kwargs
):
    """Handle !change model command."""
    if not is_super_user_or_moderator(message, config):
        await message.channel.send("🚫 Permission denied.")
        return

    model_name = command[13:].strip()  # After "!change model"
    if not model_name:
        await message.channel.send("⚠️ Please specify a model name.")
        return

    try:
        from utils.openclaw import change_openclaw_model

        success = await change_openclaw_model(config, message.author.id, model_name)

        if success:
            # Update config for this session
            config.openclaw.model = model_name
            await message.channel.send(
                f"✅ Model changed to `{model_name}`. Next message will use the new model."
            )
        else:
            await message.channel.send(f"❌ Failed to change model to `{model_name}`.")
    except Exception as e:
        logger.error(f"Error changing model: {e}")
        await message.channel.send(f"❌ Error: {str(e)[:200]}")


async def handle_teamviewer_command(
    message: discord.Message,
    config: JenniferConfig,
    **kwargs
):
    """Handle !teamviewer command."""
    try:
        from utils.teamviewer import teamviewer
        await teamviewer(config, message)
    except Exception as e:
        logger.error(f"Error in teamviewer command: {e}")
        await message.channel.send(f"❌ Error: {str(e)[:200]}")


# ============================================================================
# Session Commands
# ============================================================================

async def handle_new_session_command(
    message: discord.Message,
    config: JenniferConfig,
    user_message_histories: dict,
    history_file_name: str,
    **kwargs
):
    """Handle !new session command."""
    if not is_super_user_or_moderator(message, config):
        await message.channel.send("🚫 Permission denied.")
        return

    try:
        from utils.interactions import save_message_histories
        from utils.openclaw import start_openclaw_new_session

        # Clear local history
        user_id_str = str(message.author.id)
        if user_id_str in user_message_histories:
            user_message_histories[user_id_str] = []
            await save_message_histories(history_file_name, user_message_histories)

        # Reset OpenClaw session
        success = await start_openclaw_new_session(config, message.author.id)

        if success:
            await message.channel.send("✅ New session started. History cleared.")
        else:
            await message.channel.send("⚠️ Local history cleared, but gateway session reset failed.")
    except Exception as e:
        logger.error(f"Error starting new session: {e}")
        await message.channel.send(f"❌ Error: {str(e)[:200]}")


async def handle_recreate_agent_command(
    message: discord.Message,
    config: JenniferConfig,
    user_message_histories: dict,
    history_file_name: str,
    bot: discord.Client,
    **kwargs
):
    """Handle !recreate agent command."""
    if not is_super_user_or_moderator(message, config):
        await message.channel.send("🚫 Permission denied.")
        return

    load_msg = await message.channel.send("🔄 Recreating agent...")

    try:
        from utils.interactions import save_message_histories
        from utils.openclaw import delete_openclaw_agent

        # Clear local history
        user_id_str = str(message.author.id)
        if user_id_str in user_message_histories:
            user_message_histories[user_id_str] = []
            await save_message_histories(history_file_name, user_message_histories)

        # Delete and recreate OpenClaw agent
        await delete_openclaw_agent(config, message.author.id, message.author.display_name)

        # Clear verified cache so agent is recreated on next message
        from utils.openclaw import get_client
        client = get_client(config)
        if client:
            agent_id = client.normalize_id(message.author.id)
            client._verified_agents.pop(agent_id, None)

        await load_msg.edit(content="✅ Agent recreated successfully. Send a message to start fresh.")

    except Exception as e:
        logger.exception(f"Error recreating agent: {e}")
        await load_msg.edit(content=f"❌ Error recreating agent: {str(e)[:200]}")


async def handle_reset_agent_command(
    message: discord.Message,
    config: JenniferConfig,
    user_message_histories: dict,
    history_file_name: str,
    **kwargs
):
    """Handle !reset agent command."""
    if not is_super_user_or_moderator(message, config):
        await message.channel.send("🚫 Permission denied.")
        return

    try:
        from utils.interactions import save_message_histories
        from utils.openclaw import reset_openclaw_messages

        # Clear local history
        user_id_str = str(message.author.id)
        if user_id_str in user_message_histories:
            user_message_histories[user_id_str] = []
            await save_message_histories(history_file_name, user_message_histories)

        # Reset OpenClaw messages
        await reset_openclaw_messages(config, message.author.id)

        await message.channel.send("✅ Messages reset. Context cleared.")
    except Exception as e:
        logger.error(f"Error resetting agent: {e}")
        await message.channel.send(f"❌ Error: {str(e)[:200]}")


# ============================================================================
# Voice Commands
# ============================================================================

async def handle_join_vc_command(
    message: discord.Message,
    config: JenniferConfig = None,
    **kwargs
):
    """Handle !join_vc command."""
    if not message.author.voice:
        await message.channel.send("⚠️ You must be in a voice channel to use this command.")
        return

    try:
        # Import voice handler
        from utils.voice_recv_class import VoiceRecvClient

        channel = message.author.voice.channel

        # Check permissions before joining
        bot_member = message.guild.me
        if not bot_member.guild_permissions.connect:
            await message.channel.send("❌ I don't have permission to join voice channels.")
            return
        if not bot_member.guild_permissions.speak:
            await message.channel.send("❌ I don't have permission to speak in voice channels.")
            return

        # Pass config to VoiceRecvClient
        vc = await channel.connect(
            cls=lambda *args, **kwargs: VoiceRecvClient(config, *args, **kwargs)
        )
        vc.handle_audio_processing(message)

        await message.add_reaction("👍")
        logger.info(f"Joined voice channel: {channel.name}")
    except discord.errors.ClientException as e:
        logger.error(f"Voice join error: {e}")
        await message.channel.send("❌ I'm already in a voice channel or can't join.")
    except Exception as e:
        logger.error(f"Error joining voice channel: {e}")
        await message.channel.send(f"❌ Failed to join: {str(e)[:100]}")


async def handle_leave_vc_command(
    message: discord.Message,
    **kwargs
):
    """Handle !leave_vc command."""
    if not message.guild or not message.guild.voice_client:
        await message.channel.send("ℹ️ I'm not in a voice channel.")
        return

    try:
        await message.guild.voice_client.disconnect()

        # Clean up music player if exists
        if message.guild.id in music_players:
            del music_players[message.guild.id]

        await message.channel.send("👋 Left voice channel.")
        await message.add_reaction("👋")
    except Exception as e:
        logger.error(f"Error leaving voice channel: {e}")
        await message.channel.send(f"❌ Error: {str(e)[:100]}")


# ============================================================================
# Music Commands
# ============================================================================

async def handle_play_command(
    message: discord.Message,
    bot: discord.Client,
    command: str,
    **kwargs
):
    """Handle !play command."""
    if not message.guild:
        await message.channel.send("❌ This command only works in servers.")
        return

    if not message.author.voice:
        await message.channel.send("⚠️ You must be in a voice channel to use this command.")
        return

    # Extract URL
    url = command[5:].strip()  # After "!play"
    if not url:
        await message.channel.send("⚠️ Please provide a URL to play.")
        return

    try:
        # Get or create player
        player = get_player(message.guild.id, message.channel, bot)

        # Join channel if not already in one
        channel = message.author.voice.channel
        if not player.voice_client or not player.voice_client.is_connected():
            await player.join(channel)

        # Add to queue
        await player.enqueue(url)

        if not player.is_playing():
            await player.play_next()
        else:
            await message.channel.send(f"🎵 Added to queue: {url}")

    except Exception as e:
        logger.exception(f"Error in play command: {e}")
        await message.channel.send(f"❌ Error: {str(e)[:100]}")


async def handle_skip_command(
    message: discord.Message,
    **kwargs
):
    """Handle !skip command."""
    if not message.guild:
        return

    player = music_players.get(message.guild.id)
    if not player:
        await message.channel.send("ℹ️ I'm not playing anything right now.")
        return

    await player.skip()


async def handle_stop_command(
    message: discord.Message,
    **kwargs
):
    """Handle !stop command."""
    if not message.guild:
        return

    player = music_players.get(message.guild.id)
    if not player:
        await message.channel.send("ℹ️ I'm not playing anything right now.")
        return

    await player.stop()


async def handle_volume_command(
    message: discord.Message,
    command: str,
    **kwargs
):
    """Handle !volume command."""
    if not message.guild:
        return

    player = music_players.get(message.guild.id)
    if not player:
        await message.channel.send("ℹ️ I'm not in a voice channel.")
        return

    # Parse volume
    try:
        volume = float(command[7:].strip())  # After "!volume"
        if not 0.0 <= volume <= 1.0:
            await message.channel.send("⚠️ Volume must be between 0.0 and 1.0")
            return

        await player.set_volume(volume)
        await message.channel.send(f"🔊 Volume set to {volume:.0%}")
    except ValueError:
        await message.channel.send("⚠️ Please provide a number between 0.0 and 1.0")


async def handle_now_playing_command(
    message: discord.Message,
    **kwargs
):
    """Handle !now_playing command."""
    if not message.guild:
        return

    player = music_players.get(message.guild.id)
    if not player or not player.now_playing:
        await message.channel.send("ℹ️ Nothing is currently playing.")
        return

    await message.channel.send(f"🎵 Now playing: **{player.now_playing}**")


async def handle_queue_command(
    message: discord.Message,
    **kwargs
):
    """Handle !queue command."""
    if not message.guild:
        return

    player = music_players.get(message.guild.id)
    if not player:
        await message.channel.send("ℹ️ I'm not in a voice channel.")
        return

    queue_list = player.get_queue_list()
    if not queue_list:
        await message.channel.send("📭 The queue is empty.")
        return

    queue_text = "\n".join(f"{i+1}. {url}" for i, url in enumerate(queue_list[:10]))
    if len(queue_list) > 10:
        queue_text += f"\n... and {len(queue_list) - 10} more"

    await message.channel.send(f"**🎵 Song Queue:**\n```\n{queue_text}\n```")


async def handle_pause_command(
    message: discord.Message,
    **kwargs
):
    """Handle !pause command."""
    if not message.guild:
        return

    player = music_players.get(message.guild.id)
    if player:
        await player.pause()


async def handle_resume_command(
    message: discord.Message,
    **kwargs
):
    """Handle !resume command."""
    if not message.guild:
        return

    player = music_players.get(message.guild.id)
    if player:
        await player.resume()


# ============================================================================
# Utility Commands
# ============================================================================

async def handle_status_command(
    message: discord.Message,
    config: JenniferConfig,
    bot: discord.Client,
    **kwargs
):
    """Handle !status command - shows system health."""
    from utils.ssl_config import SSLConfigManager

    embed = discord.Embed(
        title=f"📊 {config.name} System Status",
        color=0x00ff00,
        timestamp=discord.utils.utcnow()
    )

    # Check OpenClaw
    try:
        import aiohttp
        ssl_context = SSLConfigManager.get_ssl_context(config.openclaw.gateway)
        async with aiohttp.ClientSession() as s, s.get(
            f"{config.openclaw.gateway}/health",
            ssl=ssl_context,
            timeout=aiohttp.ClientTimeout(total=5)
        ) as r:
            openclaw_status = "🟢 Online" if r.status == 200 else f"🟠 HTTP {r.status}"
    except Exception as e:
        openclaw_status = f"🔴 {str(e)[:30]}"

    embed.add_field(name="OpenClaw Gateway", value=openclaw_status, inline=False)

    # Check LocalAI
    try:
        import aiohttp
        ssl_context = SSLConfigManager.get_ssl_context(config.openclaw.model_endpoint)
        async with aiohttp.ClientSession() as s, s.get(
            f"{config.openclaw.model_endpoint}/models",
            ssl=ssl_context,
            timeout=aiohttp.ClientTimeout(total=5)
        ) as r:
            if r.status == 200:
                data = await r.json()
                model_count = len(data.get("data", []))
                localai_status = f"🟢 {model_count} models"
            else:
                localai_status = f"🟠 HTTP {r.status}"
    except Exception as e:
        localai_status = f"🔴 {str(e)[:30]}"

    embed.add_field(name="LocalAI", value=localai_status, inline=False)

    # Check Image Generation Backend
    try:
        import aiohttp

        from integrations.image_generation import (
            create_adapter_from_config,
            get_backend_display_name,
        )

        # Create a config dict for the adapter
        config_dict = {
            "SDBackend": config.sd.backend,
            "SDURL": config.sd.url,
        }
        adapter = create_adapter_from_config(config_dict)
        backend_name = get_backend_display_name(config.sd.backend)

        # Use adapter's health check endpoint
        ssl_context = SSLConfigManager.get_ssl_context(config.sd.url)
        async with aiohttp.ClientSession() as s:
            # Use the appropriate endpoint for each backend
            health_url = adapter.get_options_endpoint()
            async with s.get(
                health_url,
                ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                if r.status == 200:
                    sd_status = f"🟢 {backend_name}"
                else:
                    sd_status = f"🟠 {backend_name} HTTP {r.status}"
    except Exception as e:
        sd_status = f"🔴 {str(e)[:30]}"

    embed.add_field(name="Image Backend", value=sd_status, inline=False)

    # Check Video Generation
    try:
        from utils.video_gen import check_video_health
        video_health = await check_video_health(config.video)
        if video_health.get("healthy"):
            backend = config.video.backend.upper()
            video_status = f"🟢 {backend}"
        else:
            video_status = f"🟠 {video_health.get('error', 'Unavailable')[:30]}"
    except Exception as e:
        video_status = f"🔴 {str(e)[:30]}"

    embed.add_field(name="Video Generation", value=video_status, inline=False)

    # Bot stats
    embed.add_field(
        name="🤖 Bot Stats",
        value=f"Guilds: {len(bot.guilds)}\nLatency: {bot.latency*1000:.0f}ms",
        inline=False
    )

    # Queue stats
    if image_queue and message_queue:
        queue_stats = f"Images: {image_queue.qsize()}\nMessages: {message_queue.qsize()}"
        if video_queue:
            queue_stats += f"\nVideos: {video_queue.qsize()}"
        embed.add_field(name="📋 Queue Depth", value=queue_stats, inline=False)

    # Active voice connections
    voice_count = len(bot.voice_clients)
    embed.add_field(name="🔊 Voice Connections", value=str(voice_count), inline=False)

    # Current model
    embed.add_field(
        name="🧠 Current Model",
        value=f"`{config.openclaw.model}`",
        inline=False
    )

    await message.channel.send(embed=embed)


# =============================================================================
# Message Processing
# =============================================================================

async def check_legacy_keywords(
    message: discord.Message,
    config: JenniferConfig,
    user_message_histories: dict,
    bot: discord.Client,
    history_file_name: str,
) -> bool:
    """
    Check for legacy keywords in normal chat messages.
    Maintains parity with Lauren and Yennifer keyword-based commands.
    """
    content_lower = message.content.lower()
    is_admin = is_super_user_or_moderator(message, config)

    # Map keywords to prefixed commands
    if "draw" in content_lower or "send" in content_lower:
        # Avoid false positives for "send" in common conversation
        if "send" in content_lower and not any(kw in content_lower for kw in ["draw", "pic", "image", "photo"]):
            # Only trigger 'send' if it looks like an image request
            if not content_lower.startswith("send"):
                return False

        # Extract everything after 'draw' or 'send' as the prompt
        match = re.search(r"(?:draw|send)\s+(.*)", content_lower)
        prompt = match.group(1) if match else content_lower
        await handle_draw_command(message, config, f"!draw {prompt}", "!draw",
                                 user_message_histories=user_message_histories, bot=bot,
                                 history_file_name=history_file_name)
        return True

    elif "check models" in content_lower:
        if message.channel.type == discord.ChannelType.private or is_admin:
            await handle_check_models_command(message, config)
        else:
            await message.channel.send("🔒 I'm sorry, I cannot run that here (admin only).")
        return True

    elif "load model" in content_lower:
        if message.channel.type == discord.ChannelType.private or is_admin:
            # Extract model name
            model_name = message.content[10:].strip()
            await handle_load_model_command(message, config, f"!load model {model_name}")
        else:
            await message.channel.send("🔒 I'm sorry, I cannot run that here (admin only).")
        return True

    elif "join_vc" in content_lower or "join-vc" in content_lower:
        await handle_join_vc_command(message, config)
        return True

    elif "leave_vc" in content_lower or "leave-vc" in content_lower:
        await handle_leave_vc_command(message)
        return True

    return False


async def handle_messages(
    message: discord.Message,
    config: JenniferConfig,
    user_message_histories: dict,
    history_file_name: str,
    bot: discord.Client,
):
    """
    Handle incoming messages and determine if bot should respond.
    
    This is the main entry point for message processing from on_message events.
    It filters messages, handles commands, and queues regular messages for processing.
    """
    ignored_users = config.ignored_users
    ignored_words = config.ignored_words
    respond_to_mentions = config.respond_to_mentions
    interaction_timeout = config.interaction_timeout

    try:
        logger.info(f"Received message from {message.author} in channel {message.channel}")
        logger.debug(f"Message content: {message.content}")

        # Check channel is allowed (for non-DM, non-thread channels)
        if not isinstance(message.channel, (discord.Thread, discord.DMChannel)):
            if message.channel.id not in config.allowed_channels:
                logger.info("Message not in an allowed channel. Ignoring.")
                return

        # Check ignored users
        if message.author.id in ignored_users:
            logger.info(f"Message author {message.author.id} is ignored")
            return

        # Check ignored words
        if any(word.lower() in message.content.lower() for word in ignored_words):
            logger.info("Message contains ignored words. Ignoring.")
            return

        stripped_message = message.content.strip()
        bot_name = config.name

        # Extract and handle commands
        parsed_command = extract_prefixed_command(stripped_message, bot_name, bot.user.id)
        if parsed_command:
            await handle_command(
                message=message,
                config=config,
                user_message_histories=user_message_histories,
                bot=bot,
                history_file_name=history_file_name,
                parsed_command=parsed_command,
            )
            logger.info("Message is a command. Ignoring for regular processing.")
            return

        # FALLBACK: Check for legacy keywords (Lauren/Yennifer compatibility)
        if await check_legacy_keywords(
            message=message,
            config=config,
            user_message_histories=user_message_histories,
            bot=bot,
            history_file_name=history_file_name
        ):
            logger.info("Handled legacy keyword command")
            return

        # Handle DMs with allowed responses
        if message.channel.type == discord.ChannelType.private:
            if config.allow_dm_responses or message.author.id in config.allowed_dm_users:
                logger.info("Responding to DM")
                async with message.channel.typing():
                    await _queue_message_task(
                        message, config, user_message_histories, history_file_name
                    )
                return
            else:
                await message.channel.send("I cannot talk here. Please try a regular channel.")
                logger.info("DM responses disabled, ignoring.")
                return

        # Check active user timeout via Redis
        is_active = await redis_manager.is_user_active(message.author.id, bot_name)
        if is_active:
            logger.info(f"Continuing interaction with active user {message.author.name}")
            async with message.channel.typing():
                await redis_manager.set_active_user(message.author.id, bot_name, interaction_timeout)
                await _queue_message_task(
                    message, config, user_message_histories, history_file_name
                )
            return

        # Handle mentions and replies
        if respond_to_mentions and (bot.user in message.mentions or
                                     (message.reference and message.reference.message_id)):
            # Check if reply is to the bot
            if message.reference and message.reference.message_id:
                try:
                    referenced = await message.channel.fetch_message(message.reference.message_id)
                    if referenced.author.id != bot.user.id:
                        logger.info("Ignoring reply to another user")
                        return
                except discord.NotFound:
                    logger.warning("Referenced message not found")
                    return

            logger.info(f"Processing mention/reply from {message.author.name}")
            async with message.channel.typing():
                await redis_manager.set_active_user(message.author.id, bot_name, interaction_timeout)
                await _queue_message_task(
                    message, config, user_message_histories, history_file_name
                )
            return

        # Only enforce OnlyWhenCalled if user is NOT active
        if config.only_when_called and bot_name.lower() not in message.content.lower():
            logger.info("Message does not contain bot name and user is not active. Ignoring.")
            return

        # Process the message (OnlyWhenCalled is False or bot name was mentioned)
        logger.info(f"Processing message: {message.content[:50]}...")
        async with message.channel.typing():
            await redis_manager.set_active_user(message.author.id, bot_name, interaction_timeout)
            await _queue_message_task(
                message, config, user_message_histories, history_file_name
            )

    except Exception as e:
        logger.exception(f"Error handling message: {e}")


async def _queue_message_task(
    message: discord.Message,
    config: JenniferConfig,
    user_message_histories: dict,
    history_file_name: str,
):
    """Helper to queue a message processing task."""
    if message_queue is None:
        logger.error("Message queue not initialized")
        return

    task = Task(
        id=None,
        type="message",
        payload={
            "message_content": message.content,
            "channel_id": message.channel.id,
            "message_id": message.id,
            "user_id": message.author.id,
            "user_name": message.author.display_name,
            "history_file_name": history_file_name,
        },
        user_id=message.author.id,
        created_at=time.time(),
    )

    await message_queue.put(task)
    logger.debug(f"Message task queued for user {message.author.id}")


async def handle_help_command(
    message: discord.Message,
    config: JenniferConfig,
    **kwargs
):
    """Handle !help command."""
    is_admin = is_super_user_or_moderator(message, config)
    is_dm = message.channel.type == discord.ChannelType.private

    embed = discord.Embed(
        title=f"🆘 {config.name} Commands",
        description=f"My prefix is `!` or mention me by name (`{config.name}`)",
        color=0x0099ff
    )

    # General commands
    general = [
        "`!draw <prompt>` - Generate an image",
        "`!join_vc` - Join your voice channel",
        "`!leave_vc` - Leave voice channel",
        "`!status` - Check system status",
    ]
    embed.add_field(name="📷 General", value="\n".join(general), inline=False)

    # Music commands
    music = [
        "`!play <url>` - Play music from URL",
        "`!skip` - Skip current song",
        "`!stop` - Stop and clear queue",
        "`!pause` / `!resume` - Playback control",
        "`!volume <0.0-1.0>` - Set volume",
        "`!queue` - Show song queue",
        "`!now_playing` - Current song info",
    ]
    embed.add_field(name="🎵 Music", value="\n".join(music), inline=False)

    # Session commands (DM or admin)
    if is_dm or is_admin:
        session = [
            "`!new session` - Start fresh conversation",
            "`!reset agent` - Clear message history",
            "`!recreate agent` - Full agent rebuild",
            "`!change model <name>` - Switch LLM model",
        ]
        embed.add_field(name="🔄 Session", value="\n".join(session), inline=False)

    # Admin commands
    if is_admin:
        admin = [
            "`!check models` - List available SD models",
            "`!load model <name>` - Load SD model",
            "`!txt2vid` - Generate video",
            "`!teamviewer` - Remote access info",
        ]
        embed.add_field(name="🔐 Admin", value="\n".join(admin), inline=False)

    await message.channel.send(embed=embed)
