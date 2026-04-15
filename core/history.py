"""
Conversation history management for Jennifer Bot.
Provides persistent storage using SQLite to replace in-memory dictionaries.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class HistoryManager:
    """Manages user conversation histories using SQLite."""

    def __init__(self, db_path: Optional[str] = None, max_history: int = 20):
        self._db_path_override = Path(db_path) if db_path else None
        self.db_path = self._db_path_override or Path("data/history.db")
        self.max_history = max_history
        self._initialized = False

    async def initialize(self, bot_name: Optional[str] = None):
        """Initialize the database schema and migrate legacy data if provided."""
        if self._initialized:
            return

        if bot_name and not self._db_path_override:
            self.db_path = Path(f"data/{bot_name.lower()}_history.db")

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_id ON messages(user_id)
                """
            )
            await db.commit()

            if bot_name:
                await self._migrate_from_json(db, bot_name)

        self._initialized = True
        logger.info(f"HistoryManager initialized at {self.db_path}")

    async def _migrate_from_json(self, db: aiosqlite.Connection, bot_name: str):
        """Check for and migrate data from legacy JSON history file."""
        async with db.execute("SELECT COUNT(*) FROM messages") as cursor:
            count = await cursor.fetchone()
            if count and count[0] > 0:
                return

        legacy_path = Path(f"config/{bot_name}_message_histories.json")
        if not legacy_path.exists():
            legacy_path = Path(f"{bot_name}_message_histories.json")

        if legacy_path.exists():
            try:
                logger.info(f"Migrating legacy history from {legacy_path}")
                with open(legacy_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if not isinstance(data, dict):
                    return

                for user_id, messages in data.items():
                    if not isinstance(messages, list):
                        continue
                    for msg in messages:
                        await db.execute(
                            "INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                            (
                                user_id,
                                msg.get("role", "user"),
                                msg.get("content", ""),
                                msg.get("timestamp", ""),
                            ),
                        )
                await db.commit()
                logger.info(f"Successfully migrated history for {len(data)} users")

                legacy_path.rename(legacy_path.with_suffix(".json.migrated"))
            except Exception as e:
                logger.error(f"Failed to migrate legacy history: {e}")

    async def get_history(self, user_id: str) -> List[Dict[str, str]]:
        """Get the latest conversation history for a user."""
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT role, content FROM (
                    SELECT role, content, id
                    FROM messages
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id ASC
                """,
                (user_id, self.max_history),
            ) as cursor:
                rows = await cursor.fetchall()
                return [{"role": row["role"], "content": row["content"]} for row in rows]

    async def add_message(self, user_id: str, role: str, content: str):
        """Add a message to a user's history."""
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO messages (user_id, role, content)
                VALUES (?, ?, ?)
                """,
                (user_id, role, content),
            )
            await db.commit()

            await db.execute(
                """
                DELETE FROM messages
                WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM messages
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (user_id, user_id, self.max_history * 2),
            )
            await db.commit()

    async def clear_history(self, user_id: str):
        """Clear all history for a user."""
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
            await db.commit()

    async def get_all_users_count(self) -> int:
        """Get the count of unique users with history."""
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(DISTINCT user_id) FROM messages") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0


history_manager = HistoryManager()


async def get_history_manager() -> HistoryManager:
    """Get the global history manager instance."""
    await history_manager.initialize()
    return history_manager
