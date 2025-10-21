"""Message queue implementation for Aurora event system.

This module provides an async message queue with rate limiting to manage
incoming Discord messages for the Letta agent.
"""

import asyncio
import logging
from collections import defaultdict
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
        self.last_processed: dict[int, datetime] = defaultdict(lambda: datetime.min)
        self.rate_limit_seconds: float = rate_limit_seconds
        self.processed_message_ids: set[int] = set()
        self._max_processed_ids: int = 1000  # Prevent unbounded growth

        log.info(
            f"MessageQueue initialized: max_size={max_size}, "
            f"rate_limit={rate_limit_seconds}s"
        )

    async def enqueue(self, event: dict) -> bool:
        """Add event to queue.

        Args:
            event: Event dictionary to queue

        Returns:
            True if event was queued successfully, False if queue is full
        """
        message_id = event.get("message_id")

        # Check for duplicate
        if message_id and message_id in self.processed_message_ids:
            log.debug(f"Skipping duplicate message {message_id}")
            return True  # Return True to indicate it was handled (even if skipped)

        try:
            self.queue.put_nowait(event)

            # Track this message ID
            if message_id:
                self.processed_message_ids.add(message_id)

                # Prevent unbounded growth of processed_message_ids set
                if len(self.processed_message_ids) > self._max_processed_ids:
                    # Remove oldest half
                    to_remove = list(self.processed_message_ids)[
                        : self._max_processed_ids // 2
                    ]
                    self.processed_message_ids.difference_update(to_remove)
                    log.debug(
                        f"Cleaned up {len(to_remove)} old message IDs from tracking"
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
