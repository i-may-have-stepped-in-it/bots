"""Message interaction utilities for Jennifer bot.

Handles message history management and processing with proper type safety
and async error handling.
"""

import asyncio
import json
import logging
import textwrap
from datetime import datetime
from typing import Any

import discord

from core.config import JenniferConfig
from utils.utility_functions import generate_response

logger = logging.getLogger(__name__)

# Type aliases for clarity
MessageEntry = dict[str, Any]
MessageHistories = dict[str, list[MessageEntry]]


async def add_message_to_history(
    config: JenniferConfig,
    role: str,
    user_id: int | str,
    user_name: str,
    message_content: str,
    user_message_histories: MessageHistories | None = None,
    history_file_name: str | None = None,
) -> None:
    """Add a message to the user's conversation history.
    
    Uses HistoryManager for SQLite persistence. Falls back to in-memory dict
    if provided for backward compatibility.
    """
    user_id_str = str(user_id)

    try:
        if user_message_histories is not None:
            # Legacy in-memory path
            if user_id_str not in user_message_histories:
                user_message_histories[user_id_str] = []

            timestamp = datetime.now().isoformat()
            user_message_histories[user_id_str].append({
                'role': role,
                'name': user_name,
                'content': message_content,
                'timestamp': timestamp
            })

            # Enforce history length limit
            total_chars = sum(len(e.get('content', '')) for e in user_message_histories[user_id_str] if e)
            history_limit = config.get("History_Length", 12000)
            while total_chars > history_limit and user_message_histories[user_id_str]:
                oldest = user_message_histories[user_id_str].pop(0)
                total_chars -= len(oldest.get('content', ''))

            if history_file_name:
                await asyncio.wait_for(
                    asyncio.to_thread(_save_json_sync, history_file_name, user_message_histories),
                    timeout=5.0
                )
        else:
            # Modern SQLite path
            from core.history import history_manager
            await history_manager.add_message(user_id_str, role, message_content)

        logger.debug(f"Message added to history for user {user_id_str}")

    except Exception as e:
        logger.error(f"Error saving message history: {e}")


async def save_message_histories(
    history_file_name: str,
    user_message_histories: MessageHistories,
) -> None:
    """Save all message histories to file.
    
    Args:
        history_file_name: Path to the JSON history file
        user_message_histories: In-memory history storage dictionary
    """
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_save_json_sync, history_file_name, user_message_histories),
            timeout=10.0
        )
        logger.debug("Message histories saved successfully")
    except asyncio.TimeoutError:
        logger.error("Timeout saving message histories")
    except Exception as e:
        logger.exception(f"Error saving message histories: {e}")


def _save_json_sync(history_file_name: str, user_message_histories: MessageHistories) -> None:
    """Synchronous helper for JSON saving (runs in executor thread).
    
    Args:
        history_file_name: Path to the JSON history file
        user_message_histories: History data to serialize
    """
    with open(history_file_name, 'w', encoding='utf-8') as file:
        json.dump(user_message_histories, file, indent=2, ensure_ascii=False)


async def handle_message_processing(
    config: JenniferConfig,
    message: discord.Message,
    user_message_histories: MessageHistories | None = None,
    history_file_name: str | None = None,
) -> None:
    """Process an incoming message and generate a response."""
    channel = message.channel
    user_id = message.author.id
    user_name = message.author.display_name

    try:
        # Add user message to history
        await add_message_to_history(
            config, 'user', user_id, user_name,
            message.content, user_message_histories, history_file_name
        )

        # Generate response with typing indicator
        async with channel.typing():
            response = await generate_response(
                config, user_id, user_name,
                user_message_histories, message
            )

        if response is None:
            return

        # Normalize response
        response_text = ' '.join(str(r) for r in response) if isinstance(response, list) else str(response)
        if not response_text.strip():
            return

        # Add bot response to history
        bot_name = config.get("Name", "Jennifer")
        await add_message_to_history(
            config, 'assistant', bot_name, bot_name,
            response_text, user_message_histories, history_file_name
        )

        # Send chunks
        for chunk in split_into_chunks(response_text):
            await channel.send(chunk)
            await asyncio.sleep(0.5)

    except discord.Forbidden:
        logger.error(f"Forbidden: Cannot send message in channel {channel.id}")
    except discord.HTTPException as e:
        logger.error(f"Discord HTTP error: {e.status} - {e.text}")
    except Exception as e:
        logger.exception(f"Error processing message: {e}")


def split_into_chunks(response: str, max_length: int = 1900) -> list[str]:
    """Split a response into Discord-friendly chunks.
    
    Discord has a 2000 character message limit. This function safely splits
    long responses while preserving line breaks where possible.
    
    Args:
        response: The text to split
        max_length: Maximum chunk length (default 1900 for safety)
        
    Returns:
        List of message chunks
    """
    if not response:
        return []

    # If response fits in one message, return as-is
    if len(response) <= max_length:
        return [response]

    chunks = []
    lines = response.split('\n')

    for line in lines:
        if len(line) > max_length:
            # Wrap long lines
            wrapped = textwrap.wrap(
                line,
                width=max_length,
                break_long_words=True,
                replace_whitespace=False
            )
            chunks.extend(wrapped)
        else:
            chunks.append(line)

    # Merge small chunks to maximize message size
    merged_chunks = []
    current_chunk = ""

    for chunk in chunks:
        if len(current_chunk) + len(chunk) + 1 <= max_length:
            # Preserve blank lines (don't use .strip() which removes them)
            if current_chunk:
                current_chunk += "\n" + chunk
            else:
                current_chunk = chunk
        else:
            if current_chunk:
                merged_chunks.append(current_chunk)
            current_chunk = chunk

    if current_chunk:
        merged_chunks.append(current_chunk)

    return merged_chunks if merged_chunks else [response[:max_length]]
