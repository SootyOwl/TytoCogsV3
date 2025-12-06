"""Aurora Cog for Red Discord Bot

This cog integrates the Letta AI service to create an autonomous Discord agent
that can respond to messages in channels and DMs.
"""

import asyncio
import json
import logging
from collections import Counter
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional, TypedDict

import discord
from discord.ext import tasks
from discord.utils import format_dt
from letta_client import AsyncLetta, AsyncStream, RequestOptions
from letta_client.types.agents.approval_request_message import ApprovalRequestMessage
from letta_client.types.agents.approval_response_message import ApprovalResponseMessage
from letta_client.types.agents.assistant_message import AssistantMessage
from letta_client.types.agents.hidden_reasoning_message import HiddenReasoningMessage
from letta_client.types.agents.letta_streaming_response import (
    LettaErrorMessage,
    LettaPing,
    LettaStopReason,
    LettaUsageStatistics,
)
from letta_client.types.agents.reasoning_message import ReasoningMessage
from letta_client.types.agents.system_message import SystemMessage
from letta_client.types.agents.tool_call_message import ToolCallMessage
from letta_client.types.agents.user_message import UserMessage
from letta_client.types.tool_return_message import ToolReturnMessage
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import humanize_timedelta

from .utils.blocks import attach_blocks, detach_blocks
from .utils.context import build_event_context
from .utils.errors import CircuitBreaker, ErrorStats, RetryConfig, retry_with_backoff
from .utils.prompts import build_prompt
from .utils.queue import Event, EventQueue

log = logging.getLogger("red.tyto.aurora")

RunTracker = TypedDict("RunTracker", {"run_id": str | None, "task": asyncio.Task | None})


class ToolCallError(Exception):
    """Exception raised when a tool call fails."""

    pass


class EventType(str, Enum):
    """Types of events that can be processed."""

    MESSAGE = "message"
    SERVER_ACTIVITY = "server_activity_{guild_id}"
    SYNTHESIS = "synthesis_{guild_id}"

    def format(self, **kwargs) -> str:
        """Format the event type with the given keyword arguments."""
        return self.value.format(**kwargs)


