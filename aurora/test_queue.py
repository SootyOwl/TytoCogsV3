"""Unit tests for Aurora message queue system."""

import asyncio

import pytest

from aurora.utils.queue import Event, EventQueue


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

    @pytest.mark.asyncio
    async def test_serialize_preserves_last_processed(self, tmp_path):
        """Test that last_processed timestamps are preserved after serialization."""
        path = tmp_path / "test_last_processed.pkl"
        queue = EventQueue(default_rate_limit=10.0)

        # Mark some event types as processed
        queue.mark_processed("message")
        queue.mark_processed("channel_12345")
        queue.mark_processed("server_activity_67890")

        # Capture timestamps before serialization
        msg_timestamp = queue.last_processed["message"]
        channel_timestamp = queue.last_processed["channel_12345"]
        activity_timestamp = queue.last_processed["server_activity_67890"]

        # Serialize
        queue.to_file(path)

        # Deserialize
        loaded_queue = EventQueue.from_file(path)

        # Verify timestamps are preserved
        assert loaded_queue.last_processed["message"] == msg_timestamp
        assert loaded_queue.last_processed["channel_12345"] == channel_timestamp
        assert (
            loaded_queue.last_processed["server_activity_67890"] == activity_timestamp
        )

        # Verify rate limiting still works based on restored timestamps
        # (should still be rate limited since we just marked them)
        assert loaded_queue.can_process("message") is False
        assert loaded_queue.can_process("channel_12345") is False

    @pytest.mark.asyncio
    async def test_serialize_preserves_processed_event_ids(self, tmp_path):
        """Test that processed_event_ids are preserved for duplicate prevention."""
        path = tmp_path / "test_processed_ids.pkl"
        queue = EventQueue(default_rate_limit=5.0, default_max_size=100)

        # Enqueue several events
        event_ids = ["msg_001", "msg_002", "msg_003"]
        for eid in event_ids:
            event = Event.from_dict(
                {
                    "event_type": "message",
                    "event_id": eid,
                    "channel_id": 123,
                }
            )
            await queue.enqueue(event)

        # Dequeue them all (so queue is empty but IDs are tracked)
        for _ in event_ids:
            await queue.dequeue("message")

        # Verify IDs are tracked
        assert len(queue.processed_event_ids) == 3
        for eid in event_ids:
            assert eid in queue.processed_event_ids

        # Serialize and deserialize
        queue.to_file(path)
        loaded_queue = EventQueue.from_file(path)

        # Verify processed_event_ids are preserved
        assert len(loaded_queue.processed_event_ids) == 3
        for eid in event_ids:
            assert eid in loaded_queue.processed_event_ids

        # Verify duplicate prevention still works after reload
        duplicate_event = Event.from_dict(
            {
                "event_type": "message",
                "event_id": "msg_001",  # Already processed
                "channel_id": 123,
            }
        )
        result = await loaded_queue.enqueue(duplicate_event)
        assert result is True  # Returns True (handled as duplicate)
        # But queue should still be empty (duplicate was skipped)
        assert loaded_queue.is_empty("message")

        # New event should be enqueued normally
        new_event = Event.from_dict(
            {
                "event_type": "message",
                "event_id": "msg_004",
                "channel_id": 123,
            }
        )
        await loaded_queue.enqueue(new_event)
        assert loaded_queue.size("message") == 1

    @pytest.mark.asyncio
    async def test_serialize_preserves_max_processed_ids(self, tmp_path):
        """Test that _max_processed_ids limit is preserved."""
        path = tmp_path / "test_max_ids.pkl"

        # Create queue and modify the max limit
        queue = EventQueue(default_rate_limit=5.0)
        queue._max_processed_ids = 500  # Custom limit

        # Add some events to have state
        for i in range(10):
            await queue.enqueue(
                Event.from_dict(
                    {
                        "event_type": "message",
                        "event_id": f"test_{i}",
                        "channel_id": 1,
                    }
                )
            )

        # Serialize and deserialize
        queue.to_file(path)
        loaded_queue = EventQueue.from_file(path)

        # Verify custom limit is preserved
        assert loaded_queue._max_processed_ids == 500

    @pytest.mark.asyncio
    async def test_serialize_preserves_default_rate_limit_for_new_types(self, tmp_path):
        """Test that default_rate_limit works for new event types after reload."""
        path = tmp_path / "test_default_rate.pkl"
        queue = EventQueue(default_rate_limit=7.5)

        # Add one event type
        await queue.enqueue(
            Event.from_dict(
                {
                    "event_type": "existing_type",
                    "event_id": "1",
                }
            )
        )

        # Serialize and deserialize
        queue.to_file(path)
        loaded_queue = EventQueue.from_file(path)

        # Verify default_rate_limit is preserved
        assert loaded_queue.default_rate_limit == 7.5

        # Add a NEW event type after reload
        await loaded_queue.enqueue(
            Event.from_dict(
                {
                    "event_type": "new_type_after_reload",
                    "event_id": "2",
                }
            )
        )

        # New type should use the preserved default rate limit
        stats = loaded_queue.get_stats()
        assert stats["new_type_after_reload"]["rate_limit_seconds"] == 7.5

    @pytest.mark.asyncio
    async def test_serialize_preserves_default_max_size_for_new_types(self, tmp_path):
        """Test that default_max_size works for new event types after reload."""
        path = tmp_path / "test_default_max.pkl"
        queue = EventQueue(default_rate_limit=5.0, default_max_size=25)

        # Add one event type
        await queue.enqueue(
            Event.from_dict(
                {
                    "event_type": "existing_type",
                    "event_id": "1",
                }
            )
        )

        # Serialize and deserialize
        queue.to_file(path)
        loaded_queue = EventQueue.from_file(path)

        # Verify default_max_size is preserved
        assert loaded_queue.default_max_size == 25

        # Add a NEW event type after reload
        await loaded_queue.enqueue(
            Event.from_dict(
                {
                    "event_type": "new_type_after_reload",
                    "event_id": "2",
                }
            )
        )

        # New type should use the preserved default max size
        stats = loaded_queue.get_stats()
        assert stats["new_type_after_reload"]["max_size"] == 25

    @pytest.mark.asyncio
    async def test_serialize_preserves_per_queue_max_sizes(self, tmp_path):
        """Test that per-queue max sizes are preserved."""
        path = tmp_path / "test_per_queue_max.pkl"
        queue = EventQueue(default_rate_limit=5.0, default_max_size=10)

        # Set custom max size for specific queue type
        queue.max_sizes["special_queue"] = 100

        # Add events to both queue types
        await queue.enqueue(
            Event.from_dict(
                {
                    "event_type": "normal_queue",
                    "event_id": "1",
                }
            )
        )
        await queue.enqueue(
            Event.from_dict(
                {
                    "event_type": "special_queue",
                    "event_id": "2",
                }
            )
        )

        # Serialize and deserialize
        queue.to_file(path)
        loaded_queue = EventQueue.from_file(path)

        # Verify per-queue max sizes are preserved
        stats = loaded_queue.get_stats()
        assert stats["normal_queue"]["max_size"] == 10  # default
        assert stats["special_queue"]["max_size"] == 100  # custom

    @pytest.mark.asyncio
    async def test_serialize_full_roundtrip_stress(self, tmp_path):
        """Stress test: full roundtrip with multiple event types and states."""
        path = tmp_path / "test_stress.pkl"
        queue = EventQueue(default_rate_limit=2.0, default_max_size=50)

        # Create multiple event types with different states
        event_types = ["message", "server_activity_123", "server_activity_456", "dm"]

        # Enqueue events for each type
        for i, et in enumerate(event_types):
            for j in range(5):
                await queue.enqueue(
                    Event.from_dict(
                        {
                            "event_type": et,
                            "event_id": f"{et}_{j}",
                            "data": f"payload_{i}_{j}",
                        }
                    )
                )

        # Mark some as processed (for rate limiting)
        queue.mark_processed("message")
        queue.mark_processed("channel_999")
        queue.mark_processed("server_activity_123")

        # Dequeue some events (partial processing)
        await queue.dequeue("message")
        await queue.dequeue("message")
        await queue.dequeue("server_activity_123")

        # Capture state before serialization
        pre_stats = queue.get_stats()
        pre_processed_ids = set(queue.processed_event_ids.keys())
        pre_last_processed_keys = set(queue.last_processed.keys())

        # Serialize and deserialize
        queue.to_file(path)
        loaded_queue = EventQueue.from_file(path)

        # Verify stats match
        post_stats = loaded_queue.get_stats()
        for et in event_types:
            assert post_stats[et]["queue_size"] == pre_stats[et]["queue_size"], (
                f"Queue size mismatch for {et}"
            )
            assert post_stats[et]["max_size"] == pre_stats[et]["max_size"], (
                f"Max size mismatch for {et}"
            )
            assert (
                post_stats[et]["rate_limit_seconds"]
                == pre_stats[et]["rate_limit_seconds"]
            ), f"Rate limit mismatch for {et}"

        # Verify processed_event_ids match
        post_processed_ids = set(loaded_queue.processed_event_ids.keys())
        assert post_processed_ids == pre_processed_ids, "Processed event IDs mismatch"

        # Verify last_processed keys match
        post_last_processed_keys = set(loaded_queue.last_processed.keys())
        assert post_last_processed_keys == pre_last_processed_keys, (
            "Last processed keys mismatch"
        )

        # Verify rate limiting still works
        assert loaded_queue.can_process("message") is False
        assert loaded_queue.can_process("channel_999") is False

        # Verify can still dequeue remaining events
        remaining_msg = await loaded_queue.dequeue("message")
        assert remaining_msg.event_type == "message"

    @pytest.mark.asyncio
    async def test_deserialize_missing_file_returns_new_queue(self, tmp_path):
        """Test that loading from non-existent file returns fresh queue."""
        path = tmp_path / "nonexistent.pkl"

        loaded_queue = EventQueue.from_file(path)

        # Should be a fresh queue with defaults
        assert loaded_queue.get_stats() == {}
        assert len(loaded_queue.processed_event_ids) == 0
        assert loaded_queue.default_rate_limit == 5.0  # default

    @pytest.mark.asyncio
    async def test_serialize_handles_datetime_min_correctly(self, tmp_path):
        """Test that datetime.min values in last_processed are handled correctly."""
        path = tmp_path / "test_datetime_min.pkl"
        queue = EventQueue(default_rate_limit=5.0)

        # Add an event type but don't mark it as processed
        await queue.enqueue(
            Event.from_dict(
                {
                    "event_type": "never_processed",
                    "event_id": "1",
                }
            )
        )

        # Serialize and deserialize
        queue.to_file(path)
        loaded_queue = EventQueue.from_file(path)

        # The never-processed type should still allow processing (datetime.min means never processed)
        assert loaded_queue.can_process("never_processed") is True

        # Stats should show None for last_processed
        stats = loaded_queue.get_stats()
        assert stats["never_processed"]["last_processed"] is None

    @pytest.mark.asyncio
    async def test_serialize_aurora_message_event_structure(self, tmp_path):
        """Test that the actual Aurora message event structure can be pickled.

        This tests the real event structure used in aurora.py's on_message handler,
        including MessageMetadata, ReplyChain, and other dataclasses.
        """
        from aurora.utils.dataclasses import (
            AuthorMetadata,
            ChannelMetadata,
            GuildMetadata,
            MessageMetadata,
            MessageRecord,
            ReplyChain,
        )

        path = tmp_path / "test_aurora_event.pkl"
        queue = EventQueue(default_rate_limit=5.0, default_max_size=50)

        # Build realistic context structure matching what Aurora creates
        metadata = MessageMetadata(
            message_id=123456789012345678,
            timestamp="2025-12-05T10:30:00+00:00",
            author=AuthorMetadata(
                id=987654321098765432,
                username="testuser",
                display_name="Test User",
                global_name="TestUser#1234",
                is_bot=False,
                roles=["Member", "Verified"],
            ),
            channel=ChannelMetadata(
                id=111222333444555666,
                name="general",
                type="text",
            ),
            guild=GuildMetadata(
                id=777888999000111222,
                name="Test Server",
            ),
        )

        # Build reply chain with message records
        reply_chain = ReplyChain()
        reply_chain.insert(
            MessageRecord(
                message_id=123456789012345670,
                author="OtherUser",
                author_id=555666777888999000,
                content="This is a previous message",
                clean_content="This is a previous message",
                timestamp="2025-12-05T10:25:00+00:00",
                is_bot=False,
                has_attachments=False,
                has_embeds=False,
            )
        )
        reply_chain.insert(
            MessageRecord(
                message_id=123456789012345675,
                author="AnotherUser",
                author_id=444555666777888999,
                content="Reply to the previous message",
                clean_content="Reply to the previous message",
                timestamp="2025-12-05T10:28:00+00:00",
                is_bot=True,
                has_attachments=True,
                has_embeds=False,
            )
        )

        context = (metadata, reply_chain)

        # Create event matching Aurora's on_message structure
        event = Event.from_dict(
            {
                "event_type": "message",
                "event_id": "123456789012345678",
                "message_id": 123456789012345678,
                "context": context,
                "prompt": "[Discord Mention Event]\n\nSomeone mentioned you in #general...",
                "timestamp": "2025-12-05T10:30:00+00:00",
                "guild_id": 777888999000111222,
                "channel_id": 111222333444555666,
                "agent_id": "agent-abc123-def456-ghi789",
            }
        )

        # Enqueue and serialize
        await queue.enqueue(event)
        queue.to_file(path)

        # Deserialize
        loaded_queue = EventQueue.from_file(path)

        # Verify queue has the event
        stats = loaded_queue.get_stats()
        assert stats["message"]["queue_size"] == 1

        # Dequeue and verify all data is preserved
        dequeued = await loaded_queue.dequeue("message")

        assert dequeued.event_type == "message"
        assert dequeued.data["message_id"] == 123456789012345678
        assert dequeued.data["guild_id"] == 777888999000111222
        assert dequeued.data["channel_id"] == 111222333444555666
        assert dequeued.data["agent_id"] == "agent-abc123-def456-ghi789"
        assert dequeued.data["prompt"].startswith("[Discord Mention Event]")
        assert dequeued.data["timestamp"] == "2025-12-05T10:30:00+00:00"

        # Verify context tuple structure
        restored_context = dequeued.data["context"]
        assert isinstance(restored_context, tuple)
        assert len(restored_context) == 2

        # Verify MessageMetadata
        restored_metadata = restored_context[0]
        assert isinstance(restored_metadata, MessageMetadata)
        assert restored_metadata.message_id == 123456789012345678
        assert restored_metadata.author.id == 987654321098765432
        assert restored_metadata.author.display_name == "Test User"
        assert restored_metadata.author.roles == ["Member", "Verified"]
        assert restored_metadata.channel.name == "general"
        assert restored_metadata.guild.name == "Test Server"

        # Verify ReplyChain
        restored_chain = restored_context[1]
        assert isinstance(restored_chain, ReplyChain)
        assert len(restored_chain) == 2
        # ReplyChain.insert() inserts at beginning, so order is reversed
        assert (
            restored_chain[0].author == "AnotherUser"
        )  # Inserted second, at position 0
        assert (
            restored_chain[1].author == "OtherUser"
        )  # Inserted first, pushed to position 1
        assert restored_chain[0].has_attachments is True

    @pytest.mark.asyncio
    async def test_serialize_aurora_server_activity_event(self, tmp_path):
        """Test that server activity events can be pickled."""
        path = tmp_path / "test_activity_event.pkl"
        queue = EventQueue(default_rate_limit=5.0)

        # Create server activity event matching Aurora's on_message structure
        event = Event.from_dict(
            {
                "event_type": "server_activity_777888999000111222",
                "channel_id": 111222333444555666,
                "message_id": 123456789012345678,
            }
        )

        await queue.enqueue(event)
        queue.to_file(path)

        loaded_queue = EventQueue.from_file(path)
        dequeued = await loaded_queue.dequeue("server_activity_777888999000111222")

        assert dequeued.data["channel_id"] == 111222333444555666
        assert dequeued.data["message_id"] == 123456789012345678


