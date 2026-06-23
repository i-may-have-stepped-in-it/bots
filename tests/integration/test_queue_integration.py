"""
Integration tests for persistent queue functionality.
"""

import asyncio
from pathlib import Path

import pytest

from core.persistent_queue import PersistentQueue, Task, TaskManager


@pytest.mark.integration
@pytest.mark.asyncio
class TestQueueIntegration:
    """Integration tests for persistent queues."""

    async def test_queue_persists_across_instances(self, temp_data_dir: Path):
        """Test that tasks persist when queue is recreated."""
        db_path = temp_data_dir / "persistent.db"

        # First instance - add tasks
        queue1 = PersistentQueue(str(db_path))
        await queue1.initialize()

        for i in range(5):
            task = Task(
                id=None,
                type="test",
                payload={"idx": i},
                user_id=100 + i,
                created_at=asyncio.get_event_loop().time(),
            )
            await queue1.put(task)

        # Simulate restart - create new instance
        queue2 = PersistentQueue(str(db_path))
        await queue2.initialize()

        # Should recover all pending tasks
        assert queue2.qsize() == 5

        # Process all tasks
        processed = []
        while not queue2.empty():
            task = await queue2.get()
            processed.append(task.payload["idx"])
            await queue2.mark_done(task)

        assert sorted(processed) == [0, 1, 2, 3, 4]

    async def test_task_manager_multiple_queues(self, temp_data_dir: Path):
        """Test TaskManager managing multiple queues."""
        manager = TaskManager(str(temp_data_dir))

        # Get multiple queues
        image_queue = manager.get_queue("image")
        message_queue = manager.get_queue("message")
        music_queue = manager.get_queue("music")

        await manager.initialize_all()

        # Add tasks to each
        await image_queue.put(Task(None, "image", {"prompt": "cat"}, 1, asyncio.get_event_loop().time()))
        await message_queue.put(Task(None, "message", {"text": "hello"}, 2, asyncio.get_event_loop().time()))
        await music_queue.put(Task(None, "music", {"url": "song.mp3"}, 3, asyncio.get_event_loop().time()))

        # Get stats
        stats = await manager.get_all_stats()

        assert stats["image"]["pending"] == 1
        assert stats["message"]["pending"] == 1
        assert stats["music"]["pending"] == 1

    async def test_concurrent_producers_consumers(self, temp_data_dir: Path):
        """Test multiple producers and consumers working concurrently."""
        db_path = temp_data_dir / "concurrent.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()

        num_producers = 3
        num_consumers = 3
        tasks_per_producer = 10

        produced = asyncio.Queue()
        consumed = asyncio.Queue()

        async def producer(producer_id):
            for i in range(tasks_per_producer):
                task = Task(
                    id=None,
                    type="test",
                    payload={"producer": producer_id, "task": i},
                    user_id=producer_id,
                    created_at=asyncio.get_event_loop().time(),
                )
                await queue.put(task)
                await produced.put((producer_id, i))

        async def consumer():
            while True:
                try:
                    task = await asyncio.wait_for(queue.get(), timeout=2.0)
                    await consumed.put(task.payload)
                    await queue.mark_done(task)
                except asyncio.TimeoutError:
                    break

        # Start producers and consumers
        producers = [asyncio.create_task(producer(i)) for i in range(num_producers)]
        consumers = [asyncio.create_task(consumer()) for _ in range(num_consumers)]

        # Wait for producers to finish
        await asyncio.gather(*producers)

        # Wait a bit for consumers to process
        await asyncio.sleep(0.5)

        # Cancel consumers
        for c in consumers:
            c.cancel()

        # Verify all tasks were consumed
        assert produced.qsize() == num_producers * tasks_per_producer
        assert consumed.qsize() == num_producers * tasks_per_producer

    async def test_queue_recovery_with_mixed_status(self, temp_data_dir: Path):
        """Test recovery when some tasks are done, some pending."""
        db_path = temp_data_dir / "mixed.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()

        # Add tasks
        tasks = []
        for i in range(10):
            task = Task(
                id=None,
                type="test",
                payload={"idx": i},
                user_id=1,
                created_at=asyncio.get_event_loop().time(),
            )
            task_id = await queue.put(task)
            tasks.append((task_id, i))

        # Complete some tasks
        for i in range(5):
            task = await queue.get()
            await queue.mark_done(task)

        # Create new instance
        queue2 = PersistentQueue(str(db_path))
        await queue2.initialize()

        # Should only recover pending tasks (5 remaining)
        assert queue2.qsize() == 5

    async def test_queue_stats_accuracy(self, temp_data_dir: Path):
        """Test that queue stats are accurate."""
        db_path = temp_data_dir / "stats.db"
        queue = PersistentQueue(str(db_path))
        await queue.initialize()

        # Initial stats
        stats = await queue.get_stats()
        assert stats == {"pending": 0, "processing": 0, "done": 0, "failed": 0}

        # Add tasks
        for _ in range(10):
            await queue.put(Task(None, "test", {}, 1, asyncio.get_event_loop().time()))

        stats = await queue.get_stats()
        assert stats["pending"] == 10

        # Process some
        for _ in range(3):
            task = await queue.get()
            await queue.mark_done(task)

        # Fail some
        for _ in range(2):
            task = await queue.get()
            await queue.mark_failed(task, "error")

        stats = await queue.get_stats()
        assert stats["pending"] == 5  # Remaining
        assert stats["processing"] == 0  # All processed
        assert stats["done"] == 3
        assert stats["failed"] == 2
