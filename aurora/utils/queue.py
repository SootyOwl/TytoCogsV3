"""Message queue implementation for Aurora event system.

This module provides:
- an async message queue with rate limiting to manage incoming Discord messages for the Letta agent.
- an event queue for managing server activity events with rate limiting and deduplication.
"""

import asyncio
import logging
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger("red.tyto.aurora.queue")


class MessageQueue:
    """Manages incoming Discord messages for agent processing.

    Implements:
    - Async queue for message events
    - Rate limiting per channel
    - Queue size limits with overflow handling
    - Message deduplication
    """

    def __init__(self, max_size: int = 50, rate_limit_seconds: float = 2.0):
        """Initialize the message queue.

        Args:
            max_size: Maximum number of events in queue (default: 50)
            rate_limit_seconds: Minimum seconds between processing messages
                               from the same channel (default: 2.0)
        """
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self.is_processing: bool = False
        self.last_processed: dict[int, datetime] = defaultdict(lambda: datetime.min)
        self.rate_limit_seconds: float = rate_limit_seconds
        # needs to be ordered to remove oldest entries first
        self.processed_message_ids = OrderedDict()
        self._max_processed_ids: int = 1000  # Prevent unbounded growth

        log.info(
            f"MessageQueue initialized: max_size={max_size}, "
            f"rate_limit={rate_limit_seconds}s"
        )

    async def enqueue(self, event: dict, allow_duplicate: bool = False) -> bool:
        """Add event to queue.

        Args:
            event: Event dictionary to queue

        Returns:
            True if event was queued successfully, False if queue is full
        """
        message_id = event.get("message_id")

        # Check for duplicate (unless caller explicitly allows re-queueing the same message)
        if (
            message_id
            and message_id in self.processed_message_ids
            and not allow_duplicate
        ):
            log.debug(f"Skipping duplicate message {message_id}")
            return True  # Return True to indicate it was handled (even if skipped)

        try:
            # Use put_nowait to avoid awaiting while holding caller context
            self.queue.put_nowait(event)

            # Track this message ID (only when first enqueuing, not for allowed re-queues)
            if message_id and not allow_duplicate:
                self.processed_message_ids[message_id] = None

                # Prevent unbounded growth of processed_message_ids list
                if len(self.processed_message_ids.keys()) > self._max_processed_ids:
                    cleanup_size = self._max_processed_ids // 2
                    for _ in range(cleanup_size):
                        self.processed_message_ids.popitem(last=False)
                    log.debug(
                        f"Cleaned up {cleanup_size} old message IDs from tracking"
                    )

            log.debug(
                f"Enqueued message {message_id}, queue size: {self.queue.qsize()}"
            )
            return True

        except asyncio.QueueFull:
            log.warning(
                f"Message queue full (size={self.queue.qsize()}), "
                f"dropping event for message {message_id}"
            )
            return False

    def can_process(self, channel_id: int) -> bool:
        """Check if enough time has passed since last message from this channel.

        Args:
            channel_id: Discord channel ID to check

        Returns:
            True if channel can be processed, False if rate limited
        """
        if self.is_processing:
            return False
        last = self.last_processed[channel_id]
        elapsed = (datetime.now() - last).total_seconds()
        can_process = elapsed >= self.rate_limit_seconds

        if not can_process:
            remaining = self.rate_limit_seconds - elapsed
            log.debug(f"Channel {channel_id} rate limited, {remaining:.1f}s remaining")

        return can_process

    def mark_processed(self, channel_id: int):
        """Mark a channel as having been processed.

        Args:
            channel_id: Discord channel ID to mark
        """
        self.is_processing = False
        self.last_processed[channel_id] = datetime.now()
        log.debug(f"Marked channel {channel_id} as processed")

    async def dequeue(self) -> dict:
        """Get next event from queue (blocks if empty).

        Returns:
            Event dictionary from queue
        """
        event = await self.queue.get()
        log.debug(f"Dequeued event for message {event.get('message_id')}")
        return event

    def is_empty(self) -> bool:
        """Check if queue is empty.

        Returns:
            True if queue is empty, False otherwise
        """
        return self.queue.empty()

    def size(self) -> int:
        """Get current queue size.

        Returns:
            Number of events in queue
        """
        return self.queue.qsize()

    def clear(self):
        """Clear all events from the queue."""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        log.info("Message queue cleared")

    def get_stats(self) -> dict:
        """Get queue statistics.

        Returns:
            Dictionary containing queue stats
        """
        return {
            "queue_size": self.queue.qsize(),
            "max_size": self.queue.maxsize,
            "rate_limit_seconds": self.rate_limit_seconds,
            "tracked_channels": len(self.last_processed),
            "tracked_message_ids": len(self.processed_message_ids),
        }


