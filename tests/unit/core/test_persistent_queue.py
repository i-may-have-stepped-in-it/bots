"""
Unit tests for core/persistent_queue.py - SQLite-backed persistent queues.
"""

import asyncio
import json
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core.persistent_queue import Task, PersistentQueue, TaskManager


# =============================================================================
# Task Tests
# =============================================================================

class TestTask:
    """Tests for the Task dataclass."""

    def test_task_creation(self):
        """Test creating a Task instance."""
        task = Task(
            id=None,
            type="image",
            payload={"prompt": "test"},
            user_id=12345,
            created_at=1234567890.0,
        )
        
        assert task.id is None
        assert task.type == "image"
        assert task.payload == {"prompt": "test"}
        assert task.user_id == 12345
        assert task.created_at == 1234567890.0
        assert task.status == "pending"
        assert task.retries == 0

    def test_task_to_dict(self):
        """Test converting Task to dictionary."""
        task = Task(
            id=1,
            type="message",
            payload={"content": "hello"},
            user_id=12345,
            created_at=1234567890.0,
            status="processing",
            retries=1,
        )
        
        task_dict = task.to_dict()
        
        assert task_dict["id"] == 1
        assert task_dict["type"] == "message"
        assert json.loads(task_dict["payload"]) == {"content": "hello"}
        assert task_dict["user_id"] == 12345
        assert task_dict["created_at"] == 1234567890.0
        assert task_dict["status"] == "processing"
        assert task_dict["retries"] == 1

    def test_task_from_row(self):
        """Test creating Task from database row."""
        # Mock a database row
        class MockRow:
            def __getitem__(self, idx):
                data = [
                    1,  # id
                    "image",  # type
                    '{"prompt": "test"}',  # payload (JSON string)
                    12345,  # user_id
                    1234567890.0,  # created_at
                    "pending",  # status
                    0,  # retries
                ]
                return data[idx]
        
        row = MockRow()
        task = Task.from_row(row)
        
        assert task.id == 1
        assert task.type == "image"
        assert task.payload == {"prompt": "test"}
        assert task.user_id == 12345
        assert task.status == "pending"


# =============================================================================
# PersistentQueue Tests
# =============================================================================

