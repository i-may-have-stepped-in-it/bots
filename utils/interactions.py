"""Message interaction utilities for Jennifer bot.

Handles message history management and processing with proper type safety
and async error handling.
"""

import logging
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
import discord
import asyncio
import textwrap

from core.config import JenniferConfig
from utils.utility_functions import generate_response

logger = logging.getLogger(__name__)

# Type aliases for clarity
MessageEntry = Dict[str, Any]
MessageHistories = Dict[str, List[MessageEntry]]


async def add_message_to_history(
    config: JenniferConfig,
    role: str,
    user_id: Union[int, str],
    user_name: str,
    message_content: str,
    user_message_histories: MessageHistories,
    history_file_name: str,
) -> None:
    """Add a message to the user's conversation history.
    
    Automatically truncates history based on configured character limit.
    Offloads file I/O to a thread to avoid blocking the event loop.
    
    Args:
        config: Bot configuration with history_length setting
        role: Message role ('user' or 'assistant')
        user_id: Discord user ID
        user_name: Display name of the user
        message_content: The message content to store
        user_message_histories: In-memory history storage dictionary
        history_file_name: Path to the JSON history file
    """
    user_id_str = str(user_id)
    
    try:
        if user_id_str not in user_message_histories:
            user_message_histories[user_id_str] = []
        
        timestamp = datetime.now().isoformat()
        user_message_histories[user_id_str].append({
            'role': role,
            'name': user_name,
            'content': message_content,
            'timestamp': timestamp
        })
        
        # Enforce history length limit by character count
        total_chars = sum(
            len(entry.get('content', ''))
            for entry in user_message_histories[user_id_str]
            if entry is not None
        )
        
        history_limit = config.get("History_Length", 12000)
        while total_chars > history_limit:
            if not user_message_histories[user_id_str]:
                break
            oldest_entry = user_message_histories[user_id_str].pop(0)
            total_chars -= len(oldest_entry.get('content', ''))
        
        # Offload blocking I/O to thread with timeout
        await asyncio.wait_for(
            asyncio.to_thread(_save_json_sync, history_file_name, user_message_histories),
            timeout=10.0
        )
        logger.debug(f"Message added to history for user {user_id_str}")
        
    except asyncio.TimeoutError:
        logger.error(f"Timeout saving history for user {user_id_str}")
    except Exception as e:
        logger.exception(f"Error saving message history: {e}")


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
    user_message_histories: MessageHistories,
    history_file_name: str,
) -> None:
    """Process an incoming message and generate a response.
    
    Handles the full flow: add to history, generate response, send reply.
    
    Args:
        config: Bot configuration
        message: Discord message to process
        user_message_histories: Conversation history storage
        history_file_name: Path to history file
    """
    channel = message.channel
    user_id = message.author.id
    user_name = message.author.display_name
    
    try:
        # Add user message to history
        await add_message_to_history(
            config, 'user', user_id, user_name,
            message.content, user_message_histories, history_file_name
        )
        
        logger.debug(f"Processing message with personality inclusion: True")
        
        # Generate response with typing indicator
        async with channel.typing():
            response = await generate_response(
                config, user_id, user_name,
                user_message_histories, message
            )
        
        if response is None:
            logger.warning(f"No response generated for user {user_id}")
            return
        
        # Normalize response to string
        if isinstance(response, list):
            response = ' '.join(str(r) for r in response)
        else:
            response = str(response)
        
        if not response.strip():
            return
        
        # Add bot response to history
        bot_name = config.get("Name", "Jennifer")
        await add_message_to_history(
            config, 'assistant', bot_name, bot_name,
            response, user_message_histories, history_file_name
        )
        
        # Split and send response chunks
        chunks = split_into_chunks(response)
        for chunk in chunks:
            await channel.send(chunk)
            await asyncio.sleep(0.5)  # Rate limit avoidance
            
    except discord.Forbidden:
        logger.error(f"Forbidden: Cannot send message in channel {channel.id}")
    except discord.HTTPException as e:
        logger.error(f"Discord HTTP error: {e.status} - {e.text}")
    except Exception as e:
        logger.exception(f"Error processing message: {e}")


def split_into_chunks(response: str, max_length: int = 1900) -> List[str]:
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
