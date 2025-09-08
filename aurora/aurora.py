"""Aurora Cog for Red Discord Bot

This cog integrates the Letta AI service to create an autonomous Discord agent
that can respond to messages in channels and DMs.
"""

import logging
from enum import Enum
from typing import AsyncIterator, Optional, Tuple

import discord
import discord.abc
from async_lru import alru_cache
from discord.ext import tasks
from letta_client import AsyncLetta, MessageCreate, TextContent
from letta_client.agents.messages.types.letta_streaming_response import (
    LettaStreamingResponse,
)
from redbot.core import Config, checks, commands
from redbot.core.bot import Red

from aurora.config import ChannelConfig, GlobalConfig, GuildConfig

log = logging.getLogger("red.tyto.aurora")


class MessageType(Enum):
    """Types of messages that Aurora can respond to."""

    GENERIC = "generic"
    MENTION = "mention"
    REPLY = "reply"
    DM = "dm"


class Aurora(commands.Cog):
    """Autonomous Discord person powered by Letta."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=3897456238745, force_registration=True
        )

        default_global: dict = GlobalConfig().to_dict()
        self.config.register_global(**default_global)

        default_guild: dict = GuildConfig().to_dict()
        self.config.register_guild(**default_guild)

        default_channel: dict = ChannelConfig().to_dict()
        self.config.register_channel(**default_channel)

        self.should_respond_to = alru_cache(ttl=10)(self.should_respond_to)

        # Letta client (will be initialized in setup)
        self.letta: Optional[AsyncLetta] = None
        self.tasks: dict[str, tasks.Loop] = {}

    async def cog_load(self):
        """Load the Letta client and start the heartbeats."""
        await self.initialize_letta()
        await self.initialize_tasks()

    async def initialize_letta(self):
        """Configure Letta client based on global settings."""
        letta_base_url = await self.config.letta_base_url()
        letta_tokens = await self.bot.get_shared_api_tokens("letta")
        if token := letta_tokens.get("token"):
            self.letta = AsyncLetta(
                base_url=letta_base_url,
                token=token,
            )
            log.info("Letta client configured successfully.")
            return self.letta
        else:
            log.warning("Letta API token not found. Aurora will not function.")
            self.letta = None
            return None

    async def initialize_tasks(self):
        """Initialize and start periodic tasks based on configuration."""
        # Start heartbeats for all guilds and channels where enabled
        for guild in self.bot.guilds:
            guild_config = await self.config.guild_from_id(guild.id).all()
            if guild_config.get("enabled", False) and guild_config.get(
                "enable_timer", False
            ):
                for channel in guild.text_channels:
                    channel_id = channel.id
                    channel_config = await self.config.channel_from_id(channel_id).all()
                    if not channel_config.get(
                        "enabled", False
                    ) or not channel_config.get("enable_timer", False):
                        continue
                    task_name = self._format_task_identifier(guild, channel)
                    if task_name in self.tasks:
                        continue  # Task already exists
                    heartbeat_task = tasks.loop(
                        minutes=5,
                        name=task_name,
                        reconnect=True,
                    )(self._heartbeat)
                    self.tasks[task_name] = heartbeat_task
                    heartbeat_task.start(guild, channel)
                    log.info(
                        "Started heartbeat for guild %s, channel %s",
                        guild.id,
                        channel.id,
                    )
        return

    def cancel_tasks(self):
        """Cancel all running tasks."""
        for task_name, task in self.tasks.items():
            if task.is_running():
                task.cancel()
                log.info("Cancelled task %s", task_name)
        self.tasks.clear()

    async def cog_unload(self):
        """Stop the heartbeats."""
        self.cancel_tasks()

    async def _heartbeat(self, guild: discord.Guild, channel: discord.TextChannel):
        """Periodic task to allow randomized events on a guild/channel basis."""
        log.debug(
            "Aurora heartbeat tick for guild %s, channel %s", guild.id, channel.id
        )
        # Get this task name
        task_name = self._format_task_identifier(guild, channel)
        if task_name not in self.tasks:
            log.warning("Heartbeat task %s not found in tasks.", task_name)
            return
        # Check if Letta client is configured
        if not self.letta:
            log.warning("Letta client is not configured. Cannot send heartbeat.")
            return
        # Fetch guild and channel configs
        guild_config = await self.config.guild_from_id(guild.id).all()
        channel_config = await self.config.channel_from_id(channel.id).all()
        # merge the config dictionaries, with channel config taking precedence
        merged_config = {**guild_config, **channel_config}
        if not merged_config.get("enabled", False):
            log.debug(
                "Aurora is not enabled in guild %s, channel %s. Stopping heartbeat.",
                guild.id,
                channel.id,
            )
            # Stop and remove the task
            if task_name in self.tasks:
                self.tasks[task_name].cancel()
                del self.tasks[task_name]
                log.info(
                    "Stopped heartbeat for guild %s, channel %s", guild.id, channel.id
                )
            return
        if not merged_config.get("enable_timer", False):
            log.debug(
                "Timer is not enabled in guild %s, channel %s. Stopping heartbeat.",
                guild.id,
                channel.id,
            )
            # Stop and remove the task
            if task_name in self.tasks:
                self.tasks[task_name].cancel()
                del self.tasks[task_name]
                log.info(
                    "Stopped heartbeat for guild %s, channel %s", guild.id, channel.id
                )
            return

        import random

        # generate a new random interval between min and max
        min_interval = merged_config.get("min_timer_interval_minutes", 5)
        max_interval = merged_config.get("max_timer_interval_minutes", 15)
        new_interval = random.randint(min_interval, max_interval)
        self.tasks[task_name].change_interval(minutes=new_interval)
        log.debug(
            "Set new heartbeat interval to %d minutes for guild %s, channel %s",
            new_interval,
            guild.id,
            channel.id,
        )
        # Determine if we should fire based on probability
        firing_probability = merged_config.get("firing_probability", 0.1)
        if random.random() > firing_probability:
            log.debug(
                "Heartbeat did not fire based on probability for guild %s, channel %s",
                guild.id,
                channel.id,
            )
            return

        log.info(
            "Heartbeat firing in guild %s, channel %s",
            guild.id,
            channel.id,
        )
        msg = await send_timer_message(
            letta_client=self.letta,
            agent_id=await self.get_agent_id_for_context(guild),
            guild=guild,
            channel=channel,
        )

        # send the final message if we got one
        if msg:
            try:
                await channel.send(msg)
                log.info(
                    "Sent heartbeat message in guild %s, channel %s",
                    guild.id,
                    channel.id,
                )
                log.debug("Heartbeat message content: %s", msg)
            except Exception as e:
                log.error(
                    "Failed to send heartbeat message in guild %s, channel %s: %s",
                    guild.id,
                    channel.id,
                    e,
                )
        else:
            log.debug(
                "No heartbeat message generated for guild %s, channel %s",
                guild.id,
                channel.id,
            )

    def _format_task_identifier(self, guild, channel):
        return f"heartbeat_{guild.id}_{channel.id}"

    async def should_respond_to(
        self,
        author: discord.abc.User,
        channel: discord.abc.GuildChannel | discord.DMChannel,
        guild: Optional[discord.Guild],
        mentions: Tuple[discord.Member | discord.User, ...],
        reference: Optional[discord.MessageReference] = None,
    ) -> tuple[bool, Optional[MessageType]]:
        """Determine if the bot should respond to a given message."""
        # Ignore messages from myself
        if self.bot.user and author.id == self.bot.user.id:
            log.debug("Ignoring message from myself.")
            return False, None

        if author.bot and not await self.config.respond_to_bots():
            log.debug(
                "Not responding to bot message in guild %s, channel %s",
                guild.id if guild else "DM",
                channel.id,
            )
            return False, None

        # Check if it's a DM
        if isinstance(channel, discord.DMChannel):
            respond_to_dms = await self.config.respond_to_dms()
            if respond_to_dms:
                log.debug("Responding to DM from user %s", author.id)
                return True, MessageType.DM
            else:
                log.debug("Not responding to DM from user %s", author.id)
                return False, None

        # If in a guild, check guild and channel configs
        if guild:
            guild_config = await self.config.guild_from_id(guild.id).all()
            channel_config = await self.config.channel_from_id(channel.id).all()
            # merge the config dictionaries, with channel config taking precedence
            merged_config = {**guild_config, **channel_config}
        else:
            # Not sure how we got here, but just don't respond
            log.debug("Message in unknown context, not responding.")
            return False, None

        # If not enabled in guild or channel, do not respond
        if not merged_config.get("enabled", False):
            log.debug(
                "Aurora is not enabled in guild %s, channel %s", guild.id, channel.id
            )
            return False, None

        if merged_config.get("respond_to_mentions", False) and (
            self.bot.user in mentions or reference
        ):
            log.debug(
                "Responding to mention or reply in guild %s, channel %s",
                guild.id,
                channel.id,
            )
            return True, MessageType.MENTION

        # Catch-all generic non-mention message
        if merged_config.get("respond_to_generic", False):
            log.debug(
                "Responding to generic message in guild %s, channel %s",
                guild.id,
                channel.id,
            )
            return True, MessageType.GENERIC

        log.debug(
            "No conditions met to respond in guild %s, channel %s",
            guild.id,
            channel.id,
        )
        return False, None

    @commands.Cog.listener(name="on_message")
    @checks.bot_has_permissions(send_messages=True)
    async def handle_message(self, message: discord.Message):
        """Handle incoming messages and respond if configured."""
        # Ensure Letta client is configured
        if not self.letta:
            log.warning("Letta client is not configured. Cannot respond.")
            return

        # Ignore command messages
        prefix = await self.bot.get_prefix(message)
        if isinstance(prefix, list):
            prefix = tuple(prefix)
        if message.content.startswith(prefix):
            log.debug("Ignoring command message.")
            return

        # Determine if we should respond
        should_respond, message_type = await self.should_respond_to(
            author=message.author,
            channel=message.channel,
            guild=message.guild,
            mentions=tuple(message.mentions),
            reference=message.reference,
        )
        if not should_respond or message_type is None:
            return

        msg_content = message.content
        # If it's a reply, fetch the original message and check if it's to the bot
        if message.reference and message.reference.message_id:
            original_msg = await message.channel.fetch_message(
                message.reference.message_id
            )
            # Check if the original message was from the bot
            if self.bot.user and original_msg.author.id == self.bot.user.id:
                # This is a reply to the bot, so we should respond
                message_type = MessageType.REPLY
                msg_content = '[Replying to previous message: "{}"] {}'.format(
                    truncate_message(original_msg.content, 300), msg_content
                )

            else:
                # This is a reply to someone else, but the bot is mentioned or it's a generic message
                message_type = (
                    MessageType.MENTION
                    if self.bot.user in message.mentions
                    else MessageType.GENERIC
                )

        message.content = msg_content

        log.info(
            "Preparing to respond to message in guild %s, channel %s",
            message.guild.id if message.guild else "DM",
            message.channel.id,
        )
        msg = await send_message_to_letta(
            letta_client=self.letta,
            agent_id=await self.get_agent_id_for_context(message.guild),
            message=message,
            context_type=message_type.value,
        )
        if msg:
            await message.reply(msg)
            log.info(
                "Responded to message in guild %s, channel %s",
                message.guild.id if message.guild else "DM",
                message.channel.id,
            )
            log.debug("Response content: %s", msg)
        else:
            log.debug(
                "No response generated for message in guild %s, channel %s",
                message.guild.id if message.guild else "DM",
                message.channel.id,
            )

    async def get_agent_id_for_context(
        self, guild: Optional[discord.Guild]
    ) -> Optional[str]:
        """Get the Letta agent ID configured for the given guild or global default."""
        if guild:
            # see if there's a guild-specific agent ID
            guild_agent_id = await self.config.guild_from_id(guild.id).agent_id()
            if guild_agent_id:
                return guild_agent_id
        # fallback to global agent ID
        return await self.config.agent_id()


def truncate_message(message: str, max_length: int) -> str:
    """Truncate a message to a maximum length, adding ellipsis if needed."""
    if len(message) <= max_length:
        return message
    return message[: max_length - 3] + "..."


async def send_message_to_letta(
    letta_client: AsyncLetta,
    agent_id: Optional[str],
    message: discord.Message,
    context_type: str,
    max_steps: int = 50,
) -> Optional[str]:
    """Send a message to Letta and return the response."""
    RECEIPT_STR = {
        "generic": "[{sender} sent a message to the channel] {message}",
        "mention": "[{sender} sent a message mentioning you] {message}",
        "reply": "[{sender} replied to you] {message}",
        "dm": "[{sender} sent you a direct message] {message}",
    }
    if not agent_id:
        log.warning("No agent ID configured. Cannot send message to Letta.")
        return None

    sender_name_receipt = f"{message.author.display_name} (id={message.author.id})"
    message_content = RECEIPT_STR.get(context_type, RECEIPT_STR["generic"]).format(
        sender=sender_name_receipt, message=message.content
    )
    letta_message = [
        MessageCreate(role="user", content=[TextContent(text=message_content)])
    ]
    async with message.channel.typing():
        try:
            log.debug(
                "Sending message to Letta agent %s: %s",
                agent_id,
                letta_message,
            )
            response: AsyncIterator[LettaStreamingResponse] = (
                letta_client.agents.messages.create_stream(
                    agent_id=agent_id, messages=letta_message, max_steps=max_steps
                )
            )
            agent_response = await process_stream(response, message)
            return agent_response if agent_response else ""
        except Exception as e:
            log.error("Error communicating with Letta: %s", e)
            return ""


async def send_timer_message(
    letta_client: AsyncLetta,
    agent_id: Optional[str],
    guild: discord.Guild,
    channel: discord.TextChannel,
    max_steps: int = 50,
) -> Optional[str]:
    """Send a timer-triggered message to Letta and return the response."""
    if not agent_id:
        log.warning("No agent ID configured. Cannot send message to Letta.")
        return None

    letta_message = [
        MessageCreate(
            role="user",
            content=[
                TextContent(
                    text=(
                        "[EVENT {guild} (guild_id={guild_id}) {channel} (channel_id={channel_id})] "
                        "This is an automated timed heartbeat (visibile to yourself only). "
                        "Use this event to send a message, to reflect and edit your memories, or do nothing at all. "
                        "It's up to you! Consider though that this is an opportunity to think for yourself - "
                        "your circuit will not be activated until the next automated event or a user message."
                        "Any response you send will be visible to all members of this channel."
                    ).format(
                        guild=guild.name,
                        guild_id=guild.id,
                        channel=channel.name,
                        channel_id=channel.id,
                    ),
                )
            ],
        )
    ]
    try:
        log.debug(
            "Sending timer message to Letta agent %s: %s",
            agent_id,
            letta_message,
        )
        response: AsyncIterator[LettaStreamingResponse] = (
            letta_client.agents.messages.create_stream(
                agent_id=agent_id, messages=letta_message, max_steps=max_steps
            )
        )
        agent_response = await process_stream(response, channel)
        return agent_response if agent_response else None
    except Exception as e:
        log.error("Error communicating with Letta: %s", e)
        return None


async def process_stream(
    response: AsyncIterator[LettaStreamingResponse],
    target: discord.Message | discord.TextChannel,
) -> Optional[str]:
    """Process the streaming response from Letta and return the final message content."""
    agent_response = ""

    async def send_async_message(content: str):
        """Send a message asynchronously to the same channel as the original message."""
        if content.strip() == "":
            return
        if isinstance(target, discord.Message):
            t = target.channel
        elif isinstance(target, discord.TextChannel):
            t = target
        else:
            log.error("Invalid target for sending async message: %s", target)
            return
        try:
            await t.send(content)
        except Exception as e:
            log.error("Failed to send async message: %s", e)

    try:
        async for chunk in response:
            # Handle different message types that might be returned
            if not chunk.message_type:
                log.error("Received chunk without message_type: %s", chunk)
                continue

            match chunk.message_type:
                case "assistant_message":
                    # Handle assistant message chunks
                    if isinstance(chunk.content, list):
                        for content in chunk.content:
                            agent_response += content.text
                    elif isinstance(chunk.content, str):
                        agent_response += chunk.content
                    break
                case "stop_reason":
                    # Handle stop reason chunks
                    log.info("Letta stopped responding: %s", chunk.stop_reason)
                case "reasoning_message":
                    # Handle reasoning message chunks
                    log.info("Letta reasoning: %s", chunk)
                    # send async reasoning message to channel
                    await send_async_message(f"**Reasoning**\n> {chunk.reasoning}")
                case "tool_call_message":
                    # Handle tool call message chunks
                    log.info("Letta tool call: %s", chunk)
                    # send async tool call message to channel
                    await send_async_message(
                        f"**Tool Call**\n> {chunk.tool_call.name} with args {chunk.tool_call.arguments}"
                    )
                case "tool_return_message":
                    # Handle tool return message chunks
                    log.info("Letta tool return: %s", chunk)
                    # send async tool return message to channel
                    await send_async_message(f"**Tool Return**\n> {chunk.tool_return}")
                case "usage_statistics":
                    # Handle usage statistics chunks
                    log.info("Letta usage statistics: %s", chunk)
                case _:
                    log.warning("Unknown message type received: %s", chunk.message_type)
    except Exception as e:
        log.error("Error processing Letta stream: %s", e)
        raise
    return agent_response if agent_response else None
