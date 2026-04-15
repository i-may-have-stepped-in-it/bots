"""
Redis client for distributed global state.
Handles active user tracking and rate limiting across multiple worker processes.
"""

import os
import logging
from typing import Optional
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class RedisManager:
    """Manages connections to Redis and provides high-level state operations."""
    
    def __init__(self, url: str = "redis://localhost:6379/0"):
        # Allow override via environment variable (useful in Docker Compose)
        self.url = os.getenv("REDIS_URL", url)
        self.client: Optional[redis.Redis] = None

    async def connect(self):
        """Establish connection to Redis with pooling and reliability settings."""
        if not self.client:
            self.client = redis.from_url(
                self.url,
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=5,
                socket_timeout=5,
                health_check_interval=30,
                retry_on_timeout=True
            )
            try:
                await self.client.ping()
                logger.info(f"Connected to Redis at {self.url} (pool_size=20)")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self.client = None

    async def close(self):
        """Close the Redis connection."""
        if self.client:
            await self.client.close()

    async def set_active_user(self, user_id: int, bot_name: str, timeout: int):
        """Mark a user as active in a conversation with a specific bot."""
        if not self.client:
            return
        key = f"active_user:{bot_name}:{user_id}"
        await self.client.setex(key, timeout, "active")

    async def is_user_active(self, user_id: int, bot_name: str) -> bool:
        """Check if a user is currently active."""
        if not self.client:
            return False
        key = f"active_user:{bot_name}:{user_id}"
        return bool(await self.client.exists(key))

    async def remove_active_user(self, user_id: int, bot_name: str):
        """Manually remove a user from the active state."""
        if not self.client:
            return
        key = f"active_user:{bot_name}:{user_id}"
        await self.client.delete(key)

# Global singleton
redis_manager = RedisManager()
