"""
Caching layer for AI responses and metadata.
Reduces latency and costs by avoiding redundant API calls.
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class CacheManager:
    """Asynchronous disk-based cache using SQLite."""

    def __init__(self, db_path: str = "data/cache.db", default_ttl: int = 3600):
        self.db_path = Path(db_path)
        self.default_ttl = default_ttl
        self._initialized = False

    async def initialize(self):
        """Initialize the cache database schema."""
        if self._initialized:
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_expires_at ON cache(expires_at)"
            )
            await db.commit()

        self._initialized = True
        logger.info(f"CacheManager initialized at {self.db_path}")

    def _generate_key(self, input_data: Any) -> str:
        """Generate a unique key for the input data."""
        if isinstance(input_data, (dict, list)):
            key_src = json.dumps(input_data, sort_keys=True)
        else:
            key_src = str(input_data)
        return hashlib.sha256(key_src.encode("utf-8")).hexdigest()

    async def get(self, input_data: Any) -> Optional[Any]:
        """Retrieve a value from cache if it exists and hasn't expired."""
        await self.initialize()
        key = self._generate_key(input_data)
        now = time.time()

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value FROM cache WHERE key = ? AND expires_at > ?",
                (key, now),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    logger.debug(f"Cache HIT for key {key[:8]}")
                    return json.loads(row[0])

        logger.debug(f"Cache MISS for key {key[:8]}")
        return None

    async def set(self, input_data: Any, value: Any, ttl: Optional[int] = None):
        """Store a value in cache with a TTL in seconds."""
        await self.initialize()
        key = self._generate_key(input_data)
        now = time.time()
        expires_at = now + (ttl if ttl is not None else self.default_ttl)
        value_json = json.dumps(value)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO cache (key, value, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, value_json, expires_at, now),
            )
            await db.commit()

    async def cleanup(self):
        """Remove expired entries from the cache."""
        await self.initialize()
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM cache WHERE expires_at < ?", (now,))
            await db.commit()


cache_manager = CacheManager()
