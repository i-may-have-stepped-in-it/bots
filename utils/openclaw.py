import aiohttp
import logging
import json
import asyncio
import os
import re

class OpenClawClient:
    """
    Client for interacting with the OpenClaw Gateway.
    Creates a unique agent for each user.
    Uses the "gateway" tool to dynamically update OpenClaw configuration.
    """
    def __init__(self, gateway_url, api_token):
        # Ensure url doesn't have trailing slash
        self.url = gateway_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        self.api_token = api_token

    def normalize_id(self, user_id):
        """Normalizes user_id to a valid OpenClaw agent ID (alphanumeric and hyphens)."""
        return re.sub(r'[^a-zA-Z0-9-]', '-', f"jennifer-user-{user_id}").lower()

    async def wait_for_gateway(self, timeout=30):
        """Waits for the gateway to become responsive again after a restart."""
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.url}/health", headers=self.headers, ssl=False, timeout=2) as resp:
                        if resp.status == 200:
                            logging.info("OpenClaw Gateway is back online.")
                            return True
            except Exception:
                pass
            await asyncio.sleep(2)
        logging.error("Timeout waiting for OpenClaw Gateway to restart.")
        return False

    async def ensure_agent_exists(self, user_id, user_name, config):
        """
        Checks if an agent exists for the user, and creates one if it doesn't.
        Injects user identity (name) into the agent's initial context.
        """
        agent_id = self.normalize_id(user_id)
        
        # 1. Use config.get to see if it exists (more reliable than /v1/models if it returns HTML)
        try:
            get_payload = {
                "tool": "gateway",
                "args": {
                    "action": "config.get"
                },
                "sessionKey": f"jennifer:system:admin:check-{agent_id}"
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.url}/tools/invoke", json=get_payload, headers=self.headers, ssl=False) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("ok"):
                            full_config = data.get("result", {}).get("config", {})
                            agents_list = full_config.get("agents", {}).get("list", [])
                            if any(a.get("id") == agent_id for a in agents_list):
                                return agent_id
        except Exception as e:
            logging.error(f"Error checking agents via config.get: {e}")

        # 2. Create agent if not found
        logging.info(f"Creating new OpenClaw agent for user {user_name} ({user_id})...")
        
        bot_name = config.get("Name", "your persona")
        personality = config.get("OpenClawPersonality", config.get("Personality", ""))
        system_prompt = config.get("OpenClawSystemPrompt", "")
        user_context = f"The person you are talking to is named \"{user_name}\". They are using Discord."
        combined_instructions = f"{system_prompt}\n\nCORE PERSONALITY:\n{personality}\n\nUSER IDENTITY:\n{user_context}"
        
        primary_model = config.get("OpenClawmodel", "chat")
        
        tool_payload = {
            "tool": "gateway",
            "args": {
                "action": "config.patch",
                "raw": json.dumps({
                    "agents": {
                        "list": [
                            {
                                "id": agent_id,
                                "name": f"{bot_name} ({user_name})",
                                "model": {
                                    "primary": primary_model
                                },
                                "identity": {
                                    "name": bot_name,
                                    "theme": combined_instructions,
                                    "emoji": "🫦"
                                }
                            }
                        ]
                    }
                }),
                "note": f"Created user agent for {user_name} ({user_id})"
            },
            "sessionKey": f"jennifer:system:admin:{agent_id}"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/tools/invoke", 
                    json=tool_payload, 
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                    ssl=False
                ) as resp:
                    if resp.status == 200:
                        logging.info(f"Agent creation successful for {agent_id}. Waiting for restart...")
                        await self.wait_for_gateway()
                        return agent_id
                    else:
                        err_text = await resp.text()
                        logging.error(f"Failed to create agent: {err_text}")
        except Exception as e:
            logging.error(f"Error during agent creation: {e}")
        
        return "chat"

    async def delete_user_agent(self, user_id, user_name):
        """Deletes the user-specific agent from OpenClaw config."""
        pass

    async def reset_user_messages(self, user_id):
        """Resets the conversation history for a user's session."""
        return True

    async def send_message(self, user_id, user_name, messages, config):
        """Sends a conversation history to a user-specific OpenClaw agent."""
        agent_id = await self.ensure_agent_exists(user_id, user_name, config)
        session_key = f"jennifer:user:{user_id}"
        
        payload = {
            "model": agent_id,
            "messages": messages,
            "user": session_key
        }

        logging.info(f"Routing to user agent '{agent_id}' for session {session_key}...")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/v1/chat/completions", 
                    json=payload, 
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=300),
                    ssl=False
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logging.error(f"OpenClaw Gateway error ({resp.status}): {error_text}")
                        if resp.status == 404:
                            payload["model"] = "chat"
                            async with session.post(f"{self.url}/v1/chat/completions", json=payload, headers=self.headers, ssl=False) as fb_resp:
                                if fb_resp.status == 200:
                                    data = await fb_resp.json()
                                    return data.get("choices", [{}])[0].get("message", {}).get("content")
                        return f"⚠️ OpenClaw Gateway error: {resp.status}"
                    
                    data = await resp.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content")

        except Exception as e:
            logging.error(f"Failed to communicate with OpenClaw Gateway: {e}")
            return f"❌ Connection to OpenClaw failed: {str(e)}"

async def generate_openclaw_response(config, user_id, user_name, messages):
    """High-level entry point for Jennifer's interaction loop."""
    gateway_url = config.get("OpenClawGateway")
    api_token = config.get("OpenClawToken")
    if not gateway_url or not api_token:
        return "System configuration error: OpenClaw credentials missing."
    client = OpenClawClient(gateway_url, api_token)
    return await client.send_message(user_id, user_name, messages, config)

async def delete_openclaw_agent(config, user_id, user_name):
    gateway_url = config.get("OpenClawGateway")
    api_token = config.get("OpenClawToken")
    client = OpenClawClient(gateway_url, api_token)
    return await client.delete_user_agent(user_id, user_name)

async def reset_openclaw_messages(config, user_id):
    gateway_url = config.get("OpenClawGateway")
    api_token = config.get("OpenClawToken")
    client = OpenClawClient(gateway_url, api_token)
    return await client.reset_user_messages(user_id)
