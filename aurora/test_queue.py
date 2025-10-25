"""Unit tests for Aurora message queue system."""

import asyncio

import pytest

from aurora.utils.queue import Event, EventQueue, MessageQueue


class TestEventQueue:
    """Tests for EventQueue class."""

    @pytest.mark.asyncio
    async def test_event_queue_initialization(self):
        """Test event queue initializes with correct defaults."""
        queue = EventQueue(default_rate_limit=5.0)
        stats = queue.get_stats()
        assert stats == {}

    @pytest.mark.asyncio
    async def test_serialize_deserialize_event_queue(self, tmp_path):
        """Test serialization and deserialization of the event queue."""
        path = tmp_path / "test_event_queue.pkl"
        queue = EventQueue(default_rate_limit=3.0)
        event = {
            "event_type": "test_event",
            "channel_id": 123456,
            "guild_id": 654321,
            "details": "Some event details",
        }
        event = Event.from_dict(event)
        await queue.enqueue(event)

        with path.open("wb") as f:
            queue.to_file(f.name)

        loaded_queue = EventQueue.from_file(path)
        stats = loaded_queue.get_stats()
        assert stats["test_event"]["queue_size"] == 1
        assert stats["test_event"]["rate_limit_seconds"] == 3.0

        dequeued_event = await loaded_queue.dequeue("test_event")
        assert dequeued_event == event


