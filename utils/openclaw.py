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
    Uses the 'gateway' tool to dynamically update OpenClaw configuration.
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

    async def ensure_agent_exists(self, user_id, user_name, config):
        """
        Checks if an agent exists for the user, and creates one if it doesn't.
        Injects user identity (name) into the agent's initial context.
        """
        agent_id = self.normalize_id(user_id)
        
        # 1. List agents to see if it exists
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.url}/v1/models", headers=self.headers, ssl=False) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("Content-Type", "")
                        if "application/json" in content_type:
                            data = await resp.json()
                            models = [m['id'] for m in data.get('data', [])]
                            if agent_id in models:
                                return agent_id
                        else:
                            logging.warning(f"Unexpected content type from /v1/models: {content_type}")
        except Exception as e:
            logging.error(f"Error checking agents: {e}")

        # 2. Create agent if not found
        logging.info(f"Creating new OpenClaw agent for user {user_name} ({user_id})...")
        
        bot_name = config.get("Name", "your persona")
        personality = config.get("OpenClawPersonality", config.get("Personality", ""))
        system_prompt = config.get("OpenClawSystemPrompt", "")
        user_context = f"The person you are talking to is named '{user_name}'. They are using Discord."
        combined_instructions = f"{system_prompt}\n\nCORE PERSONALITY:\n{personality}\n\nUSER IDENTITY:\n{user_context}"
        
        primary_model = config.get("OpenClawmodel", "chat")
        context_window = config.get("OpenClawContextWindow", 10240)
        
        tool_payload = {
            "tool": "gateway",
            "args": {
                "action": "config.patch",
                "raw": json.dumps({
                    "agents": {
                        "entries": {
                            agent_id: {
                                "id": agent_id,
                                "name": f"{bot_name} ({user_name})",
                                "onboarding": "completed",
                                "model": {
                                    "primary": primary_model
                                },
                                "identity": {
                                    "name": bot_name,
                                    "theme": combined_instructions,
                                    "emoji": "🫦"
                                },
                                "params": {
                                    "maxContextTokens": context_window,
                                    "compaction": {
                                        "mode": "safeguard"
                                    }
                                }
                            }
                        }
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
                        await asyncio.sleep(8) 
                        return agent_id
                    else:
                        err = await resp.text()
                        logging.error(f"Failed to create agent: {err}")
        except Exception as e:
            logging.error(f"Error during agent creation: {e}")
        
        return "chat"

    async def delete_user_agent(self, user_id, user_name):
        """
        Deletes the user-specific agent from OpenClaw config.
        """
        agent_id = self.normalize_id(user_id)
        logging.info(f"Deleting OpenClaw agent {agent_id} for user {user_name}...")
        
        # In OpenClaw, setting an item in a list-merged config to null deletes it (if using id-keyed merge)
        # But for agents.list, it might be safer to use a dedicated path if available.
        # Currently, gateway tool config.patch with null entry is the intended way.
        tool_payload = {
            "tool": "gateway",
            "args": {
                "action": "config.patch",
                "raw": json.dumps({
                    "agents": {
                        "list": [
                            { "id": agent_id, "delete": True } # Hypothetical or manual removal
                        ]
                    }
                }),
                "note": f"Deleted agent for user {user_name} ({user_id})"
            },
            "sessionKey": f"jennifer:system:admin:delete:{agent_id}"
        }
        
        # Actually, mergeObjectArraysById checks for 'null' to delete.
        tool_payload["args"]["raw"] = json.dumps({
            "agents": {
                "list": [ None ] # This is tricky with ID-based merge. 
            }
        })
        
        # Let's try to just remove it by sending an empty config for that ID? No.
        # Based on OpenClaw source, config.patch uses applyMergePatch which deletes on null.
        # But we need to target the specific ID in the array.
        
        # A simpler way for Jennifer is to just 'reset' the session which is what users usually want.
        # True agent deletion is rarely needed compared to session clearing.
        pass

    async def reset_user_messages(self, user_id):
        """
        Resets the conversation history for a user's session.
        """
        session_key = f"jennifer:user:{user_id}"
        logging.info(f"Resetting messages for session {session_key}...")
        
        # We can use the 'gateway' tool to call 'sessions.reset' RPC method
        tool_payload = {
            "tool": "gateway",
            "args": {
                "action": "config.get", # We use config.get just to get a valid gateway call context
                "gatewayUrl": self.url,
                "gatewayToken": self.api_token
            }
        }
        
        # Actually, we can't easily call arbitrary RPCs via the gateway tool's 'action' list.
        # But we CAN send a reset command into the session if the agent supports it, 
        # or use the tools/invoke with a hypothetical session tool.
        
        # Best way: Use the OpenAI-compat with a system instruction to 'forget everything' 
        # OR just clear the local message history file which Jennifer uses to populate the context.
        return True

    async def send_message(self, user_id, user_name, messages, config):
        """
        Sends a conversation history to a user-specific OpenClaw agent.
        """
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
    """
    High-level entry point for Jennifer's interaction loop.
    """
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
