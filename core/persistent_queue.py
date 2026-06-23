"""
Persistent queue implementation using SQLite.
Survives container restarts without losing pending tasks.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite


@dataclass
class Task:
    """Represents a queue task."""
    id: int | None
    type: str  # 'image' or 'message'
    payload: dict
    user_id: int
    created_at: float
    status: str = "pending"  # pending, processing, done, failed
    retries: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "payload": json.dumps(self.payload),
            "user_id": self.user_id,
            "created_at": self.created_at,
            "status": self.status,
            "retries": self.retries,
        }

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Task":
        return cls(
            id=row[0],
            type=row[1],
            payload=json.loads(row[2]),
            user_id=row[3],
            created_at=row[4],
            status=row[5],
            retries=row[6],
        )


class PersistentQueue:
    """
    Async queue with SQLite persistence.
    Uses in-memory queue for speed, backs up to SQLite for durability.
    """

    def __init__(self, db_path: str = "/app/data/queue.db", max_retries: int = 3,
                 max_backoff_seconds: int = 60):
        self.db_path = Path(db_path)
        self.max_retries = max_retries
        self.max_backoff_seconds = max_backoff_seconds
        self._memory_queue: asyncio.Queue[Task] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._initialized = False
        self._worker_task: asyncio.Task | None = None
        self._shutdown = False

    async def initialize(self):
        """Initialize database and recover pending tasks."""
        if self._initialized:
            return

        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            # Performance & Concurrency optimizations
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    retries INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)
            """)
            await db.commit()

        # Recover pending tasks from previous session
        await self._recover_pending()

        self._initialized = True

    async def _recover_pending(self):
        """Load pending tasks from database into memory queue."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at"
            ) as cursor:
                count = 0
                async for row in cursor:
                    task = Task.from_row(row)
                    await self._memory_queue.put(task)
                    count += 1

                if count > 0:
                    print(f"[Queue] Recovered {count} pending tasks from previous session")

    async def put(self, task: Task) -> int:
        """
        Add task to queue.
        Returns task ID.
        """
        if not self._initialized:
            await self.initialize()

        # Save to database first
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO tasks (type, payload, user_id, created_at, status, retries) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task.type, json.dumps(task.payload), task.user_id,
                 time.time(), "pending", 0)
            )
            await db.commit()
            task.id = cursor.lastrowid

        # Add to memory queue
        await self._memory_queue.put(task)
        return task.id

    async def get(self) -> Task:
        """Get next task from queue."""
        if not self._initialized:
            await self.initialize()

        task = await self._memory_queue.get()

        # Mark as processing in database
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE tasks SET status = 'processing' WHERE id = ?",
                (task.id,)
            )
            await db.commit()

        return task

    async def mark_done(self, task: Task):
        """Mark task as completed."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE tasks SET status = 'done' WHERE id = ?",
                (task.id,)
            )
            await db.commit()

        self._memory_queue.task_done()

    async def mark_failed(self, task: Task, error: str):
        """Mark task as failed, with retry logic."""
        task.retries += 1

        if task.retries >= self.max_retries:
            # Permanent failure
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """UPDATE tasks SET status = 'failed', payload = ? WHERE id = ?""",
                    (json.dumps({"error": error, "original": task.payload}), task.id)
                )
                await db.commit()
        else:
            # Retry - put back in queue
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE tasks SET retries = ?, status = 'pending' WHERE id = ?",
                    (task.retries, task.id)
                )
                await db.commit()

            # Re-queue with capped exponential backoff
            delay = min(2 ** task.retries, self.max_backoff_seconds)
            await asyncio.sleep(delay)
            await self._memory_queue.put(task)

        self._memory_queue.task_done()

    def qsize(self) -> int:
        """Return in-memory queue depth.

        NOTE: This only reflects tasks currently loaded in memory.  After a
        restart, recovered tasks are re-added to the memory queue during
        ``initialize()``, so ``qsize()`` will be accurate again once
        initialization completes.  For a definitive count of all pending work
        (including tasks not yet loaded), use ``pending_count()`` instead.
        """
        return self._memory_queue.qsize()

    async def pending_count(self) -> int:
        """Return the true number of pending tasks from the database."""
        async with aiosqlite.connect(self.db_path) as db, db.execute(
            "SELECT COUNT(*) FROM tasks WHERE status IN ('pending', 'processing')"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    def empty(self) -> bool:
        """Check if the in-memory queue is empty (see qsize() caveat)."""
        return self._memory_queue.empty()

    async def get_stats(self) -> dict:
        """Get queue statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            stats = {}
            for status in ["pending", "processing", "done", "failed"]:
                async with db.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status = ?", (status,)
                ) as cursor:
                    row = await cursor.fetchone()
                    stats[status] = row[0]
            return stats

    async def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Remove completed/failed tasks older than specified hours."""
        cutoff = time.time() - (max_age_hours * 3600)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM tasks WHERE status IN ('done', 'failed') AND created_at < ?",
                (cutoff,)
            )
            await db.commit()


class TaskManager:
    """Manages multiple persistent queues for different task types."""

    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.queues: dict[str, PersistentQueue] = {}

    def get_queue(self, name: str) -> PersistentQueue:
        """Get or create named queue."""
        if name not in self.queues:
            db_path = self.data_dir / f"{name}_queue.db"
            self.queues[name] = PersistentQueue(str(db_path))
        return self.queues[name]

    async def initialize_all(self):
        """Initialize all queues."""
        for queue in self.queues.values():
            await queue.initialize()

    async def get_all_stats(self) -> dict:
        """Get stats for all queues."""
        stats = {}
        for name, queue in self.queues.items():
            stats[name] = await queue.get_stats()
        return stats
