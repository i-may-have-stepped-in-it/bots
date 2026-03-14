import logging
import json
from datetime import datetime
from utils.utility_functions import *
import discord
import asyncio
import textwrap

async def add_message_to_history(config, role, user_id, user_name, message_content, user_message_histories, history_file_name):
    try:
        if user_id not in user_message_histories:
            user_message_histories[user_id] = []
        
        timestamp = datetime.now().isoformat()
        user_message_histories[user_id].append({
            'role': role, 
            'name': user_name, 
            'content': message_content,
            'timestamp': timestamp
        })
        
        total_character_count = sum(len(entry['content']) for entry in user_message_histories.get(user_id, []) if entry is not None)
        while total_character_count > config["History_Length"]:
            oldest_entry = user_message_histories[user_id].pop(0)
            total_character_count -= len(oldest_entry['content'])
        
        # Offload blocking I/O to thread
        await asyncio.to_thread(_save_json_sync, history_file_name, user_message_histories)
        logging.debug("Message added to history and saved to file successfully.")
    except Exception as e:
        logging.error("An error occurred while writing to the JSON file in add_message_to_history: " + str(e))

async def save_message_histories(history_file_name, user_message_histories):
    try:
        # Offload blocking I/O to thread
        await asyncio.to_thread(_save_json_sync, history_file_name, user_message_histories)
        logging.debug("Message histories saved to file successfully in save_message_histories.")
    except Exception as e:
        logging.error("An error occurred while saving message histories in save_message_histories: " + str(e))

def _save_json_sync(history_file_name, user_message_histories):
    """Synchronous helper for JSON saving (to be run in thread)."""
    with open(history_file_name, 'w') as file:
        json.dump(user_message_histories, file)

async def handle_message_processing(config, message, user_message_histories, history_file_name):
    try:
        await add_message_to_history(config, 'user', message.author.id, message.author.display_name, message.content, user_message_histories, history_file_name)
        channel = message.channel
        logging.debug(f"include_personality parameter in handle_message_processing: {True}")

        async with channel.typing():
            openairesponse = await generate_response(config, message.author.id, message.author.display_name, user_message_histories, message)
        
        if isinstance(openairesponse, list):
            openairesponse = ' '.join(openairesponse)

        if openairesponse:
            # Add assistant response to history
            bot_name = config.get("Name", "Jennifer")
            await add_message_to_history(config, 'assistant', bot_name, bot_name, openairesponse, user_message_histories, history_file_name)
            
            chunks = split_into_chunks(openairesponse)
            for chunk in chunks:
                if isinstance(message.channel, discord.Thread):
                    await message.channel.send(chunk)
                else:
                    await message.channel.send(chunk)
                await asyncio.sleep(0.5)
    except Exception as e:
        logging.error("An error occurred during message processing in handle_message_processing: " + str(e))

def split_into_chunks(response):
	max_length = 1900
	chunks = []
	lines = response.split('\n')
	for line in lines:
		wrapped_lines = textwrap.wrap(line, width=max_length, break_long_words=False)
		for wrapped_line in wrapped_lines:
			chunks.append(wrapped_line.strip())
	return chunks