@dataclass
class Event:
    """Represents a server activity event."""

    event_type: str
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    data: dict = field(default_factory=dict)

    @property
    def as_dict(self) -> dict:
        """Return event as dictionary."""
        return {
            "event_type": self.event_type,
            "event_id": str(self.event_id),
            **self.data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        """Create Event instance from dictionary."""
        event_type = data.get("event_type")
        if not event_type:
            raise ValueError("event_type is required to create an Event")
        event_id = (
            uuid.UUID(data.get("event_id")) if "event_id" in data else uuid.uuid4()
        )
        event_data = {
            k: v for k, v in data.items() if k not in {"event_type", "event_id"}
        }
        return cls(event_type=event_type, event_id=event_id, data=event_data)


class EventQueue:
    """Manages server activity events with rate limiting.

    Has a queue for each event type to allow independent processing.
    """

    def __init__(self, default_rate_limit: float = 5.0):
        """Initialize the event queue.

        Args:
            default_rate_limit: Minimum seconds between processing events
                               of the same type (default: 5.0)
        """
        self.queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.rate_limits: dict[str, float] = defaultdict(lambda: default_rate_limit)
        self.last_processed: dict[str, datetime] = defaultdict(lambda: datetime.min)
        self.processed_event_ids = OrderedDict()
        self._max_processed_ids: int = 1000  # Prevent unbounded growth

    async def enqueue(
        self, event: Event | dict, allow_duplicates: bool = False
    ) -> bool:
        """Add event to appropriate queue.

        Args:
            event: Event instance or dictionary to queue
            allow_duplicates: If True, allows duplicate event IDs to be enqueued (default: False)

        Returns:
            True if event was queued successfully
        """
        if isinstance(event, dict):
            event = Event.from_dict(event)

        queue = self.queues[event.event_type]
        # Check for duplicate
        if event.event_id in self.processed_event_ids and not allow_duplicates:
            log.debug(f"Skipping duplicate event {event.event_id}")
            return True  # Indicate handled even if skipped

        try:
            # Use put_nowait to avoid awaiting while holding caller context
            queue.put_nowait(event)
            log.debug(
                f"Enqueued event {event.event_id} of type {event.event_type}, "
                f"queue size: {queue.qsize()}"
            )
            # Track this event ID
            if not allow_duplicates:
                self.processed_event_ids[event.event_id] = None

                # Prevent unbounded growth of processed_event_ids list
                if len(self.processed_event_ids.keys()) > self._max_processed_ids:
                    cleanup_size = self._max_processed_ids // 2
                    for _ in range(cleanup_size):
                        self.processed_event_ids.popitem(last=False)
                    log.debug(f"Cleaned up {cleanup_size} old event IDs from tracking")
            return True
        except asyncio.QueueFull:
            log.warning(
                f"Event queue for type {event.event_type} full, "
                f"dropping event {event.event_id}"
            )
            return False

    def can_process(self, event_type: str) -> bool:
        """Check if enough time has passed since last event of this type.

        Args:
            event_type: Type of event to check
        Returns:
            True if event type can be processed, False if rate limited
        """
        last = self.last_processed[event_type]
        elapsed = (datetime.now() - last).total_seconds()
        can_process = elapsed >= self.rate_limits[event_type]

        if not can_process:
            remaining = self.rate_limits[event_type] - elapsed
            log.debug(
                f"Event type {event_type} rate limited, {remaining:.1f}s remaining"
            )

        return can_process

    def mark_processed(self, event_type: str):
        """Mark an event type as having been processed.

        Args:
            event_type: Type of event to mark
        """
        self.last_processed[event_type] = datetime.now()
        log.debug(f"Marked event type {event_type} as processed")

    async def dequeue(self, event_type: str) -> Event:
        """Get next event of specified type from queue (blocks if empty).

        Args:
            event_type: Type of event to dequeue

        Returns:
            Event instance from queue
        """
        queue = self.queues[event_type]
        event = await queue.get()
        log.debug(f"Dequeued event {event.event_id} of type {event.event_type}")
        return event

    async def consume_all(self, event_type: str):
        """
        Consume all events of specified type from queue. Empties the queue for that type.

        Args:
            event_type: Type of event to consume

        Returns:
            List of Event instances from queue
        """
        events = []
        queue = self.queues[event_type]
        while not queue.empty():
            event = await queue.get()
            events.append(event)
            log.debug(f"Consumed event {event.event_id} of type {event.event_type}")
        return events

    def is_empty(self, event_type: str) -> bool:
        """Check if queue for specified event type is empty.

        Args:
            event_type: Type of event to check

        Returns:
            True if the queue for the specified event type is empty, False otherwise
        """
        queue = self.queues[event_type]
        return queue.empty()

    def size(self, event_type: str) -> int:
        """Get current size of queue for specified event type.

        Args:
            event_type: Type of event to check

        Returns:
            int: Number of events in the queue for the specified event type
        """
        queue = self.queues[event_type]
        return queue.qsize()

    def clear(self, event_type: str):
        """Clear all events from the queue for specified event type.

        Args:
            event_type: Type of event queue to clear
        """
        queue = self.queues[event_type]
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        log.info(f"Event queue for type {event_type} cleared")

    def reset(self):
        """Clear all queues and reset tracking."""
        self.queues.clear()
        self.last_processed.clear()
        self.processed_event_ids.clear()
        log.info("All event queues and tracking reset")

    def get_stats(self) -> dict:
        """Get statistics for all event queues.

        Returns:
            Dictionary containing stats per event type
        """
        stats = {}
        for event_type, queue in self.queues.items():
            stats[event_type] = {
                "queue_size": queue.qsize(),
                "rate_limit_seconds": self.rate_limits[event_type],
                "last_processed": self.last_processed[event_type].isoformat(),
            }
        return stats