class Aurora(commands.Cog):
    """Autonomous Discord person powered by Letta."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=3897456238745, force_registration=True)
        default_global = {
            "letta_base_url": "https://api.letta.ai/v1",
        }
        self.config.register_global(**default_global)

        # get data path for serialization of queues (persisted across restarts)
        self.data_path = cog_data_path(self)

        default_guild = {
            "agent_id": None,
            "enabled": False,
            "synthesis_interval": 3600,
            "server_activity_interval": 1800,
            "activity_threshold": 1,
            # Event system settings
            "reply_thread_depth": 5,
            "enable_typing_indicator": True,
            "enable_dm_responses": True,
            "max_queue_size": 50,
            "agent_timeout": 60,
            "mcp_guidance_enabled": True,
            "rate_limit_seconds": 2,
        }
        self.config.register_guild(**default_guild)

        # Letta client (will be initialized in setup)
        self.letta: Optional[AsyncLetta] = None
        self.tasks: dict[str, tasks.Loop] = {}

        # Event queue for all events (messages and activity)
        self.queue: Optional[EventQueue] = None
        self._events_paused: bool = False

        # Error handling components
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            half_open_attempts=3,
        )
        self.error_stats = ErrorStats(window_size=100)
        self.retry_config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            exponential_base=2.0,
            max_delay=30.0,
        )
        self.request_options = RequestOptions(timeout=300, max_retries=3)

    def _get_event_stats(self, event_type: str | None = None) -> dict:
        """Return normalized stats for event types from the EventQueue.

        This maps EventQueue.get_stats() values into a shape used by the
        UI and commands which expect an event-queue style summary.

        Args:
            event_type: Specific event type to get stats for, or None for all types.

        Returns:
            If event_type is specified: stats dict for that event type.
            If event_type is None: dict mapping event_type -> stats dict for all types.
        """
        if not self.queue:
            empty_stats = {
                "queue_size": 0,
                "max_size": 0,
                "rate_limit_seconds": None,
                "tracked_channels": 0,
                "tracked_event_ids": 0,
            }
            return empty_stats if event_type else {}

        # Global tracking stats (shared across all event types)
        tracked_channels = len(
            [k for k in self.queue.last_processed.keys() if str(k).startswith("channel_")]  # type: ignore
        )
        tracked_event_ids = len(self.queue.processed_event_ids) if hasattr(self.queue, "processed_event_ids") else 0

        queue = self.queue  # Local reference for type narrowing

        def build_stats_for_type(et: str, raw_stats: dict) -> dict:
            """Build normalized stats for a single event type."""
            # queue.maxsize is 0 for an unbounded asyncio.Queue
            max_size = raw_stats.get("max_size", None)
            if max_size is None and et in queue.queues:
                max_size = queue.queues[et].maxsize
            rate_limit_seconds = raw_stats.get("rate_limit_seconds")
            return {
                "queue_size": raw_stats.get("queue_size", 0),
                "max_size": max_size or 0,
                "rate_limit_seconds": rate_limit_seconds or queue.default_rate_limit,
                "last_processed": raw_stats.get("last_processed"),
                "tracked_channels": tracked_channels,
                "tracked_event_ids": tracked_event_ids,
            }

        raw_stats = queue.get_stats()

        if event_type is not None:
            # Return stats for specific event type
            return build_stats_for_type(event_type, raw_stats.get(event_type, {}))

        # Return stats for all event types
        return {et: build_stats_for_type(et, et_stats) for et, et_stats in raw_stats.items()}

    async def cog_load(self):
        """Load the Letta client and start the synthesis."""
        try:
            # Load persisted queues if they exist
            self.queue = EventQueue.from_file(self.data_path / "event_queue.pkl")
            log.info("Loaded persisted queues from disk")
        except Exception as e:
            log.error(f"Error loading queues: {e}, initializing new queues.")
            self.queue = EventQueue()
        # Start message processor worker
        self.process_message_queue.start()
        log.info("Message processor started")
        # kick off the initialization without blocking
        asyncio.create_task(self.initialize_letta())

    @commands.Cog.listener(name="on_ready")
    async def initialize_letta(self):
        """Configure Letta client based on global settings."""
        await self.bot.wait_until_ready()
        letta_base_url = await self.config.letta_base_url()
        letta_tokens = await self.bot.get_shared_api_tokens("letta")
        if token := letta_tokens.get("token"):
            self.letta = AsyncLetta(
                base_url=letta_base_url,
                api_key=token,
            )
            log.info("Letta client configured successfully.")

            # start tasks for all guilds with enabled agents
            all_guilds: dict[int, dict] = await self.config.all_guilds()
            for guild_id, guild_config in all_guilds.items():
                if guild_config.get("enabled") and guild_config.get("agent_id"):
                    synthesis_interval = guild_config.get("synthesis_interval", 3600)
                    self._get_or_create_task(
                        self.synthesis,
                        guild_id,
                        synthesis_interval,
                        before_coro=self.before_synthesis,
                    )
                    activity_interval = guild_config.get("server_activity_interval", 1800)
                    self._get_or_create_task(
                        self.track_server_activity,
                        guild_id,
                        activity_interval,
                        before_coro=self.before_activity_tracking,
                    )
            return self.letta
        else:
            log.warning("Letta API token not found. Aurora will not function.")
            self.letta = None
            return None

    async def cog_unload(self):
        """Stop the synthesis and message processor."""
        self._cancel_tasks()

        # Stop message processor
        self.process_message_queue.stop()
        log.info("Message processor stopped")
        try:
            # Persist queues to disk
            if self.queue:
                self.queue.to_file(self.data_path / "event_queue.pkl")
            log.info("Persisted queues to disk")
        except Exception as e:
            log.error(f"Error persisting queues: {e}")

    # region: Task Management
    def _get_task(self, coro, guild_id: int) -> Optional[tasks.Loop]:
        """Get the task for the given guild, if it exists."""
        task_name = f"{coro.__name__}_{guild_id}"
        return self.tasks.get(task_name)

    def _get_or_create_task(
        self,
        coro,
        guild_id: int,
        interval_secs: int = 3600,
        before_coro=None,
        after_coro=None,
    ) -> tasks.Loop:
        """Get or create a task for the given guild."""
        task_name = f"{coro.__name__}_{guild_id}"
        if task_name not in self.tasks:
            task = tasks.loop(seconds=interval_secs)(coro)  # type: ignore
            if before_coro:
                task.before_loop(before_coro)  # type: ignore
            if after_coro:
                task.after_loop(after_coro)  # type: ignore
            self.tasks[task_name] = task
            task.start(guild_id=guild_id)
            log.info("Started task %s for guild %d", task_name, guild_id)
        return self.tasks[task_name]

    def _remove_task(self, coro, guild_id: int):
        """Remove and cancel the task for the given guild."""
        task_name = f"{coro.__name__}_{guild_id}"
        if task_name in self.tasks:
            task = self.tasks[task_name]
            task.cancel()
            log.info("Cancelled task %s for guild %d", task_name, guild_id)
            del self.tasks[task_name]

    def _cancel_tasks(self):
        """Cancel all running tasks."""
        for task_name, task in self.tasks.items():
            task.cancel()
            log.info("Cancelled task %s", task_name)

        self.tasks.clear()
        log.info("All tasks cancelled.")

    # endregion

    # region: Synthesis Task
    async def synthesis(self, guild_id: int):
        """A synthesis task to allow aurora to perform periodic actions."""
        log.debug("synthesis for guild %d", guild_id)
        today = date.today()
        heatbeat_dict = {
            "type": "synthesis_and_exploration",
            "guild_id": guild_id,
            "description": "Dedicated time for autonomous reflection, learning, and experimentation. Use this time to:",
            "activities": [
                "Review and consolidate recent interactions into memory blocks",
                "Explore the Discord server: search messages, read channels, understand dynamics",
                "Search the web for topics of interest or relevance to your goals",
                "Analyze patterns in your behavior and interactions",
                "Create new memory structures to organize knowledge",
                "Experiment with tools and capabilities",
                "Reflect on your growth, patterns, and evolving understanding",
                "Plan and send messages to relevant channels based on your insights",
                "Document insights in temporal journals (daily/monthly/yearly) - NOTE: Do not manually create these memory blocks outside of this task as they are managed for you.",
                "Synthesize experiences into core memory (zeitgeist, persona, humans, etc.)",
                "Generate new goals and plans based on your reflections and insights",
                "Update your persona to reflect your evolving identity and objectives",
                "...and more as you see fit",
            ],
            "autonomy_level": "high",
            "time": today.isoformat(),
            "journals": [
                f"aurora_daily_{today.strftime('%Y_%m_%d')}",
                f"aurora_month_{today.strftime('%Y_%m')}",
                f"aurora_year_{today.strftime('%Y')}",
            ],
        }
        heatbeat_prompt = (
            "[Synthesis and Exploration Event]\n" f"""```json\n{json.dumps(heatbeat_dict, indent=2)}\n```"""
        )
        if not self.letta:
            log.warning("Letta client not configured. Cannot run synthesis.")
            return

        agent_id = None
        attached = False
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                log.warning("Guild %d not found. Stopping synthesis task.", guild_id)
                self._remove_task(self.synthesis, guild_id)  # type: ignore
                return

            guild_config = await self.config.guild(guild).all()
            agent_id = guild_config.get("agent_id")
            if not agent_id:
                log.warning(
                    "Agent ID not configured for guild %d. Stopping synthesis task.",
                    guild_id,
                )
                self._remove_task(self.synthesis, guild_id)  # type: ignore
                return

            log.info("Starting synthesis for guild %d", guild_id)
            # attach necessary blocks
            block_names = [
                f"aurora_daily_{today.strftime('%Y_%m_%d')}",
                f"aurora_month_{today.strftime('%Y_%m')}",
                f"aurora_year_{today.strftime('%Y')}",
            ]
            success, attached = await attach_blocks(self.letta, agent_id, block_names)
            if not success:
                log.warning("Failed to attach blocks for guild %d during synthesis.", guild_id)

            # Send the synthesis prompt to the agent with retry logic
            async def send_synthesis_message():
                message_stream = await self.letta.agents.messages.create(
                    agent_id=agent_id,
                    messages=[
                        {
                            "role": "system",
                            "content": heatbeat_prompt,
                        }
                    ],
                    streaming=True,
                    stream_tokens=False,
                    max_steps=100,  # increased to allow more processing steps during synthesis
                    timeout=self.request_options.get("timeout"),
                )
                await self._process_agent_stream(message_stream)

            await retry_with_backoff(
                send_synthesis_message,
                self.retry_config,
                self.circuit_breaker,
            )
        except Exception as e:
            log.exception("Exception during synthesis for guild %d: %s", guild_id, str(e))
        finally:
            # Update last synthesis time (even on error, to prevent rapid retries)
            event_type = EventType.SYNTHESIS.format(guild_id=guild_id)
            if self.queue:
                self.queue.mark_processed(event_type)
            # detach blocks
            if self.letta and agent_id and attached:
                success, _ = await detach_blocks(self.letta, agent_id, block_names)
                if not success:
                    log.warning(
                        "Failed to detach blocks for guild %d after synthesis.",
                        guild_id,
                    )

    async def before_synthesis(self):
        """Prepare for synthesis by checking timing constraints.

        Loop.before_loop callbacks cannot accept the loop arguments, so infer
        the guild_id by finding which Loop object in self.tasks has the current
        asyncio Task as its underlying task."""
        current = asyncio.current_task()
        guild_id = None
        for name, loop in self.tasks.items():
            if getattr(loop, "_task", None) is current:
                # extract guild_id from task name
                try:
                    guild_id = int(name.split("_")[-1])
                except (ValueError, IndexError):
                    continue
                break
        if guild_id is None:
            log.error("Could not determine guild_id for synthesis before_loop.")
            return False

        await self.bot.wait_until_ready()
        # Check if synthesis is enabled and timing is correct
        guild = self.bot.get_guild(guild_id)
        if not guild:
            log.warning("Guild %d not found. Cannot run synthesis.", guild_id)
            self._remove_task(self.synthesis, guild_id)  # type: ignore
            return False

        guild_config = await self.config.guild(guild).all()
        synthesis_interval: int = guild_config.get("synthesis_interval", 3600)

        # Get last synthesis time from queue
        event_type = EventType.SYNTHESIS.format(guild_id=guild_id)
        last_synthesis_dt = self.queue.last_processed.get(event_type, datetime.min) if self.queue else datetime.min

        if last_synthesis_dt != datetime.min:
            time_since_last = (
                datetime.now(timezone.utc) - last_synthesis_dt.replace(tzinfo=timezone.utc)
            ).total_seconds()
            if time_since_last < synthesis_interval:
                wait_time: float = synthesis_interval - time_since_last
                log.info(
                    "Not enough time since last synthesis for guild %d. " "Waiting %.1f seconds.",
                    guild_id,
                    wait_time,
                )
                # wait until next interval
                await asyncio.sleep(wait_time)
        return True

    # endregion

    # region: Server Activity Task
    async def track_server_activity(self, guild_id: int):
        """A task to track server activity and notify the agent periodically."""
        log.debug("track_server_activity for guild %d", guild_id)
        if not self.letta:
            log.warning("Letta client not configured. Cannot track server activity.")
            return
        if not self.queue:
            log.warning("Activity queue not initialized. Cannot track activity.")
            return

        agent_id = None
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                log.warning("Guild %d not found. Stopping channel activity task.", guild_id)
                self._remove_task(self.track_server_activity, guild_id)  # type: ignore
                return

            guild_config = await self.config.guild(guild).all()
            agent_id = guild_config.get("agent_id")
            if not agent_id:
                log.warning(
                    "Agent ID not configured for guild %d. Stopping channel activity task.",
                    guild_id,
                )
                self._remove_task(self.track_server_activity, guild_id)  # type: ignore
                return

            log.info("Starting server activity tracking for guild %d", guild_id)
            # Consume all the server_activity events in the queue for this guild
            event_type = EventType.SERVER_ACTIVITY.format(guild_id=guild_id)
            events: list[Event] = await self.queue.consume_all(event_type)
            if not events:
                log.info("No server activity events to process for guild %d.", guild_id)
                return
            # Build activity summary
            activity_summary: dict
            events_to_reenqueue: list[Event]
            activity_summary, events_to_reenqueue = await self.build_activity_summary(
                events, threshold=guild_config.get("activity_threshold", 1)
            )
            log.info("Built activity summary for guild %d: %s", guild_id, activity_summary)

            # Re-enqueue events from channels that didn't meet the threshold
            if events_to_reenqueue:
                log.info(
                    "Re-enqueueing %d events from channels below threshold for guild %d.",
                    len(events_to_reenqueue),
                    guild_id,
                )
                for event in events_to_reenqueue:
                    await self.queue.enqueue(event, allow_duplicates=True)

            if not activity_summary:
                log.info("No channels met the activity threshold for guild %d.", guild_id)
                return

            # Send the activity summary to the agent with retry logic
            async def send_activity_message():
                message_stream = await self.letta.agents.messages.create(
                    agent_id=agent_id,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "[Server Activity Notification]\n\n"
                                f"```json\n{json.dumps(activity_summary, indent=2)}\n```\n\n"
                                "The above is a summary of recent server activity - channels and users which have new activity.\n"
                                "You may choose to engage with active channels or users based on this information using your `discord_*` tools, if appropriate.\n"
                                "Use the `discord_read_messages` tool to read recent messages in active channels to get context before responding.\n"
                                "You may use `web_search`, `fetch_webpage`, `get_image_alttext`, etc. to gather more information if needed.\n"
                                "Focus on meaningful engagement that adds value to the conversations.\n"
                                "Do not feel obligated to respond to all activity; use your judgment to decide when and where to participate.\n"
                            ),
                        }
                    ],
                    streaming=True,
                    stream_tokens=False,
                    max_steps=50,
                    timeout=self.request_options.get("timeout"),
                )
                await self._process_agent_stream(message_stream)

            await retry_with_backoff(
                send_activity_message,
                self.retry_config,
                self.circuit_breaker,
            )
        except Exception as e:
            log.exception(
                "Exception during server activity tracking for guild %d: %s",
                guild_id,
                str(e),
            )
        finally:
            # Always mark as processed to update timing for rate limiting and stats
            # This uses queue.last_processed as the single source of truth
            if self.queue:
                event_type = EventType.SERVER_ACTIVITY.format(guild_id=guild_id)
                self.queue.mark_processed(event_type)

    async def before_activity_tracking(self):
        """Prepare for activity tracking by checking timing constraints.

        Loop.before_loop callbacks cannot accept the loop arguments, so infer
        the guild_id by finding which Loop object in self.tasks has the current
        asyncio Task as its underlying task."""
        current = asyncio.current_task()
        guild_id = None
        for name, loop in self.tasks.items():
            if getattr(loop, "_task", None) is current:
                # extract guild_id from task name
                try:
                    guild_id = int(name.split("_")[-1])
                except (ValueError, IndexError):
                    continue
                break
        if guild_id is None:
            log.error("Could not determine guild_id for activity tracking before_loop.")
            return False

        await self.bot.wait_until_ready()
        # Check if activity tracking is enabled and timing is correct
        guild = self.bot.get_guild(guild_id)
        if not guild:
            log.warning("Guild %d not found. Cannot track activity.", guild_id)
            self._remove_task(self.track_server_activity, guild_id)  # type: ignore
            return False

        guild_config = await self.config.guild(guild).all()
        activity_interval: int = guild_config.get("server_activity_interval", 1800)

        # Use queue.last_processed as the single source of truth for timing
        event_type = EventType.SERVER_ACTIVITY.format(guild_id=guild_id)
        if self.queue:
            last_processed = self.queue.last_processed.get(event_type)
            if last_processed and last_processed != datetime.min:
                time_since_last = (datetime.now() - last_processed).total_seconds()
                if time_since_last < activity_interval:
                    wait_time: float = activity_interval - time_since_last
                    log.info(
                        "Not enough time since last activity tracking for guild %d. " "Waiting %.1f seconds.",
                        guild_id,
                        wait_time,
                    )
                    # wait until next interval
                    await asyncio.sleep(wait_time)
        return True

    async def build_activity_summary(self, events: list[Event], threshold: int) -> tuple[dict, list[Event]]:
        """Build a summary of server activity from the list of events.

        Don't need content, just who said stuff in which channel.
        TODO: This is probably fairly inefficient if there are a lot of events but should
        be fine for now.

        Args:
            events (list[Event]): The list of events to summarize.
            threshold (int): Minimum number of messages in a channel to be included in the summary.

        Returns:
            tuple[dict, list[Event]]: A tuple containing:
                - The activity summary dict for channels meeting the threshold
                - List of events from channels below the threshold (to be re-enqueued)
        """
        summary: dict = {
            "type": "server_activity_summary",
            "description": "Summary of recently active channels and users. Notifies about which channels have had activity and who has been active there.",
            "channels": {},
        }
        # Track which events correspond to which channels
        channel_events: dict[int, list[Event]] = {}

        for event in events:
            channel_id = event.data.get("channel_id")
            message_id = event.data.get("message_id")
            if not message_id or not channel_id:
                continue
            # check the message hasn't been deleted
            try:
                await self.bot.wait_until_ready()
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue
                message = await channel.fetch_message(message_id)  # type: ignore
            except discord.NotFound:
                continue
            except discord.DiscordException:
                log.warning("Could not fetch message %d to build activity summary.", message_id)
                continue
            except Exception as e:
                log.exception(
                    "Exception fetching message %d for activity summary: %s",
                    message_id,
                    str(e),
                )
                continue

            channel_id = message.channel.id
            channel_name = getattr(message.channel, "name", "dm")
            if channel_id not in summary["channels"]:
                summary["channels"][channel_id] = {
                    "channel_name": channel_name,
                    "activity_summary": {
                        "total_messages": 0,
                        "active_users": Counter(),
                        "last_message_time": None,
                        "last_message_user": None,
                    },
                }
                channel_events[channel_id] = []

            # Track this event for this channel
            channel_events[channel_id].append(event)

            channel_summary = summary["channels"][channel_id]["activity_summary"]

            # Update channel activity summary
            author = message.author
            channel_summary["total_messages"] += 1
            channel_summary["active_users"][f"{author.id=} ({author.display_name=} | {author.global_name=})"] += 1
            # Ensure comparison is done with datetime objects
            prev_time = channel_summary["last_message_time"]
            latest_time = self.compare_message_timestamps(message.created_at, prev_time)
            channel_summary["last_message_time"] = latest_time.isoformat()
            channel_summary["last_message_user"] = f"{author.id=} ({author.display_name=} | {author.global_name=})"

        # Separate channels that meet threshold from those that don't
        channels_below_threshold = [
            channel_id
            for channel_id, channel_data in summary["channels"].items()
            if channel_data["activity_summary"]["total_messages"] < threshold
        ]

        # Filter out channels below the threshold from summary
        summary["channels"] = {
            channel_id: channel_data
            for channel_id, channel_data in summary["channels"].items()
            if channel_data["activity_summary"]["total_messages"] >= threshold
        }

        # Collect events from channels below threshold to re-enqueue
        events_to_reenqueue = []
        for channel_id in channels_below_threshold:
            events_to_reenqueue.extend(channel_events.get(channel_id, []))

        # If no channels meet the threshold, return an empty summary
        if not summary["channels"]:
            return {}, events_to_reenqueue
        return summary, events_to_reenqueue

    def compare_message_timestamps(self, message_created_at: datetime, prev_time: datetime | str | None) -> datetime:
        """Compare a message timestamp with a previous timestamp and return the later datetime.

        Args:
            message: The message object containing the timestamp to compare.
            prev_time: The previous timestamp to compare against, can be a string, datetime, or None.

        Returns:
            The later of the parsed prev_time and message.created_at.
        """
        # ensure we have offset-aware datetimes for comparison
        if not message_created_at.tzinfo:
            message_created_at = message_created_at.replace(tzinfo=timezone.utc)

        if prev_time is not None and isinstance(prev_time, str):
            try:
                prev_time_dt = datetime.fromisoformat(prev_time)
            except Exception:
                prev_time_dt = datetime.min.replace(tzinfo=timezone.utc)
        elif isinstance(prev_time, datetime):
            prev_time_dt = prev_time
        else:
            prev_time_dt = datetime.min.replace(tzinfo=timezone.utc)
        latest_time = max(prev_time_dt, message_created_at)
        return latest_time

    # endregion

    # region: Commands

    @commands.group(name="aurora")  # type: ignore
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def aurora(self, ctx: commands.Context):
        """Manage Aurora agent and event system."""
        pass

    @aurora.group(name="queue")
    @commands.is_owner()
    async def aurora_queue(self, ctx: commands.Context):
        """Manage the global message queue (bot owner only)."""
        pass

    @aurora_queue.command(name="status")
    async def queue_status(self, ctx: commands.Context):
        """Show current queue state and statistics for all event types."""
        if not self.queue:
            await ctx.send("❌ Event queue not initialized.")
            return

        all_stats = self._get_event_stats()  # Get all event types

        embed = discord.Embed(
            title="📊 Aurora Event Queue Status",
            color=discord.Color.blue(),
        )

        # Global status fields
        embed.add_field(
            name="Events Paused",
            value="✅ Yes" if self._events_paused else "❌ No",
            inline=True,
        )

        # Get global tracking stats from any event type (they're shared)
        if all_stats:
            first_stats = next(iter(all_stats.values()))
            embed.add_field(
                name="Tracked Channels",
                value=str(first_stats.get("tracked_channels", 0)),
                inline=True,
            )
            embed.add_field(
                name="Tracked Event IDs",
                value=str(first_stats.get("tracked_event_ids", 0)),
                inline=True,
            )
        else:
            embed.add_field(name="Tracked Channels", value="0", inline=True)
            embed.add_field(name="Tracked Event IDs", value="0", inline=True)

        # Add a field for each event type queue
        total_pending = 0
        if all_stats:
            for event_type, stats in sorted(all_stats.items()):
                queue_size = stats.get("queue_size", 0)
                max_size = stats.get("max_size", 0)
                rate_limit = stats.get("rate_limit_seconds", "?")
                last_processed = stats.get("last_processed", "Never")

                total_pending += queue_size

                # Format the event type name for display
                display_name = event_type.replace("_", " ").title()
                if "server_activity" in event_type:
                    # Extract guild ID from server_activity_{guild_id}
                    display_name = "🔔 " + display_name
                elif event_type == "message":
                    display_name = "💬 Message"
                else:
                    display_name = "📋 " + display_name

                max_display = f"/{max_size}" if max_size > 0 else " (unbounded)"
                queue_info = (
                    f"**Size:** {queue_size}{max_display}\n"
                    f"**Rate Limit:** {rate_limit}s\n"
                    f"**Last Processed:** {last_processed if last_processed else 'Never'}"
                )
                embed.add_field(
                    name=display_name,
                    value=queue_info,
                    inline=True,
                )
        else:
            embed.add_field(
                name="No Queues",
                value="No event queues have been initialized yet.",
                inline=False,
            )

        # Set description based on overall queue state
        if total_pending == 0:
            embed.description = "✨ All queues empty - all events processed!"
        else:
            embed.description = f"⚠️ {total_pending} event(s) waiting to be processed across all queues."

        await ctx.send(embed=embed)

    @aurora_queue.command(name="clear")
    async def queue_clear(self, ctx: commands.Context):
        """Clear all pending messages from the queue."""
        if not self.queue:
            await ctx.send("❌ Message queue not initialized.")
            return

        initial_size = self.queue.size("message")
        self.queue.clear("message")

        await ctx.send(f"✅ Cleared {initial_size} message(s) from the queue.")
        log.info(f"Queue cleared by {ctx.author}")

    @aurora.group(name="events")
    @commands.is_owner()
    async def aurora_events(self, ctx: commands.Context):
        """Manage global event processing (bot owner only)."""
        pass

    @aurora_events.command(name="pause")
    async def events_pause(self, ctx: commands.Context):
        """Temporarily pause event processing globally."""
        if self._events_paused:
            await ctx.send("ℹ️ Event processing is already paused.")
            return

        self._events_paused = True
        await ctx.send(
            "⏸️ **Global event processing paused.** The bot will not respond to mentions or DMs "
            "in any server until you run `aurora events resume`."
        )
        log.info(f"Event processing paused globally by {ctx.author}")

    @aurora_events.command(name="resume")
    async def events_resume(self, ctx: commands.Context):
        """Resume event processing globally."""
        if not self._events_paused:
            await ctx.send("ℹ️ Event processing is not paused.")
            return

        self._events_paused = False
        await ctx.send("▶️ **Global event processing resumed.** The bot will now respond to mentions and DMs.")
        log.info(f"Event processing resumed globally by {ctx.author}")

    @aurora_events.command(name="status")
    async def events_status(self, ctx: commands.Context, guild_id: int | None = None):
        """Show global event system status and optionally specific guild status.

        Parameters:
        - guild_id: Optional guild ID to show configuration for
        """
        embed = discord.Embed(
            title="⚙️ Aurora Event System Status (Global)",
            color=discord.Color.green(),
        )

        # Global event processing status
        embed.add_field(
            name="Event Processing",
            value="▶️ Active" if not self._events_paused else "⏸️ Paused (Global)",
            inline=True,
        )

        # Global queue status
        if self.queue:
            stats = self._get_event_stats("message")
            embed.add_field(
                name="Queue",
                value=f"{stats['queue_size']}/{stats['max_size']} messages",
                inline=True,
            )
            embed.add_field(
                name="Tracked Channels",
                value=str(stats["tracked_channels"]),
                inline=True,
            )

        # Error handling status (global)
        circuit_status = self.circuit_breaker.get_status()
        error_state_emoji = {
            "closed": "🟢",
            "open": "🔴",
            "half_open": "🟡",
        }
        error_rate = await self.error_stats.get_error_rate(300)
        error_text = (
            f"**Circuit Breaker:** {error_state_emoji.get(circuit_status['state'], '❓')} {circuit_status['state'].upper()}\n"
            f"**Recent Failures:** {circuit_status['failure_count']}\n"
            f"**Error Rate (5min):** {error_rate:.1f}%"
        )
        embed.add_field(
            name="Error Handling (Global)",
            value=error_text,
            inline=False,
        )

        # Guild-specific status if requested
        if guild_id:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                embed.add_field(
                    name=f"Guild {guild_id}",
                    value="❌ Guild not found or bot not in that guild",
                    inline=False,
                )
            else:
                guild_config = await self.config.guild(guild).all()
                agent_id = guild_config.get("agent_id")

                guild_status = (
                    f"**Name:** {guild.name}\n"
                    f"**Agent:** {f'✅ Enabled (`{agent_id[:8]}...`)' if guild_config.get('enabled') and agent_id else '❌ Disabled'}\n"
                    f"**Reply Depth:** {guild_config.get('reply_thread_depth', 5)}\n"
                    f"**Typing Indicator:** {'✅' if guild_config.get('enable_typing_indicator', True) else '❌'}\n"
                    f"**DM Responses:** {'✅' if guild_config.get('enable_dm_responses', True) else '❌'}\n"
                    f"**MCP Guidance:** {'✅' if guild_config.get('mcp_guidance_enabled', True) else '❌'}\n"
                    f"**Rate Limit:** {guild_config.get('rate_limit_seconds', 2)}s\n"
                    f"**Agent Timeout:** {guild_config.get('agent_timeout', 60)}s"
                )
                embed.add_field(
                    name=f"Guild: {guild.name} ({guild_id})",
                    value=guild_status,
                    inline=False,
                )
        elif ctx.guild:
            # If no guild_id provided but invoked in a guild, show that guild's status
            guild_config = await self.config.guild(ctx.guild).all()
            agent_id = guild_config.get("agent_id")

            guild_status = (
                f"**Agent:** {f'✅ Enabled (`{agent_id[:8]}...`)' if guild_config.get('enabled') and agent_id else '❌ Disabled'}\n"
                f"**Reply Depth:** {guild_config.get('reply_thread_depth', 5)}\n"
                f"**Typing Indicator:** {'✅' if guild_config.get('enable_typing_indicator', True) else '❌'}\n"
                f"**DM Responses:** {'✅' if guild_config.get('enable_dm_responses', True) else '❌'}\n"
                f"**MCP Guidance:** {'✅' if guild_config.get('mcp_guidance_enabled', True) else '❌'}\n"
                f"**Rate Limit:** {guild_config.get('rate_limit_seconds', 2)}s\n"
                f"**Agent Timeout:** {guild_config.get('agent_timeout', 60)}s"
            )
            embed.add_field(
                name=f"Current Guild: {ctx.guild.name} ({ctx.guild.id})",
                value=guild_status,
                inline=False,
            )
        else:
            embed.add_field(
                name="Guild Config",
                value="💡 Use `aurora events status <guild_id>` to see guild-specific configuration",
                inline=False,
            )

        await ctx.send(embed=embed)

    @aurora_events.command(name="errors")
    async def events_errors(self, ctx: commands.Context):
        """Show detailed error statistics."""
        stats = await self.error_stats.get_stats()
        circuit_status = self.circuit_breaker.get_status()

        embed = discord.Embed(
            title="📊 Error Statistics",
            color=discord.Color.red() if circuit_status["state"] != "closed" else discord.Color.green(),
        )

        # Overall stats
        embed.add_field(
            name="Total Operations",
            value=str(stats["total_operations"]),
            inline=True,
        )
        embed.add_field(
            name="Total Errors",
            value=str(stats["total_errors"]),
            inline=True,
        )
        embed.add_field(
            name="Overall Error Rate",
            value=f"{stats['recent_error_rate']:.1f}%",
            inline=True,
        )

        # Time-windowed error rates
        embed.add_field(
            name="Error Rate (Last 5 min)",
            value=f"{stats['error_rate_5min']:.1f}%",
            inline=True,
        )

        # Circuit breaker
        state_emoji = {
            "closed": "🟢 CLOSED",
            "open": "🔴 OPEN",
            "half_open": "🟡 HALF-OPEN",
        }
        embed.add_field(
            name="Circuit Breaker",
            value=state_emoji.get(circuit_status["state"], "❓ UNKNOWN"),
            inline=True,
        )
        embed.add_field(
            name="Circuit Failures",
            value=str(circuit_status["failure_count"]),
            inline=True,
        )

        # Error breakdown by type
        if stats["error_by_type"]:
            error_breakdown = "\n".join(
                [
                    f"**{error_type}:** {count}"
                    for error_type, count in sorted(stats["error_by_type"].items(), key=lambda x: x[1], reverse=True)[
                        :5
                    ]  # Top 5 error types
                ]
            )
            embed.add_field(
                name="Top Error Types",
                value=error_breakdown or "None",
                inline=False,
            )

        # Next retry time if circuit is open
        if circuit_status["state"] == "open" and circuit_status["next_retry"]:
            embed.add_field(
                name="Next Retry Attempt",
                value=circuit_status["next_retry"],
                inline=False,
            )

        await ctx.send(embed=embed)

    @aurora_events.command(name="resetcircuit")
    async def events_reset_circuit(self, ctx: commands.Context):
        """Manually reset the circuit breaker."""
        old_state = self.circuit_breaker.state
        self.circuit_breaker.state = self.circuit_breaker.CLOSED
        self.circuit_breaker.failure_count = 0
        self.circuit_breaker.last_failure_time = None

        await ctx.send(
            f"✅ Circuit breaker reset from `{old_state}` to `CLOSED`.\n"
            f"⚠️ Use this command carefully - the circuit breaker opened for a reason."
        )
        log.warning(f"Circuit breaker manually reset by {ctx.author} (was {old_state})")

    @aurora.group(name="config")
    async def aurora_config(self, ctx: commands.Context):
        """Configure event system settings."""
        pass

    @aurora_config.command(name="replydepth")
    async def config_reply_depth(self, ctx: commands.Context, depth: int):
        """Set maximum reply thread depth to fetch.

        Parameters:
        - depth: Number of parent messages to fetch (1-10)
        """
        if not 1 <= depth <= 10:
            await ctx.send("❌ Reply depth must be between 1 and 10.")
            return
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a guild.")
            return
        await self.config.guild(ctx.guild).reply_thread_depth.set(depth)  # type: ignore
        await ctx.send(f"✅ Reply thread depth set to {depth} messages.")
        log.info(f"Reply depth set to {depth} by {ctx.author} in guild {ctx.guild.name} ({ctx.guild.id})")

    @aurora_config.command(name="typing")
    async def config_typing(self, ctx: commands.Context, enabled: bool):
        """Enable or disable typing indicator while processing.

        Parameters:
        - enabled: True to enable, False to disable
        """
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a guild.")
            return
        await self.config.guild(ctx.guild).enable_typing_indicator.set(enabled)
        status = "enabled" if enabled else "disabled"
        await ctx.send(f"✅ Typing indicator {status}.")
        log.info(f"Typing indicator {status} by {ctx.author} in guild {ctx.guild.name} ({ctx.guild.id})")

    @aurora_config.command(name="ratelimit")
    async def config_rate_limit(self, ctx: commands.Context, seconds: float):
        """Set minimum seconds between messages per channel.

        Parameters:
        - seconds: Minimum seconds (0.5-10)
        """
        if not 0.5 <= seconds <= 10:
            await ctx.send("❌ Rate limit must be between 0.5 and 10 seconds.")
            return
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a guild.")
            return
        await self.config.guild(ctx.guild).rate_limit_seconds.set(seconds)

        # Update queue rate limit if initialized
        if self.queue:
            # Update EventQueue default rate limit value and adjust existing per-channel rate limits
            try:
                self.queue.default_rate_limit = seconds
                for k in list(self.queue.rate_limits.keys()):
                    if str(k).startswith("channel_"):
                        self.queue.rate_limits[k] = seconds
            except Exception:
                log.exception("Error updating queue rate limits")

        await ctx.send(f"✅ Rate limit set to {seconds} seconds per channel.")
        log.info(f"Rate limit set to {seconds}s by {ctx.author} in guild {ctx.guild.name} ({ctx.guild.id})")

    @aurora_config.command(name="queuesize")
    async def config_queue_size(self, ctx: commands.Context, size: int):
        """Set maximum queue size.

        Parameters:
        - size: Maximum queued messages (10-200)
        """
        if not 10 <= size <= 200:
            await ctx.send("❌ Queue size must be between 10 and 200.")
            return
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a guild.")
            return
        await self.config.guild(ctx.guild).max_queue_size.set(size)
        await ctx.send(
            f"✅ Maximum queue size set to {size}.\n" f"⚠️ Note: Queue size change requires cog reload to take effect."
        )
        log.info(f"Queue size set to {size} by {ctx.author} in guild {ctx.guild.name} ({ctx.guild.id})")

    @aurora_config.command(name="timeout")
    async def config_timeout(self, ctx: commands.Context, seconds: int):
        """Set agent execution timeout.

        Parameters:
        - seconds: Maximum execution time (10-300)
        """
        if not 10 <= seconds <= 300:
            await ctx.send("❌ Timeout must be between 10 and 300 seconds.")
            return
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a guild.")
            return
        await self.config.guild(ctx.guild).agent_timeout.set(seconds)
        await ctx.send(f"✅ Agent timeout set to {seconds} seconds.")
        log.info(f"Agent timeout set to {seconds}s by {ctx.author} in guild {ctx.guild.name} ({ctx.guild.id})")

    @aurora_config.command(name="mcpguidance")
    async def config_mcp_guidance(self, ctx: commands.Context, enabled: bool):
        """Enable or disable MCP tool guidance in prompts.

        Parameters:
        - enabled: True to enable, False to disable
        """
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a guild.")
            return
        await self.config.guild(ctx.guild).mcp_guidance_enabled.set(enabled)
        status = "enabled" if enabled else "disabled"
        await ctx.send(
            f"✅ MCP tool guidance {status}.\n"
            f"ℹ️ When enabled, prompts include hints about using discord_read_messages() and discord_send() tools."
        )
        log.info(f"MCP guidance {status} by {ctx.author} in guild {ctx.guild.name} ({ctx.guild.id})")

    @aurora_config.command(name="show")
    async def config_show(self, ctx: commands.Context, guild_id: int | None = None):
        """Show current configuration for this guild or a specified guild.

        Parameters:
        - guild_id: Optional guild ID to show configuration for (owner only)
        """
        # If guild_id is provided, only owner can use it
        if guild_id is not None and not await self.bot.is_owner(ctx.author):
            await ctx.send("❌ Only the bot owner can view other guilds' configurations.")
            return

        # Determine which guild to show config for
        if guild_id:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                await ctx.send(f"❌ Guild with ID {guild_id} not found or bot not in that guild.")
                return
        else:
            if not ctx.guild:
                await ctx.send("❌ This command must be used in a guild or with a guild_id parameter.")
                return
            guild = ctx.guild

        guild_config = await self.config.guild(guild).all()

        embed = discord.Embed(
            title=f"⚙️ Aurora Configuration: {guild.name}",
            color=discord.Color.blue(),
        )

        # Agent settings
        agent_id = guild_config.get("agent_id")
        # synthesis task
        synthesis_task = self._get_task(self.synthesis, guild.id)
        if not synthesis_task:
            synthesis_task = None
            log.info("No synthesis task found for guild %d", guild.id)
        # activity tracking task
        activity_task = self._get_task(self.track_server_activity, guild.id)
        if not activity_task:
            activity_task = None
            log.info("No activity tracking task found for guild %d", guild.id)
        # Get last synthesis timestamp from queue
        synthesis_event_type = EventType.SYNTHESIS.format(guild_id=guild.id)
        last_synthesis_dt = (
            self.queue.last_processed.get(synthesis_event_type, datetime.min) if self.queue else datetime.min
        )
        last_synthesis_ts = last_synthesis_dt.timestamp() if last_synthesis_dt != datetime.min else 0
        # Get last activity tracking timestamp from queue
        activity_event_type = EventType.SERVER_ACTIVITY.format(guild_id=guild.id)
        last_activity_dt = (
            self.queue.last_processed.get(activity_event_type, datetime.min) if self.queue else datetime.min
        )
        last_activity_ts = last_activity_dt.timestamp() if last_activity_dt != datetime.min else 0
        agent_status = (
            (
                f"✅ Enabled\nAgent ID: `{agent_id}`\n"
                f"Synthesis Task: {'Running' if synthesis_task else 'Not Running'}\n"
                f"Synthesis Interval: `every {humanize_timedelta(seconds=guild_config.get('synthesis_interval', 3600))}`\n"
                f"Last Synthesis: {format_dt(datetime.fromtimestamp(last_synthesis_ts, tz=timezone.utc), 'F') if last_synthesis_ts > 0 else 'Never'}\n"
                f"Next Synthesis: {format_dt(datetime.fromtimestamp(last_synthesis_ts + guild_config.get('synthesis_interval', 3600), tz=timezone.utc), 'F') if last_synthesis_ts > 0 else 'N/A'}\n"
                f"Activity Tracking Task: {'Running' if activity_task else 'Not Running'}\n"
                f"Activity Tracking Interval: `every {humanize_timedelta(seconds=guild_config.get('server_activity_interval', 3600))}`\n"
                f"Activity Threshold: {guild_config.get('activity_threshold', 1)} messages/channel\n"
                f"Last Activity Tracking: {format_dt(datetime.fromtimestamp(last_activity_ts, tz=timezone.utc), 'F') if last_activity_ts > 0 else 'Never'}\n"
                f"Next Activity Tracking: {format_dt(datetime.fromtimestamp(last_activity_ts + guild_config.get('server_activity_interval', 3600), tz=timezone.utc), 'F') if last_activity_ts > 0 else 'N/A'}"
            )
            if guild_config.get("enabled") and agent_id
            else "❌ Disabled"
        )
        embed.add_field(
            name="Agent Status",
            value=agent_status,
            inline=False,
        )

        # Event system settings
        event_settings = (
            f"**Reply Thread Depth:** {guild_config.get('reply_thread_depth', 5)}\n"
            f"**Typing Indicator:** {'✅ Enabled' if guild_config.get('enable_typing_indicator', True) else '❌ Disabled'}\n"
            f"**DM Responses:** {'✅ Enabled' if guild_config.get('enable_dm_responses', True) else '❌ Disabled'}\n"
            f"**MCP Guidance:** {'✅ Enabled' if guild_config.get('mcp_guidance_enabled', True) else '❌ Disabled'}"
        )
        embed.add_field(
            name="Event System",
            value=event_settings,
            inline=False,
        )

        # Performance settings
        perf_settings = (
            f"**Rate Limit:** {guild_config.get('rate_limit_seconds', 2)}s per channel\n"
            f"**Max Queue Size:** {guild_config.get('max_queue_size', 50)} messages\n"
            f"**Agent Timeout:** {guild_config.get('agent_timeout', 60)}s"
        )
        embed.add_field(
            name="Performance",
            value=perf_settings,
            inline=False,
        )

        # Global settings (owner only)
        if await self.bot.is_owner(ctx.author):
            global_config = await self.config.all()
            global_settings = f"**Letta Base URL:** {global_config.get('letta_base_url', 'Not set')}"
            embed.add_field(
                name="Global Settings (Owner)",
                value=global_settings,
                inline=False,
            )

        embed.set_footer(text=f"Guild ID: {guild.id}")
        await ctx.send(embed=embed)

    @aurora.command(name="enable")
    async def enable_agent(self, ctx: commands.Context, agent_id: str):
        """Enable Aurora agent for this guild.

        Parameters:
        - agent_id: The Letta agent ID to use for this guild
        """
        if not ctx.guild:
            await ctx.send("❌ This command must be used in a guild.")
            return

        # Validate agent_id format (basic check)
        if not agent_id or len(agent_id) < 8:
            await ctx.send("❌ Invalid agent ID. Please provide a valid Letta agent ID.")
            return

        await self.config.guild(ctx.guild).agent_id.set(agent_id)
        await self.config.guild(ctx.guild).enabled.set(True)

        await ctx.send(
            f"✅ Aurora agent enabled for {ctx.guild.name}!\n"
            f"Agent ID: `{agent_id}`\n\n"
            f"The bot will now respond to mentions and DMs (if configured)."
        )
        log.info(f"Agent {agent_id} enabled for guild {ctx.guild.name} ({ctx.guild.id}) by {ctx.author}")

        # Start synthesis tasks if Letta is initialized
        if self.letta:
            guild_config = await self.config.guild(ctx.guild).all()
            if guild_config.get("enabled") and guild_config.get("agent_id"):
                synthesis_interval = guild_config.get("synthesis_interval", 3600)
                self._get_or_create_task(
                    self.synthesis,
                    ctx.guild.id,
                    synthesis_interval,
                    before_coro=self.before_synthesis,
                )
                activity_interval = guild_config.get("server_activity_interval", 3600)
                self._get_or_create_task(
                    self.track_server_activity,
                    ctx.guild.id,
                    activity_interval,
                    before_coro=self.before_activity_tracking,
                )

    @aurora.command(name="disable")
    async def disable_agent(self, ctx: commands.Context):
        """Disable Aurora agent for this guild."""
        if not ctx.guild:
            await ctx.send("❌ This command must be used in a guild.")
            return

        guild_config = await self.config.guild(ctx.guild).all()
        if not guild_config.get("enabled"):
            await ctx.send("ℹ️ Aurora agent is not currently enabled for this guild.")
            return

        await self.config.guild(ctx.guild).enabled.set(False)

        # Stop synthesis task
        self._remove_task(self.synthesis, ctx.guild.id)
        # Stop activity tracking task
        self._remove_task(self.track_server_activity, ctx.guild.id)

        await ctx.send(
            f"✅ Aurora agent disabled for {ctx.guild.name}.\n" f"The bot will no longer respond to mentions or DMs."
        )
        log.info(f"Agent disabled for guild {ctx.guild.name} ({ctx.guild.id}) by {ctx.author}")

    @aurora.command(name="setsynthesisinterval")
    async def set_synthesis_interval(self, ctx: commands.Context, seconds: int):
        """Set synthesis interval in seconds.

        Parameters:
        - seconds: Interval in seconds (600-86400)
        """
        if not ctx.guild:
            await ctx.send("❌ This command must be used in a guild.")
            return

        if not 600 <= seconds <= 86400:
            await ctx.send("❌ Interval must be between 600 and 86400 seconds (10s to 24h).")
            return

        await self.config.guild(ctx.guild).synthesis_interval.set(seconds)

        # Update synthesis task if running
        guild_config = await self.config.guild(ctx.guild).all()
        if guild_config.get("enabled") and self.letta:
            # get the existing task
            task = self._get_task(self.synthesis, ctx.guild.id)
            if task:
                task.change_interval(seconds=seconds)
                log.info(f"Synthesis task interval updated to {seconds}s for guild {ctx.guild.name} ({ctx.guild.id})")

        await ctx.send(f"✅ Synthesis interval set to {seconds} seconds.")
        log.info(f"Synthesis interval set to {seconds}s by {ctx.author} in guild {ctx.guild.name} ({ctx.guild.id})")

    @aurora.command(name="setactivity")
    async def set_activity(self, ctx: commands.Context, seconds: int, threshold: int = 1):
        """Set activity tracking interval in seconds.

        Parameters:
        - seconds: Interval in seconds (600-86400)
        - threshold: Message threshold for activity tracking (1-100)
        """
        if not ctx.guild:
            await ctx.send("❌ This command must be used in a guild.")
            return

        if not 600 <= seconds <= 86400:
            await ctx.send("❌ Interval must be between 600 and 86400 seconds (10s to 24h).")
            return

        await self.config.guild(ctx.guild).server_activity_interval.set(seconds)
        await self.config.guild(ctx.guild).activity_threshold.set(threshold)

        # Update activity task if running
        guild_config = await self.config.guild(ctx.guild).all()
        if guild_config.get("enabled") and self.letta:
            # get the existing task
            task = self._get_task(self.track_server_activity, ctx.guild.id)
            if task:
                task.change_interval(seconds=seconds)
                log.info(
                    f"Activity tracking task interval updated to {seconds}s for guild {ctx.guild.name} ({ctx.guild.id})"
                )

        await ctx.send(f"✅ Activity tracking interval set to {seconds} seconds, threshold {threshold} messages.")
        log.info(
            f"Activity tracking interval set to {seconds}s, threshold {threshold} messages by {ctx.author} in guild {ctx.guild.name} ({ctx.guild.id}"
        )

    @aurora.command(name="setagent")
    async def set_agent(self, ctx: commands.Context, agent_id: str):
        """Change the Letta agent ID for this guild.

        Parameters:
        - agent_id: The new Letta agent ID to use
        """
        if not ctx.guild:
            await ctx.send("❌ This command must be used in a guild.")
            return

        # Validate agent_id format (basic check)
        if not agent_id or len(agent_id) < 8:
            await ctx.send("❌ Invalid agent ID. Please provide a valid Letta agent ID.")
            return

        old_agent_id = await self.config.guild(ctx.guild).agent_id()
        await self.config.guild(ctx.guild).agent_id.set(agent_id)

        # Restart tasks if agent is enabled
        guild_config = await self.config.guild(ctx.guild).all()
        if guild_config.get("enabled") and self.letta:
            # get the existing task
            synthesis_task = self._get_task(self.synthesis, ctx.guild.id)
            if synthesis_task:
                synthesis_task.restart()
                log.info(f"Synthesis task restarted for guild {ctx.guild.name} ({ctx.guild.id})")

            activity_task = self._get_or_create_task(
                self.track_server_activity,
                ctx.guild.id,
                before_coro=self.before_activity_tracking,
            )
            if activity_task:
                activity_task.restart()
                log.info(f"Activity tracking task restarted for guild {ctx.guild.name} ({ctx.guild.id})")

        await ctx.send(
            f"✅ Agent ID updated for {ctx.guild.name}!\n" f"Old: `{old_agent_id or 'None'}`\n" f"New: `{agent_id}`"
        )
        log.info(
            f"Agent ID changed from {old_agent_id} to {agent_id} for guild {ctx.guild.name} ({ctx.guild.id}) by {ctx.author}"
        )

    @aurora.group(name="global")
    @commands.is_owner()
    async def aurora_global(self, ctx: commands.Context):
        """Global Aurora settings (bot owner only)."""
        pass

    @aurora_global.command(name="baseurl")
    async def global_base_url(self, ctx: commands.Context, url: str | None = None):
        """Get or set the Letta base URL.

        Parameters:
        - url: The new Letta base URL (e.g., https://api.letta.ai/v1 or http://localhost:8283)
        """
        if url is None:
            # Show current URL
            current_url = await self.config.letta_base_url()
            await ctx.send(f"Current Letta base URL: `{current_url}`")
            return

        # Validate URL format
        if not url.startswith(("http://", "https://")):
            await ctx.send("❌ Invalid URL. Must start with http:// or https://")
            return

        # Remove trailing slash if present
        url = url.rstrip("/")

        old_url = await self.config.letta_base_url()
        await self.config.letta_base_url.set(url)

        await ctx.send(
            f"✅ Letta base URL updated!\n"
            f"Old: `{old_url}`\n"
            f"New: `{url}`\n\n"
            f"⚠️ Reload the cog for this change to take effect: `{ctx.prefix}reload aurora`"
        )
        log.info(f"Letta base URL changed from {old_url} to {url} by {ctx.author}")

    @aurora_global.command(name="show")
    async def global_show(self, ctx: commands.Context):
        """Show all global Aurora settings."""
        global_config = await self.config.all()

        embed = discord.Embed(
            title="🌐 Aurora Global Settings",
            color=discord.Color.purple(),
        )

        embed.add_field(
            name="Letta Base URL",
            value=f"`{global_config.get('letta_base_url', 'Not set')}`",
            inline=False,
        )

        # Add circuit breaker settings
        circuit_status = self.circuit_breaker.get_status()
        circuit_info = (
            f"**Failure Threshold:** {self.circuit_breaker.failure_threshold}\n"
            f"**Recovery Timeout:** {self.circuit_breaker.recovery_timeout}s\n"
            f"**Half-Open Attempts:** {self.circuit_breaker.half_open_attempts}\n"
            f"**Current State:** {circuit_status['state'].upper()}"
        )
        embed.add_field(
            name="Circuit Breaker Configuration",
            value=circuit_info,
            inline=False,
        )

        # Add retry configuration
        retry_info = (
            f"**Max Attempts:** {self.retry_config.max_attempts}\n"
            f"**Base Delay:** {self.retry_config.base_delay}s\n"
            f"**Exponential Base:** {self.retry_config.exponential_base}x\n"
            f"**Max Delay:** {self.retry_config.max_delay}s\n"
            f"**Jitter:** {'✅ Enabled' if self.retry_config.jitter else '❌ Disabled'}"
        )
        embed.add_field(
            name="Retry Configuration",
            value=retry_info,
            inline=False,
        )

        await ctx.send(embed=embed)

    @aurora.command(name="context")
    async def context_preview(self, ctx: commands.Context, message_id: str):
        """Preview what context would be sent to the agent for a message.

        Parameters:
        - message_id: The ID of the message to preview context for
        """
        try:
            # Try to find the message in the current channel first
            message = await ctx.channel.fetch_message(int(message_id))
        except (discord.NotFound, discord.HTTPException, ValueError):
            await ctx.send("❌ Message not found in this channel. Make sure the ID is correct.")
            return

        if not ctx.guild:
            await ctx.send("❌ This command must be used in a guild.")
            return

        try:
            guild_config = await self.config.guild(ctx.guild).all()
            max_reply_depth = guild_config.get("reply_thread_depth", 5)

            # Extract context
            context = await build_event_context(message, max_reply_depth=max_reply_depth)

            # Build prompt
            event_type = "mention"  # Assume mention for preview
            include_mcp_guidance = guild_config.get("mcp_guidance_enabled", True)
            prompt = build_prompt(
                interaction_type=event_type,
                message_content=message.content,
                context=context,
                include_mcp_guidance=include_mcp_guidance,
            )

            # Create preview embed
            embed = discord.Embed(
                title="🔍 Context Preview",
                description=f"Preview of context that would be sent to the agent for message `{message_id}`",
                color=discord.Color.blue(),
            )

            # Metadata
            metadata = context[0]
            embed.add_field(
                name="Author",
                value=f"{metadata.author.display_name} (ID: {metadata.author.id})",
                inline=True,
            )
            embed.add_field(
                name="Channel",
                value=f"#{metadata.channel.name}",
                inline=True,
            )
            embed.add_field(
                name="Timestamp",
                value=metadata.timestamp,
                inline=True,
            )

            # Reply chain
            reply_chain = context[1]
            embed.add_field(
                name="Reply Chain",
                value=f"{len(reply_chain)} parent message(s)" if reply_chain else "No reply chain",
                inline=False,
            )

            # Show truncated prompt
            prompt_preview = prompt[:1000] + "..." if len(prompt) > 1000 else prompt
            embed.add_field(
                name="Generated Prompt (truncated)",
                value=f"```\n{prompt_preview}\n```",
                inline=False,
            )

            embed.set_footer(text=f"Full prompt length: {len(prompt)} characters")

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ Error generating context preview: {str(e)}")
            log.exception(f"Error in context preview for message {message_id}: {e}")

    # endregion

    # region: Event listeners
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for message events and queue them for the agent."""
        # Skip if events are paused
        if self._events_paused:
            return

        # Skip messages from bots (including self)
        if message.author.bot:
            return

        # Skip if Letta client not initialized
        if not self.letta or not self.queue:
            return

        # Check if this is a Red command - don't interfere
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # Determine event type
        is_dm = isinstance(message.channel, (discord.DMChannel, discord.GroupChannel))
        is_mention = (
            self.bot.user in message.mentions
            or (
                message.reference
                and message.reference.resolved
                and isinstance(message.reference.resolved, discord.Message)
                and message.reference.resolved.author == self.bot.user
            )
            if not is_dm
            else False
        )
        # Check if this is the first reply in a thread created from a bot message
        is_first_thread_reply = (
            message.type == discord.MessageType.default
            and isinstance(message.channel, discord.Thread)
            and message.channel.id
            and message.channel.parent
            and isinstance(message.channel.parent, discord.TextChannel)
            and (await self.is_bot_thread_starter(message))
            # this is the first message in the thread
            # i.e., the thread starter message is the most recent message in the channel except for this one
            # kinda hacky but it works
            and (
                len(
                    [
                        msg
                        async for msg in message.channel.history(limit=2)
                        if msg.type == discord.MessageType.thread_starter_message
                    ]
                )
                == 1
            )
        )

        # If neither DM nor mention, track guild activity for periodic tasks
        if not is_dm and not is_mention and not is_first_thread_reply:
            if not self.queue:
                return

            # Enqueue guild activity event
            event = {
                "event_type": EventType.SERVER_ACTIVITY.format(guild_id=message.guild.id if message.guild else "dm"),
                "channel_id": message.channel.id,
                "message_id": message.id,
            }
            await self.queue.enqueue(event)
            return
        # If DM responses are disabled, skip
        if is_dm:
            if message.guild:
                # This should not happen, but guard anyway
                return
            # Check if DM responses are enabled globally or per guild
            # For DMs, we could check a global config or per-user config if needed
            # Here, we assume a global config for simplicity
            dm_responses_enabled = await self.config.enable_dm_responses()
            if not dm_responses_enabled:
                return

        try:
            # Get guild config (or use defaults for DMs)
            if message.guild:
                guild_config = await self.config.guild(message.guild).all()

                # Check if agent is enabled for this guild
                if not guild_config.get("enabled"):
                    return

                agent_id = guild_config.get("agent_id")
                if not agent_id:
                    log.debug(f"No agent configured for guild {message.guild.id}")
                    return
            else:
                # DM handling
                guild_config = {}
                # For DMs, we'd need a separate DM agent config - skip for now if not implemented
                log.debug("DM received but DM agent handling not yet implemented")
                return

            # Extract context
            max_reply_depth = guild_config.get("reply_thread_depth", 5)
            context = await build_event_context(message, max_reply_depth=max_reply_depth)

            # If we're in a thread, include the thread starter message in context if we're not over max depth
            if isinstance(message.channel, discord.Thread) and len(context[1]) < max_reply_depth:
                try:
                    thread_starter_msg = await message.channel.parent.fetch_message(message.channel.id)  # type: ignore
                    context[1].insert(thread_starter_msg)
                except Exception as e:
                    log.exception(f"Error fetching thread starter message: {e}")
                # if we're still under max depth, build context for the thread starter's reply chain as well and merge
                if len(context[1]) < max_reply_depth:
                    parent_context = await build_event_context(
                        thread_starter_msg,
                        max_reply_depth=max_reply_depth - len(context[1]),
                    )
                    # Merge parent reply chain
                    for msg in parent_context[1]:
                        context[1].insert(msg)

            # Build prompt
            interaction_type = "dm" if is_dm else "mention"
            include_mcp_guidance = guild_config.get("mcp_guidance_enabled", True)
            prompt = build_prompt(
                interaction_type=interaction_type,
                message_content=message.content,
                context=context,
                include_mcp_guidance=include_mcp_guidance,
            )

            # Create event for queue (only picklable data - no Discord objects)
            event = {
                "event_type": "message",
                "event_id": str(message.id),
                "message_id": message.id,
                "context": context,
                "prompt": prompt,
                "timestamp": message.created_at.isoformat(),
                "guild_id": message.guild.id if message.guild else None,
                "channel_id": message.channel.id,
                "agent_id": agent_id,
            }

            # Enqueue for processing
            success = await self.queue.enqueue(event)
            if success:
                channel_name = "DM" if is_dm else getattr(message.channel, "name", "Unknown")
                log.info(
                    f"Queued {interaction_type} from {message.author} in " f"{'DM' if is_dm else f'#{channel_name}'}"
                )
            else:
                log.warning(f"Failed to queue message {message.id} - queue full")

        except Exception as e:
            log.exception(f"Error processing message {message.id}: {e}")

    async def is_bot_thread_starter(self, message):
        try:
            return (await message.channel.parent.fetch_message(message.channel.id)).author == self.bot.user
        except discord.NotFound:
            return False
        except Exception as e:
            log.exception(f"Error checking if bot is thread starter for message {message.id}: {e}")
            return False

    # endregion

    # region: Message Processor
    @tasks.loop(seconds=5)
    async def process_message_queue(self):
        """Worker that processes messages from the queue."""
        if not self.letta or not self.queue or self.queue.is_empty("message"):
            return

        try:
            event = await self.queue.dequeue("message")
            channel_id = event.data["channel_id"]

            agent_id = event.data.get("agent_id")
            if not agent_id:
                log.warning(f"No agent ID in event for message {event.data.get('message_id')}")
                return

            # Rate limiting check
            rate_limit_key = f"channel_{channel_id}"
            if not self.queue.can_process(rate_limit_key):
                # Re-queue event for later, allow duplicate enqueue so we don't
                # skip messages that were already tracked as processed.
                await self.queue.enqueue(event, allow_duplicates=True)
                await asyncio.sleep(0.5)
                return

            # Fetch channel and message from IDs (we only store picklable data in queue)
            message_id = event.data["message_id"]
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(
                channel,
                (
                    discord.TextChannel,
                    discord.Thread,
                    discord.DMChannel,
                    discord.GroupChannel,
                ),
            ):
                log.warning(
                    f"Channel {channel_id} not found or not a messageable channel, skipping message {message_id}"
                )
                return

            try:
                # Fetch message to ensure it still exists
                message: discord.Message = await channel.fetch_message(message_id)
            except discord.NotFound:
                log.info(f"Message {message_id} was deleted, skipping")
                return
            except discord.Forbidden:
                log.warning(f"No permission to access message {message_id}, skipping")
                return

            # Show typing indicator while agent processes
            guild_id = event.data.get("guild_id")
            enable_typing = True
            if guild_id:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    guild_config = await self.config.guild(guild).all()
                    enable_typing = guild_config.get("enable_typing_indicator", True)

            if enable_typing:
                async with message.channel.typing():
                    # Send to Letta agent and monitor execution
                    await self.send_to_agent(agent_id, event.data["prompt"], guild_id)
            else:
                await self.send_to_agent(agent_id, event.data["prompt"], guild_id)

            # Update last processed timestamps:
            # - rate_limit_key for per-channel rate limiting
            # - "message" event type for stats display
            self.queue.mark_processed(rate_limit_key)
            self.queue.mark_processed("message")

        except Exception as e:
            log.exception(f"Error processing message from queue: {e}")
        finally:
            pass

    async def send_to_agent(self, agent_id: str, prompt: str, guild_id: int | None = None):
        """Send enriched prompt to Letta agent and monitor execution.

        The agent will use discord_send() MCP tool to respond directly.
        Includes retry logic and circuit breaker protection.
        """
        run_tracker: RunTracker = {"run_id": None, "task": None}

        try:
            agent_timeout = 60
            if guild_id:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    try:
                        guild_config = await self.config.guild(guild).all()
                        agent_timeout = guild_config.get("agent_timeout", 60)
                    except Exception as e:
                        log.error(f"Error fetching guild config for {guild_id}: {e}")

            # Wrapper to execute agent call and track task/run_id
            async def _execute_with_timeout(aid: str, prm: str, timeout: float):
                # Reset run tracking for this attempt
                run_tracker["run_id"] = None

                task = asyncio.create_task(self._execute_agent_call(aid, prm, run_tracker))
                run_tracker["task"] = task

                try:
                    await asyncio.wait_for(task, timeout=timeout)
                except asyncio.TimeoutError as exc:
                    raise TimeoutError("Agent execution timed out after configured timeout") from exc
                finally:
                    run_tracker["task"] = None

            async def _cleanup_after_failure(attempt: int, exception: Exception):
                task: asyncio.Task | None = run_tracker.get("task")
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                run_id = run_tracker.get("run_id")
                if run_id and self.letta:
                    try:
                        await self.letta.agents.messages.cancel(agent_id, run_ids=[run_id])
                        log.info(
                            "Cancelled Letta run %s for agent %s before retry",
                            run_id,
                            agent_id,
                        )
                    except Exception as cancel_err:
                        log.error(
                            "Failed to cancel Letta run %s for agent %s: %s",
                            run_id,
                            agent_id,
                            cancel_err,
                        )
                run_tracker["run_id"] = None

            # Execute with retry and circuit breaker
            await retry_with_backoff(
                lambda: _execute_with_timeout(agent_id, prompt, agent_timeout),
                self.retry_config,
                self.circuit_breaker,
                before_retry=_cleanup_after_failure,
            )
            run_tracker["run_id"] = None
            # Record success for stats
            await self.error_stats.record_success()

        except Exception as e:
            # Record error for stats
            await self.error_stats.record_error(e)
            log.exception(f"Fatal error during agent execution for agent {agent_id}: {e}")

            # Check if we should alert
            if await self.error_stats.should_alert(threshold=50.0):
                error_rate = await self.error_stats.get_error_rate(300)
                log.critical(
                    f"High error rate detected: {error_rate:.1f}% "
                    f"over last 5 minutes. Circuit breaker state: {self.circuit_breaker.state}"
                )
                # message the bot owner
                owner = (await self.bot.application_info()).owner
                if owner:
                    try:
                        await owner.send(
                            f"⚠️ High error rate detected in Aurora cog: "
                            f"{error_rate:.1f}% over last 5 minutes.\n"
                            f"Circuit breaker state: {self.circuit_breaker.state}\n"
                            f"Please investigate."
                        )
                    except Exception as msg_err:
                        log.error(f"Failed to message bot owner: {msg_err}")

            raise

    async def _execute_agent_call(self, agent_id: str, prompt: str, run_tracker: RunTracker | None = None) -> None:
        """Internal method to execute the actual Letta agent call.

        This is separated out so it can be wrapped with retry logic.
        """
        if not self.letta:
            raise RuntimeError("Letta client not initialized")

        try:
            stream: AsyncStream[
                SystemMessage
                | UserMessage
                | ReasoningMessage
                | HiddenReasoningMessage
                | ToolCallMessage
                | ToolReturnMessage
                | AssistantMessage
                | ApprovalRequestMessage
                | ApprovalResponseMessage
                | LettaPing
                | LettaErrorMessage
                | LettaStopReason
                | LettaUsageStatistics
            ] = await self.letta.agents.messages.create(
                agent_id=agent_id,
                messages=[
                    {
                        "role": "system",
                        "content": prompt,
                    }
                ],
                streaming=True,
                stream_tokens=False,  # Get complete chunks, not token-by-token
                max_steps=50,
                timeout=self.request_options.get("timeout"),
            )
            # Pass run_id container so it can be updated during stream processing
            await self._process_agent_stream(stream, run_tracker)

        except Exception as e:
            # Let retry logic handle it
            log.error(f"Error in agent execution: {type(e).__name__}: {str(e)}")
            raise

    async def _process_agent_stream(
        self,
        stream: AsyncStream[
            SystemMessage
            | UserMessage
            | ReasoningMessage
            | HiddenReasoningMessage
            | ToolCallMessage
            | ToolReturnMessage
            | AssistantMessage
            | ApprovalRequestMessage
            | ApprovalResponseMessage
            | LettaPing
            | LettaErrorMessage
            | LettaStopReason
            | LettaUsageStatistics
        ],
        run_tracker: RunTracker | None = None,
    ) -> None:
        """Process agent stream and extract run_id for cancellation if needed.

        Args:
            stream: The async iterator of streaming response chunks
            run_tracker: Optional dict to store the run_id and share state with callers
        """
        tool_calls = []
        run_id_found = False
        async for chunk in stream:
            # Extract run_id from any chunk that has it (most message types have run_id)
            if (
                not run_id_found
                and run_tracker is not None
                and not run_tracker.get("run_id")
                and hasattr(chunk, "run_id")
            ):
                potential_run_id = getattr(chunk, "run_id", None)
                if potential_run_id:
                    run_tracker["run_id"] = potential_run_id
                    log.debug(f"Extracted run_id: {potential_run_id}")
                    run_id_found = True
            # Handle different chunk types
            match chunk.message_type:
                case "reasoning_message":
                    # Log internal reasoning for debugging
                    if chunk.reasoning:
                        log.info(f"Agent reasoning: {chunk.reasoning}")

                case "tool_call_message":
                    # Track tool usage
                    # chunk.tool_calls is now a list
                    current_tool_calls = getattr(chunk, "tool_calls", []) or []
                    for tool_call in current_tool_calls:
                        if tool_call.name:
                            tool_calls.append(tool_call.name)
                            log.info(f"Agent calling tool: {tool_call.name}")
                        # handle the discord_set_presence tool call internally
                        if tool_call.name == "discord_set_presence":
                            await self._handle_discord_set_presence(tool_call)

                case "tool_return_message":
                    # Log tool results
                    if chunk.status == "success":
                        log.info(f"Tool {chunk.name} succeeded")
                    else:
                        log.warning(f"Tool {chunk.name} failed: {chunk.stderr}")

                case "assistant_message":
                    # Agent may have internal thoughts not sent to Discord
                    if chunk.content:
                        log.info(f"Agent internal message: {chunk.content[:100]}...")

                case "stop_reason":
                    log.info(f"Agent execution stopped: {chunk.stop_reason}")
                    if tool_calls:
                        log.info(f"Agent used tools during execution: {', '.join(tool_calls)}")
                    else:
                        log.info("Agent did not use any tools during execution")
                case "usage_statistics":
                    log.info(
                        f"Agent usage - Prompt tokens: {chunk.prompt_tokens}, "
                        f"Completion tokens: {chunk.completion_tokens}, "
                        f"Total tokens: {chunk.total_tokens}"
                    )
                case _:
                    log.info(f"Received chunk type: {chunk.message_type}")

    async def _handle_discord_set_presence(self, tool_call: Any):
        """Handle the discord_set_presence tool call from the agent.

        Streaming responses may present a wrapper type instead of a plain
        Letta `ToolCall` type. Accept `Any` and parse the expected payload
        safely.
        """
        try:
            args = json.loads(tool_call.arguments)
            status = args.get("status", "online")
            activity_type = args.get("activity_type", None)
            activity_name = args.get("activity_name", None)

            # Map activity type if provided
            if activity_type and activity_name:
                activity_mapping = {
                    "Playing": discord.ActivityType.playing,
                    "Streaming": discord.ActivityType.streaming,
                    "Listening": discord.ActivityType.listening,
                    "Watching": discord.ActivityType.watching,
                    "Competing": discord.ActivityType.competing,
                    "Custom": discord.ActivityType.custom,
                }
                discord_activity_type = activity_mapping.get(activity_type.capitalize(), discord.ActivityType.playing)
                activity = discord.Activity(
                    type=discord_activity_type,
                    name=activity_name,
                )
            else:
                activity = None
            discord_status = getattr(discord.Status, status.lower(), discord.Status.online)

            await self.bot.change_presence(
                status=discord_status,
                activity=activity,
            )
            log.info(f"Set bot presence to status: {status}, activity: " f"{activity_type} {activity_name}")

        except Exception as e:
            log.error(f"Error handling discord_set_presence tool call: {e}")


# endregion