class TestMessageQueue:
    """Tests for MessageQueue class."""

    @pytest.mark.asyncio
    async def test_queue_initialization(self):
        """Test queue initializes with correct defaults."""
        queue = MessageQueue(max_size=50, rate_limit_seconds=2.0)

        stats = queue.get_stats()
        assert stats["queue_size"] == 0
        assert stats["max_size"] == 50
        assert stats["rate_limit_seconds"] == 2.0

    @pytest.mark.asyncio
    async def test_serialize_deserialize(self, tmp_path):
        """Test serialization and deserialization of the queue."""
        path = tmp_path / "test_queue.pkl"
        queue = MessageQueue(max_size=20)
        event = {
            "message_id": "abc123",
            "channel_id": 123456,
            "guild_id": 654321,
            "content": "Hello, World!",
        }
        await queue.enqueue(event)

        with path.open("wb") as f:
            queue.to_file(f.name)

        loaded_queue = MessageQueue.from_file(path)
        stats = loaded_queue.get_stats()
        assert stats["queue_size"] == 1
        assert stats["max_size"] == 20
        assert stats["rate_limit_seconds"] == 2.0

        dequeued_event = await loaded_queue.dequeue()
        assert dequeued_event == event

    @pytest.mark.asyncio
    async def test_enqueue_single_event(self):
        """Test enqueueing a single event."""
        queue = MessageQueue(max_size=10)

        event = {
            "message_id": "123456",
            "channel_id": 987654,
            "guild_id": 111222,
            "content": "Test message",
        }

        result = await queue.enqueue(event)

        assert result is True
        stats = queue.get_stats()
        assert stats["queue_size"] == 1

    @pytest.mark.asyncio
    async def test_enqueue_duplicate_prevention(self):
        """Test that duplicate messages are not enqueued."""
        queue = MessageQueue(max_size=10)

        event1 = {
            "message_id": "123456",
            "channel_id": 987654,
            "guild_id": 111222,
            "content": "Test message",
        }

        event2 = {
            "message_id": "123456",  # Same ID
            "channel_id": 987654,
            "guild_id": 111222,
            "content": "Different content",
        }

        result1 = await queue.enqueue(event1)
        result2 = await queue.enqueue(event2)

        # Both return True (second is handled as duplicate)
        assert result1 is True
        assert result2 is True  # Returns True even though skipped
        stats = queue.get_stats()
        # Only one should be in queue (duplicate was skipped)
        assert stats["queue_size"] == 1

    @pytest.mark.asyncio
    async def test_queue_full_behavior(self):
        """Test behavior when queue is full."""
        queue = MessageQueue(max_size=2)

        event1 = {"message_id": "111", "channel_id": 1, "guild_id": 1}
        event2 = {"message_id": "222", "channel_id": 1, "guild_id": 1}
        event3 = {"message_id": "333", "channel_id": 1, "guild_id": 1}

        await queue.enqueue(event1)
        await queue.enqueue(event2)

        # Third event should fail (queue full)
        result = await queue.enqueue(event3)

        assert result is False
        stats = queue.get_stats()
        assert stats["queue_size"] == 2

    @pytest.mark.asyncio
    async def test_dequeue_single_event(self):
        """Test dequeuing a single event."""
        queue = MessageQueue(max_size=10)

        event = {
            "message_id": "123456",
            "channel_id": 987654,
            "guild_id": 111222,
            "content": "Test message",
        }

        await queue.enqueue(event)
        dequeued = await queue.dequeue()

        assert dequeued == event
        stats = queue.get_stats()
        assert stats["queue_size"] == 0

    @pytest.mark.asyncio
    async def test_dequeue_fifo_order(self):
        """Test that queue maintains FIFO order."""
        queue = MessageQueue(max_size=10)

        events = [
            {"message_id": "111", "channel_id": 1, "guild_id": 1},
            {"message_id": "222", "channel_id": 1, "guild_id": 1},
            {"message_id": "333", "channel_id": 1, "guild_id": 1},
        ]

        for event in events:
            await queue.enqueue(event)

        # Dequeue should return in same order
        dequeued1 = await queue.dequeue()
        dequeued2 = await queue.dequeue()
        dequeued3 = await queue.dequeue()

        assert dequeued1["message_id"] == "111"
        assert dequeued2["message_id"] == "222"
        assert dequeued3["message_id"] == "333"

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue(self):
        """Test dequeuing from empty queue (should block)."""
        queue = MessageQueue(max_size=10)

        # Start dequeue in background (will block)
        dequeue_task = asyncio.create_task(queue.dequeue())

        # Wait a bit to ensure it's blocking
        await asyncio.sleep(0.1)

        # Verify task is still pending
        assert not dequeue_task.done()

        # Now enqueue an event to unblock
        event = {"message_id": "123", "channel_id": 1, "guild_id": 1}
        await queue.enqueue(event)

        # Dequeue should complete
        dequeued = await asyncio.wait_for(dequeue_task, timeout=1.0)
        assert dequeued == event

    @pytest.mark.asyncio
    async def test_can_process_rate_limiting(self):
        """Test rate limiting logic."""
        queue = MessageQueue(max_size=10, rate_limit_seconds=1.0)

        channel_id = 987654

        # First check should allow processing
        assert queue.can_process(channel_id) is True

        # Mark as processed
        queue.mark_processed(channel_id)

        # Immediate check should deny (rate limited)
        assert queue.can_process(channel_id) is False

        # Wait for rate limit to expire
        await asyncio.sleep(1.1)

        # Should allow processing again
        assert queue.can_process(channel_id) is True

    @pytest.mark.asyncio
    async def test_mark_processed_updates_timestamp(self):
        """Test that mark_processed updates the timestamp."""
        queue = MessageQueue(max_size=10, rate_limit_seconds=1.0)

        channel_id = 987654

        # First processing
        queue.mark_processed(channel_id)

        # Wait a bit but not enough to expire rate limit
        await asyncio.sleep(0.5)

        # Mark processed again (resets timer)
        queue.mark_processed(channel_id)

        # Wait remaining time from first check
        await asyncio.sleep(0.6)

        # Should still be rate limited (because we reset timer)
        assert queue.can_process(channel_id) is False

    @pytest.mark.asyncio
    async def test_different_channels_independent_rate_limits(self):
        """Test that different channels have independent rate limits."""
        queue = MessageQueue(max_size=10, rate_limit_seconds=1.0)

        channel1 = 111111
        channel2 = 222222

        # Process channel1
        queue.mark_processed(channel1)

        # Channel1 should be rate limited
        assert queue.can_process(channel1) is False

        # Channel2 should NOT be rate limited
        assert queue.can_process(channel2) is True

    @pytest.mark.asyncio
    async def test_processed_message_ids_set_management(self):
        """Test that processed_message_ids set doesn't grow unbounded."""
        queue = MessageQueue(max_size=10)

        # Enqueue many unique messages
        for i in range(1500):  # Exceeds max_processed_ids (1000)
            event = {"message_id": str(i), "channel_id": 1, "guild_id": 1}
            await queue.enqueue(event)
            await queue.dequeue()  # Clear queue to make room

        # Set should be limited to 1000
        assert len(queue.processed_message_ids) == 1000

    @pytest.mark.asyncio
    async def test_get_stats_accuracy(self):
        """Test that get_stats returns accurate information."""
        queue = MessageQueue(max_size=10)

        # Add some events
        for i in range(3):
            event = {"message_id": str(i), "channel_id": 1, "guild_id": 1}
            await queue.enqueue(event)

        # Process one channel
        queue.mark_processed(999)

        stats = queue.get_stats()

        assert stats["queue_size"] == 3
        assert stats["max_size"] == 10
        assert stats["tracked_message_ids"] == 3
        assert stats["tracked_channels"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_enqueue(self):
        """Test concurrent enqueue operations."""
        queue = MessageQueue(max_size=100)

        async def enqueue_batch(start, count):
            for i in range(start, start + count):
                event = {"message_id": str(i), "channel_id": 1, "guild_id": 1}
                await queue.enqueue(event)

        # Enqueue concurrently from multiple tasks
        await asyncio.gather(
            enqueue_batch(0, 25),
            enqueue_batch(25, 25),
            enqueue_batch(50, 25),
            enqueue_batch(75, 25),
        )

        stats = queue.get_stats()
        assert stats["queue_size"] == 100

    @pytest.mark.asyncio
    async def test_concurrent_dequeue(self):
        """Test concurrent dequeue operations."""
        queue = MessageQueue(max_size=100)

        # Enqueue events
        for i in range(50):
            event = {"message_id": str(i), "channel_id": 1, "guild_id": 1}
            await queue.enqueue(event)

        # Dequeue concurrently
        async def dequeue_batch(count):
            results = []
            for _ in range(count):
                event = await queue.dequeue()
                results.append(event)
            return results

        batches = await asyncio.gather(
            dequeue_batch(10),
            dequeue_batch(10),
            dequeue_batch(10),
            dequeue_batch(10),
            dequeue_batch(10),
        )

        # Verify all 50 events were dequeued
        all_events = [event for batch in batches for event in batch]
        assert len(all_events) == 50

        # Verify queue is empty
        stats = queue.get_stats()
        assert stats["queue_size"] == 0

    @pytest.mark.asyncio
    async def test_queue_blocking_behavior(self):
        """Test that dequeue blocks until an event is available."""
        queue = MessageQueue(max_size=10)

        dequeued_event = None

        async def consumer():
            nonlocal dequeued_event
            dequeued_event = await queue.dequeue()

        # Start consumer (will block)
        consumer_task = asyncio.create_task(consumer())

        # Give it time to start waiting
        await asyncio.sleep(0.1)

        # Enqueue an event
        event = {"message_id": "123", "channel_id": 1, "guild_id": 1}
        await queue.enqueue(event)

        # Wait for consumer to complete
        await asyncio.wait_for(consumer_task, timeout=1.0)

        assert dequeued_event == event
