"""Message queue implementation for Aurora event system.

This module provides:
- an async message queue with rate limiting to manage incoming Discord messages for the Letta agent.
- an event queue for managing server activity events with rate limiting and deduplication.
"""

import asyncio
import logging
import pickle
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Union

log = logging.getLogger("red.tyto.aurora.queue")


@dataclass
class Event:
    """Represents a server activity event."""

    event_type: str
    event_id: Union[str, int, uuid.UUID] = field(default_factory=uuid.uuid4)
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

        # Prefer an explicit event_id; for messages, allow using message_id
        event_id = data.get("event_id") or (
            data.get("message_id")
            if event_type == "message" and data.get("message_id")
            else uuid.uuid4()
        )
        # normalize to string to make deduping consistent
        if not isinstance(event_id, (str, int, uuid.UUID)):
            event_id = str(event_id)

        event_data = {
            k: v for k, v in data.items() if k not in {"event_type", "event_id"}
        }
        return cls(event_type=event_type, event_id=event_id, data=event_data)


class EventQueue:
    """Manages server activity events with rate limiting.

    Has a queue for each event type to allow independent processing.
    """

    def __init__(
        self, default_rate_limit: float = 5.0, default_max_size: int | None = None
    ):
        """Initialize the event queue.

        Args:
            default_rate_limit: Minimum seconds between processing events
                               of the same type (default: 5.0)
        """
        self.default_max_size = default_max_size
        self.max_sizes: dict[str, int] = defaultdict(lambda: default_max_size or 0)
        self.queues: dict[str, asyncio.Queue] = {}
        self.default_rate_limit = default_rate_limit
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

        # Lazily initialize queue for this event_type with maxsize
        queue = self.queues.get(event.event_type)
        if queue is None:
            maxsize = self.max_sizes[event.event_type] or 0
            queue = asyncio.Queue(maxsize=maxsize)
            self.queues[event.event_type] = queue
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
        queue = self.queues.get(event_type)
        if queue is None:
            # initialize empty queue with default max size
            maxsize = self.max_sizes[event_type] or 0
            queue = asyncio.Queue(maxsize=maxsize)
            self.queues[event_type] = queue
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
        queue = self.queues.get(event_type)
        if queue is None:
            return []
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
        queue = self.queues.get(event_type)
        if queue is None:
            return True
        return queue.empty()

    def size(self, event_type: str) -> int:
        """Get current size of queue for specified event type.

        Args:
            event_type: Type of event to check

        Returns:
            int: Number of events in the queue for the specified event type
        """
        queue = self.queues.get(event_type)
        if queue is None:
            return 0
        return queue.qsize()

    def clear(self, event_type: str):
        """Clear all events from the queue for specified event type.

        Args:
            event_type: Type of event queue to clear
        """
        queue = self.queues.get(event_type)
        if queue is None:
            return
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
                "max_size": queue.maxsize,
                "rate_limit_seconds": self.rate_limits[event_type],
                "last_processed": self.last_processed[event_type].isoformat()
                if self.last_processed[event_type] != datetime.min
                else None,
            }
        return stats

    def to_file(self, file_path: str | Path):
        """Serialize the event queues to a file."""
        with open(file_path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def from_file(cls, file_path: str | Path) -> "EventQueue":
        """Deserialize the event queues from a file."""
        if not Path(file_path).exists():
            return cls()

        with open(file_path, "rb") as f:
            queue = pickle.load(f)
        return queue

    def __getstate__(self):
        """Get state for pickling."""
        state = self.__dict__.copy()
        # Remove any non-picklable objects
        state["queues"] = {
            k: list(getattr(v, "_queue", [])) for k, v in self.queues.items()
        }
        # store maxsize per queue so we can reconstruct
        state["max_sizes"] = dict(self.max_sizes)
        state["default_max_size"] = self.default_max_size
        # convert defaultdicts to regular dicts
        state["rate_limits"] = dict(state["rate_limits"])
        state["last_processed"] = dict(state["last_processed"])
        state["processed_event_ids"] = dict(state["processed_event_ids"])
        return state

    def __setstate__(self, state):
        """Set state from pickling."""
        self.__dict__.update(state)
        # Reconstruct asyncio.Queues
        self.queues = {}
        for k, v in state["queues"].items():
            # reconstruct with maxsize if available
            maxsize = state.get("max_sizes", {}).get(k, 0) or 0
            q = asyncio.Queue(maxsize=maxsize)
            for item in v:
                q.put_nowait(item)
            self.queues[k] = q
        # Reconstruct defaultdicts
        self.rate_limits = defaultdict(
            lambda: self.default_rate_limit, state["rate_limits"]
        )
        self.last_processed = defaultdict(lambda: datetime.min, state["last_processed"])
        self.processed_event_ids = OrderedDict(state["processed_event_ids"])
        # reconstruct max_sizes
        self.max_sizes = defaultdict(
            lambda: state.get("default_max_size", 0), state.get("max_sizes", {})
        )
        self.default_max_size = state.get("default_max_size")