@pytest.mark.asyncio
class TestPersistentQueue:
    """Tests for the PersistentQueue class."""

    async def test_initialization(self, temp_data_dir: Path):
        """Test queue initialization creates database."""
        db_path = temp_data_dir / "test_init.db"
        queue = PersistentQueue(str(db_path), max_retries=3)
        
        await queue.initialize()
        
        assert db_path.exists()
        assert queue._initialized is True

    async def test_initialize_idempotent(self, temp_data_dir: Path):
        """Test that initialize is idempotent."""
        db_path = temp_data_dir / "test_idempotent.db"
        queue = PersistentQueue(str(db_path))
        
        await queue.initialize()
        await queue.initialize()  # Should not fail
        
        assert queue._initialized is True

    async def test_put_and_get(self, temp_data_dir: Path):
        """Test putting and getting tasks."""
        db_path = temp_data_dir / "test_put_get.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        task = Task(
            id=None,
            type="test",
            payload={"data": "value"},
            user_id=12345,
            created_at=asyncio.get_event_loop().time(),
        )
        
        task_id = await queue.put(task)
        
        assert task_id is not None
        assert task.id == task_id
        
        retrieved = await queue.get()
        
        assert retrieved.id == task_id
        assert retrieved.type == "test"
        assert retrieved.payload == {"data": "value"}
        assert retrieved.status == "processing"  # Should be marked as processing

    async def test_mark_done(self, temp_data_dir: Path):
        """Test marking a task as done."""
        db_path = temp_data_dir / "test_done.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        task = Task(
            id=None,
            type="test",
            payload={},
            user_id=12345,
            created_at=asyncio.get_event_loop().time(),
        )
        
        await queue.put(task)
        retrieved = await queue.get()
        
        await queue.mark_done(retrieved)
        
        # Check in database
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT status FROM tasks WHERE id = ?", (retrieved.id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row[0] == "done"

    async def test_mark_failed_with_retry(self, temp_data_dir: Path):
        """Test marking a task as failed with retry."""
        db_path = temp_data_dir / "test_fail.db"
        queue = PersistentQueue(str(db_path), max_retries=3)
        await queue.initialize()
        
        task = Task(
            id=None,
            type="test",
            payload={},
            user_id=12345,
            created_at=asyncio.get_event_loop().time(),
        )
        
        await queue.put(task)
        retrieved = await queue.get()
        
        # Mark as failed first time
        await queue.mark_failed(retrieved, "Test error")
        
        # Should be re-queued
        assert retrieved.retries == 1
        
        # Get again - should be same task
        retry_task = await queue.get()
        assert retry_task.id == retrieved.id

    async def test_mark_failed_permanent(self, temp_data_dir: Path):
        """Test permanent failure after max retries."""
        db_path = temp_data_dir / "test_permanent_fail.db"
        queue = PersistentQueue(str(db_path), max_retries=2)
        await queue.initialize()
        
        task = Task(
            id=None,
            type="test",
            payload={"original": "data"},
            user_id=12345,
            created_at=asyncio.get_event_loop().time(),
        )
        
        await queue.put(task)
        
        # Fail twice (max retries)
        for _ in range(2):
            retrieved = await queue.get()
            await queue.mark_failed(retrieved, f"Error {_}")
        
        # Check in database - should be failed
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT status, payload FROM tasks WHERE id = ?", (task.id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row[0] == "failed"
                payload_data = json.loads(row[1])
                assert "error" in payload_data

    async def test_queue_size(self, temp_data_dir: Path):
        """Test getting queue size."""
        db_path = temp_data_dir / "test_size.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        assert queue.qsize() == 0
        assert queue.empty() is True
        
        for i in range(3):
            task = Task(
                id=None,
                type="test",
                payload={"idx": i},
                user_id=12345,
                created_at=asyncio.get_event_loop().time(),
            )
            await queue.put(task)
        
        assert queue.qsize() == 3
        assert queue.empty() is False

    async def test_get_stats(self, temp_data_dir: Path):
        """Test getting queue statistics."""
        db_path = temp_data_dir / "test_stats.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        # Add and complete some tasks
        for i in range(3):
            task = Task(
                id=None,
                type="test",
                payload={},
                user_id=12345,
                created_at=asyncio.get_event_loop().time(),
            )
            await queue.put(task)
            retrieved = await queue.get()
            if i < 2:
                await queue.mark_done(retrieved)
            else:
                await queue.mark_failed(retrieved, "error")
        
        stats = await queue.get_stats()
        
        assert stats["done"] == 2
        assert stats["failed"] == 1
        assert stats["pending"] == 0
        assert stats["processing"] == 0

    async def test_cleanup_old_tasks(self, temp_data_dir: Path):
        """Test cleaning up old completed tasks."""
        db_path = temp_data_dir / "test_cleanup.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        # Manually insert old task
        import aiosqlite
        import time
        old_time = time.time() - (48 * 3600)  # 48 hours ago
        
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """INSERT INTO tasks (type, payload, user_id, created_at, status, retries)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("test", "{}", 12345, old_time, "done", 0)
            )
            await db.commit()
        
        # Cleanup old tasks (older than 24 hours)
        await queue.cleanup_old_tasks(max_age_hours=24)
        
        # Should be deleted
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM tasks") as cursor:
                row = await cursor.fetchone()
                assert row[0] == 0

    async def test_recovery_on_initialize(self, temp_data_dir: Path):
        """Test recovery of pending tasks on initialization."""
        db_path = temp_data_dir / "test_recovery.db"
        
        # First, create some pending tasks
        queue1 = PersistentQueue(str(db_path))
        await queue1.initialize()
        
        for i in range(3):
            task = Task(
                id=None,
                type="test",
                payload={"idx": i},
                user_id=12345,
                created_at=asyncio.get_event_loop().time(),
            )
            await queue1.put(task)
        
        # Create new queue instance (simulating restart)
        queue2 = PersistentQueue(str(db_path))
        await queue2.initialize()  # Should recover pending tasks
        
        # Should have recovered tasks
        assert queue2.qsize() == 3

    async def test_concurrent_operations(self, temp_data_dir: Path):
        """Test concurrent put and get operations."""
        db_path = temp_data_dir / "test_concurrent.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        results = []
        
        async def producer(start_idx):
            for i in range(5):
                task = Task(
                    id=None,
                    type="test",
                    payload={"idx": start_idx + i},
                    user_id=12345,
                    created_at=asyncio.get_event_loop().time(),
                )
                await queue.put(task)
        
        async def consumer():
            for _ in range(5):
                task = await queue.get()
                results.append(task.payload["idx"])
                await queue.mark_done(task)
        
        # Run producers and consumers concurrently
        await asyncio.gather(
            producer(0),
            producer(100),
            consumer(),
            consumer(),
        )
        
        assert len(results) == 10

    async def test_empty_queue_get_blocks(self, temp_data_dir: Path):
        """Test that getting from empty queue blocks."""
        db_path = temp_data_dir / "test_blocks.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        # Start a task that will get from queue
        async def delayed_put():
            await asyncio.sleep(0.1)
            task = Task(
                id=None,
                type="test",
                payload={"data": "delayed"},
                user_id=12345,
                created_at=asyncio.get_event_loop().time(),
            )
            await queue.put(task)
        
        # Run both concurrently
        asyncio.create_task(delayed_put())
        
        # This should block until put is called
        retrieved = await queue.get()
        
        assert retrieved.payload["data"] == "delayed"


# =============================================================================
# TaskManager Tests
# =============================================================================

@pytest.mark.asyncio
class TestTaskManager:
    """Tests for the TaskManager class."""

    async def test_get_queue_creates_new(self, temp_data_dir: Path):
        """Test getting a queue creates a new one if not exists."""
        manager = TaskManager(str(temp_data_dir))
        
        queue = manager.get_queue("test")
        
        assert "test" in manager.queues
        assert queue is manager.queues["test"]

    async def test_get_queue_returns_existing(self, temp_data_dir: Path):
        """Test getting a queue returns existing one."""
        manager = TaskManager(str(temp_data_dir))
        
        queue1 = manager.get_queue("test")
        queue2 = manager.get_queue("test")
        
        assert queue1 is queue2

    async def test_multiple_queues(self, temp_data_dir: Path):
        """Test managing multiple queues."""
        manager = TaskManager(str(temp_data_dir))
        
        image_queue = manager.get_queue("image")
        message_queue = manager.get_queue("message")
        
        assert image_queue is not message_queue
        assert len(manager.queues) == 2

    async def test_initialize_all(self, temp_data_dir: Path):
        """Test initializing all queues."""
        manager = TaskManager(str(temp_data_dir))
        
        manager.get_queue("q1")
        manager.get_queue("q2")
        
        await manager.initialize_all()
        
        assert manager.queues["q1"]._initialized is True
        assert manager.queues["q2"]._initialized is True

    async def test_get_all_stats(self, temp_data_dir: Path):
        """Test getting stats for all queues."""
        manager = TaskManager(str(temp_data_dir))
        
        image_queue = manager.get_queue("image")
        message_queue = manager.get_queue("message")
        
        await manager.initialize_all()
        
        # Add a task to one queue
        task = Task(
            id=None,
            type="test",
            payload={},
            user_id=12345,
            created_at=asyncio.get_event_loop().time(),
        )
        await image_queue.put(task)
        
        stats = await manager.get_all_stats()
        
        assert "image" in stats
        assert "message" in stats
        assert stats["image"]["pending"] == 1
        assert stats["message"]["pending"] == 0


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

@pytest.mark.asyncio
class TestQueueEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_large_payload(self, temp_data_dir: Path):
        """Test handling large payloads."""
        db_path = temp_data_dir / "test_large.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        large_payload = {"data": "x" * 100000}
        
        task = Task(
            id=None,
            type="test",
            payload=large_payload,
            user_id=12345,
            created_at=asyncio.get_event_loop().time(),
        )
        
        task_id = await queue.put(task)
        retrieved = await queue.get()
        
        assert retrieved.payload == large_payload

    async def test_unicode_payload(self, temp_data_dir: Path):
        """Test handling unicode in payloads."""
        db_path = temp_data_dir / "test_unicode.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        unicode_payload = {
            "chinese": "你好世界",
            "emoji": "🎉🎨🤖",
            "japanese": "こんにちは",
            "korean": "안녕하세요",
            "arabic": "مرحبا",
        }
        
        task = Task(
            id=None,
            type="test",
            payload=unicode_payload,
            user_id=12345,
            created_at=asyncio.get_event_loop().time(),
        )
        
        await queue.put(task)
        retrieved = await queue.get()
        
        assert retrieved.payload == unicode_payload

    async def test_special_characters_in_payload(self, temp_data_dir: Path):
        """Test handling special characters that might break SQL."""
        db_path = temp_data_dir / "test_special.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        dangerous_payload = {
            "sql": "'; DROP TABLE tasks; --",
            "quotes": '"double" and \'single\' quotes',
            "newlines": "line1\nline2\r\nline3",
            "tabs": "col1\tcol2\tcol3",
        }
        
        task = Task(
            id=None,
            type="test",
            payload=dangerous_payload,
            user_id=12345,
            created_at=asyncio.get_event_loop().time(),
        )
        
        await queue.put(task)
        retrieved = await queue.get()
        await queue.mark_done(retrieved)
        
        # Verify table still exists
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None

    async def test_very_long_type_name(self, temp_data_dir: Path):
        """Test handling very long type names."""
        db_path = temp_data_dir / "test_long_type.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        long_type = "x" * 1000
        
        task = Task(
            id=None,
            type=long_type,
            payload={},
            user_id=12345,
            created_at=asyncio.get_event_loop().time(),
        )
        
        await queue.put(task)
        retrieved = await queue.get()
        
        assert retrieved.type == long_type

    async def test_negative_user_id(self, temp_data_dir: Path):
        """Test handling negative user IDs (Discord system users)."""
        db_path = temp_data_dir / "test_negative.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        task = Task(
            id=None,
            type="test",
            payload={},
            user_id=-1,  # System webhook
            created_at=asyncio.get_event_loop().time(),
        )
        
        task_id = await queue.put(task)
        retrieved = await queue.get()
        
        assert retrieved.user_id == -1

    async def test_zero_timestamp(self, temp_data_dir: Path):
        """Test handling zero timestamp."""
        db_path = temp_data_dir / "test_zero_time.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        task = Task(
            id=None,
            type="test",
            payload={},
            user_id=12345,
            created_at=0.0,  # Unix epoch
        )
        
        await queue.put(task)
        retrieved = await queue.get()
        
        assert retrieved.created_at == 0.0

    async def test_nested_payload(self, temp_data_dir: Path):
        """Test handling deeply nested payload."""
        db_path = temp_data_dir / "test_nested.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        nested_payload = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "level5": "deep value"
                        }
                    }
                }
            }
        }
        
        task = Task(
            id=None,
            type="test",
            payload=nested_payload,
            user_id=12345,
            created_at=asyncio.get_event_loop().time(),
        )
        
        await queue.put(task)
        retrieved = await queue.get()
        
        assert retrieved.payload["level1"]["level2"]["level3"]["level4"]["level5"] == "deep value"

    async def test_list_payload(self, temp_data_dir: Path):
        """Test handling list payload."""
        db_path = temp_data_dir / "test_list.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()
        
        list_payload = [1, 2, 3, "four", "five", {"nested": "dict"}]
        
        task = Task(
            id=None,
            type="test",
            payload={"items": list_payload},
            user_id=12345,
            created_at=asyncio.get_event_loop().time(),
        )
        
        await queue.put(task)
        retrieved = await queue.get()
        
        assert retrieved.payload["items"] == list_payload