class TestMessageQueue:
    """Tests covering the message queuing behavior via EventQueue with
    event_type 'message'.
    """

    @pytest.mark.asyncio
    async def test_queue_initialization(self):
        """Test queue initializes with correct defaults."""
        queue = EventQueue(default_rate_limit=2.0, default_max_size=50)

        # Enqueue a message event to ensure the 'message' stats entry exists
        await queue.enqueue(
            Event.from_dict(
                {
                    "event_type": "message",
                    "event_id": "1",
                    "message_id": "1",
                    "channel_id": 1,
                    "guild_id": 1,
                }
            )
        )
        stats = queue.get_stats()
        assert stats["message"]["queue_size"] == 1
        # after a run, clear the queue for other tests to inspect defaults
        await queue.dequeue("message")
        assert stats["message"]["max_size"] == 50
        assert stats["message"]["rate_limit_seconds"] == 2.0

    @pytest.mark.asyncio
    async def test_serialize_deserialize(self, tmp_path):
        """Test serialization and deserialization of the queue."""
        path = tmp_path / "test_queue.pkl"
        queue = EventQueue(default_max_size=20)
        event = {
            "event_type": "message",
            "message_id": "abc123",
            "channel_id": 123456,
            "guild_id": 654321,
            "content": "Hello, World!",
        }
        await queue.enqueue(event)

        with path.open("wb") as f:
            queue.to_file(f.name)

        loaded_queue = EventQueue.from_file(path)
        stats = loaded_queue.get_stats()
        assert stats["message"]["queue_size"] == 1
        assert stats["message"]["max_size"] == 20
        # default rate limit 5.0 is the EventQueue default; if caller set rate limit differently
        assert stats["message"]["rate_limit_seconds"] >= 0

        dequeued_event = await loaded_queue.dequeue("message")
        assert dequeued_event.data.get("message_id") == event["message_id"]

    @pytest.mark.asyncio
    async def test_enqueue_single_event(self):
        """Test enqueueing a single event."""
        queue = EventQueue(default_max_size=10)

        event = {
            "message_id": "123456",
            "channel_id": 987654,
            "guild_id": 111222,
            "content": "Test message",
        }

        result = await queue.enqueue(
            Event.from_dict({"event_type": "message", **event})
        )

        assert result is True
        stats = queue.get_stats()
        assert stats["message"]["queue_size"] == 1
        await queue.dequeue("message")

    @pytest.mark.asyncio
    async def test_enqueue_duplicate_prevention(self):
        """Test that duplicate messages are not enqueued."""
        queue = EventQueue(default_max_size=10)

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

        result1 = await queue.enqueue(
            Event.from_dict({"event_type": "message", **event1})
        )
        result2 = await queue.enqueue(
            Event.from_dict({"event_type": "message", **event2})
        )

        # Both return True (second is handled as duplicate)
        assert result1 is True
        assert result2 is True  # Returns True even though skipped
        stats = queue.get_stats()
        # Only one should be in queue (duplicate was skipped)
        assert stats["message"]["queue_size"] == 1
        await queue.dequeue("message")

    @pytest.mark.asyncio
    async def test_queue_full_behavior(self):
        """Test behavior when queue is full."""
        queue = EventQueue(default_max_size=2)

        event1 = {"message_id": "111", "channel_id": 1, "guild_id": 1}
        event2 = {"message_id": "222", "channel_id": 1, "guild_id": 1}
        event3 = {"message_id": "333", "channel_id": 1, "guild_id": 1}

        await queue.enqueue(Event.from_dict({"event_type": "message", **event1}))
        await queue.enqueue(Event.from_dict({"event_type": "message", **event2}))

        # Third event should fail (queue full)
        result = await queue.enqueue(
            Event.from_dict({"event_type": "message", **event3})
        )

        assert result is False
        stats = queue.get_stats()
        assert stats["message"]["queue_size"] == 2
        await queue.dequeue("message")
        await queue.dequeue("message")

    @pytest.mark.asyncio
    async def test_dequeue_single_event(self):
        """Test dequeuing a single event."""
        queue = EventQueue(default_max_size=10)

        event = {
            "message_id": "123456",
            "channel_id": 987654,
            "guild_id": 111222,
            "content": "Test message",
        }

        await queue.enqueue(Event.from_dict({"event_type": "message", **event}))
        dequeued = await queue.dequeue("message")

        assert dequeued.data == event
        stats = queue.get_stats()
        assert stats["message"]["queue_size"] == 0

    @pytest.mark.asyncio
    async def test_dequeue_fifo_order(self):
        """Test that queue maintains FIFO order."""
        queue = EventQueue(default_max_size=10)

        events = [
            {"message_id": "111", "channel_id": 1, "guild_id": 1},
            {"message_id": "222", "channel_id": 1, "guild_id": 1},
            {"message_id": "333", "channel_id": 1, "guild_id": 1},
        ]

        for event in events:
            await queue.enqueue(Event.from_dict({"event_type": "message", **event}))

        # Dequeue should return in same order
        dequeued1 = await queue.dequeue("message")
        dequeued2 = await queue.dequeue("message")
        dequeued3 = await queue.dequeue("message")

        assert dequeued1.data.get("message_id") == "111"
        assert dequeued2.data.get("message_id") == "222"
        assert dequeued3.data.get("message_id") == "333"

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue(self):
        """Test dequeuing from empty queue (should block)."""
        queue = EventQueue(default_max_size=10)

        # Start dequeue in background (will block)
        dequeue_task = asyncio.create_task(queue.dequeue("message"))

        # Wait a bit to ensure it's blocking
        await asyncio.sleep(0.1)

        # Verify task is still pending
        assert not dequeue_task.done()

        # Now enqueue an event to unblock
        event = {"message_id": "123", "channel_id": 1, "guild_id": 1}
        await queue.enqueue(Event.from_dict({"event_type": "message", **event}))

        # Dequeue should complete
        dequeued = await asyncio.wait_for(dequeue_task, timeout=1.0)
        assert dequeued.data.get("message_id") == event["message_id"]

    @pytest.mark.asyncio
    async def test_can_process_rate_limiting(self):
        """Test rate limiting logic."""
        queue = EventQueue(default_rate_limit=1.0)

        channel_id = 987654

        # First check should allow processing
        assert queue.can_process(f"channel_{channel_id}") is True

        # Mark as processed
        queue.mark_processed(f"channel_{channel_id}")

        # Immediate check should deny (rate limited)
        assert queue.can_process(f"channel_{channel_id}") is False

        # Wait for rate limit to expire
        await asyncio.sleep(1.1)

        # Should allow processing again
        assert queue.can_process(f"channel_{channel_id}") is True

    @pytest.mark.asyncio
    async def test_mark_processed_updates_timestamp(self):
        """Test that mark_processed updates the timestamp."""
        queue = EventQueue(default_rate_limit=1.0)

        channel_id = 987654

        # First processing
        queue.mark_processed(f"channel_{channel_id}")

        # Wait a bit but not enough to expire rate limit
        await asyncio.sleep(0.5)

        # Mark processed again (resets timer)
        queue.mark_processed(f"channel_{channel_id}")

        # Wait remaining time from first check
        await asyncio.sleep(0.6)

        # Should still be rate limited (because we reset timer)
        assert queue.can_process(f"channel_{channel_id}") is False

    @pytest.mark.asyncio
    async def test_different_channels_independent_rate_limits(self):
        """Test that different channels have independent rate limits."""
        queue = EventQueue(default_rate_limit=1.0)

        channel1 = 111111
        channel2 = 222222

        # Process channel1
        queue.mark_processed(f"channel_{channel1}")

        # Channel1 should be rate limited
        assert queue.can_process(f"channel_{channel1}") is False

        # Channel2 should NOT be rate limited
        assert queue.can_process(f"channel_{channel2}") is True

    @pytest.mark.asyncio
    async def test_processed_message_ids_set_management(self):
        """Test that processed_message_ids set doesn't grow unbounded."""
        queue = EventQueue(default_max_size=10)

        # Enqueue many unique messages
        for i in range(1500):  # Exceeds max_processed_ids (1000)
            event = {"message_id": str(i), "channel_id": 1, "guild_id": 1}
            await queue.enqueue(Event.from_dict({"event_type": "message", **event}))
            await queue.dequeue("message")  # Clear queue to make room

        # Set should be limited to 1000
        assert len(queue.processed_event_ids) == 1000

    @pytest.mark.asyncio
    async def test_get_stats_accuracy(self):
        """Test that get_stats returns accurate information."""
        queue = EventQueue(default_max_size=10)

        # Add some events
        for i in range(3):
            event = {"message_id": str(i), "channel_id": 1, "guild_id": 1}
            await queue.enqueue(Event.from_dict({"event_type": "message", **event}))

        # Process one channel
        queue.mark_processed("channel_999")

        stats = queue.get_stats()
        msg_stats = stats.get("message")

        assert msg_stats["queue_size"] == 3
        assert msg_stats["max_size"] == 10
        assert len(queue.processed_event_ids) == 3
        tracked_channels = [
            k for k in queue.last_processed.keys() if str(k).startswith("channel_")
        ]
        assert len(tracked_channels) == 1

    @pytest.mark.asyncio
    async def test_concurrent_enqueue(self):
        """Test concurrent enqueue operations."""
        queue = EventQueue(default_max_size=100)

        async def enqueue_batch(start, count):
            for i in range(start, start + count):
                event = {"message_id": str(i), "channel_id": 1, "guild_id": 1}
                await queue.enqueue(Event.from_dict({"event_type": "message", **event}))

        # Enqueue concurrently from multiple tasks
        await asyncio.gather(
            enqueue_batch(0, 25),
            enqueue_batch(25, 25),
            enqueue_batch(50, 25),
            enqueue_batch(75, 25),
        )

        stats = queue.get_stats()
        assert stats["message"]["queue_size"] == 100

    @pytest.mark.asyncio
    async def test_concurrent_dequeue(self):
        """Test concurrent dequeue operations."""
        queue = EventQueue(default_max_size=100)

        # Enqueue events
        for i in range(50):
            event = {"message_id": str(i), "channel_id": 1, "guild_id": 1}
            await queue.enqueue(Event.from_dict({"event_type": "message", **event}))

        # Dequeue concurrently
        async def dequeue_batch(count):
            results = []
            for _ in range(count):
                event = await queue.dequeue("message")
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
        assert stats["message"]["queue_size"] == 0

    @pytest.mark.asyncio
    async def test_queue_blocking_behavior(self):
        """Test that dequeue blocks until an event is available."""
        queue = EventQueue(default_max_size=10)

        dequeued_event = None

        async def consumer():
            nonlocal dequeued_event
            dequeued_event = await queue.dequeue("message")

        # Start consumer (will block)
        consumer_task = asyncio.create_task(consumer())

        # Give it time to start waiting
        await asyncio.sleep(0.1)

        # Enqueue an event
        event = {"message_id": "123", "channel_id": 1, "guild_id": 1}
        await queue.enqueue(Event.from_dict({"event_type": "message", **event}))

        # Wait for consumer to complete
        await asyncio.wait_for(consumer_task, timeout=1.0)

        assert dequeued_event.data == event
