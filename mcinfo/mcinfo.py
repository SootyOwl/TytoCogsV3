"""A cog to periodically retrieve the status of minecraft servers.
Only supports Java servers for now.
Inspired by palmtree5's `Mcsvr` cog: https://github.com/palmtree5/palmtree5-cogs
"""

# Commands needed:
# - set mode (channel description or message edit)
# - add server: only one server supported if channel description, many on edit mode, need url
# - remove server
# - a way of initialisating the editable message for when mode is MESSAGE
# Methods:
# - checker - a discord task looping
# Helpers:
# - get status
# - get statuses (for multiple servers at once)
# - format channel description
# - format message embed

import asyncio
from enum import StrEnum
from typing import Optional
import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import bounded_gather
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import logging
from mcinfo.helpers import (
    fetch_servers,
    format_channel_desc,
    format_message_embed,
    JavaStatusResponse,
)


class Mode(StrEnum):
    """Enum for the mode of the server status check."""

    CHANNEL_DESC = "desc"
    MESSAGE = "msg"


class MessageIdNotFound(KeyError):
    """Exception raised when the message ID is not found in the config."""


class BadChannelError(ValueError):
    """Exception raised when the channel is not found or not a text channel."""


class McInfo(commands.Cog):
    """Periodically retrieve the status of minecraft servers and update a channel description or message.

    Uses the discord.ext.tasks extension to run the status checks periodically."""

    default_channel = {
        "mode": Mode.CHANNEL_DESC,
        "servers": [],
        "message_id": None,  # only used if mode is MESSAGE, the id of the bot message to edit
    }
    default_global = {
        "interval": 5,  # default interval for the server check in minutes
    }

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            cog_instance=self, identifier=788963682, force_registration=True
        )
        # per-channel default settings
        self.config.register_channel(**self.default_channel)
        # global default settings
        self.config.register_global(**self.default_global)
        # set up logging
        self.logger = logging.getLogger("red.mcinfo")
        self.logger.setLevel(logging.INFO)
        # start the task loop
        self.perform_check.start()

    async def cog_load(self):
        # set the interval for the task loop
        interval = await self.config.interval()
        self.perform_check.change_interval(minutes=interval)
        self.logger.info(f"Starting mcinfo cog with interval {interval} minutes.")

    def cog_unload(self):
        self.perform_check.cancel()

    @tasks.loop(minutes=5)
    async def perform_check(self):
        """Perform the server check for all channels with the cog enabled."""
        # get all channels with the cog enabled
        channels: dict[int, dict] = await self.config.all_channels()
        # make tasks for each channel
        tasks = []
        for channel_id, channel_config in channels.items():
            # add the task to the list
            tasks.append(self._execute_channel_check(channel_id, channel_config))
        # run the tasks concurrently
        results = await bounded_gather(*tasks, return_exceptions=True, limit=5)
        # log the results for debugging
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"Error checking server status: {result}")
            else:
                self.logger.info(f"Server status check result: {result}")

    async def _execute_channel_check(self, channel_id: int, channel_config: dict):
        """Perform the server check for a single channel."""
        # get the channel
        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            await self._remove_channel_from_config(channel_id)
            raise BadChannelError(
                f"Channel {channel_id} not found or not a text channel."
            )

        # get the mode and servers from the config
        mode = channel_config.get("mode")
        servers = channel_config.get("servers")
        if not servers:
            await self._remove_channel_from_config(channel_id)
            raise ValueError(f"No servers found in config for channel {channel_id}.")

        # fetch the server statuses
        self.logger.info(f"Fetching server statuses for channel {channel_id}...")
        server_statuses = await fetch_servers(servers)
        # format the status for the channel
        if mode == Mode.CHANNEL_DESC:
            # only use the first server - more than one server on channel desc is not supported
            address = servers[0]
            server_status = server_statuses.get(address)
            # format the channel description
            description = await format_channel_desc(address, server_status)
            # update the channel description
            await channel.edit(topic=description)
            return description
        elif mode == Mode.MESSAGE:
            try:
                return await self._handle_message(
                    channel, channel_config, server_statuses
                )
            except (MessageIdNotFound, discord.NotFound, discord.Forbidden) as e:
                self.logger.error(
                    f"Error updating message in channel {channel_id}: {e}"
                )
                await self._remove_channel_from_config(channel_id)
                raise e
            except discord.HTTPException as e:
                self.logger.error(
                    f"Error updating message in channel {channel_id}: {e}"
                )
                raise e

    async def _handle_message(
        self,
        channel: discord.TextChannel,
        channel_config: dict,
        server_statuses: dict[str, JavaStatusResponse | None],
    ):
        """Handle the message update for the channel.

        Args:
            channel (discord.TextChannel): The channel to update.
            channel_config (dict): The config for the channel.
            server_statuses (dict): The server statuses to update the message with.

        Returns:
            discord.Message: The updated message.

        Raises:
            ValueError: If the message ID is not found in the config.
            discord.NotFound: If the message is not found in the channel.
            discord.Forbidden: If the bot does not have the correct permissions to get/edit the message.
            discord.HTTPException: If there is an error with the HTTP request.
        """
        message_id = channel_config.get("message_id")

        if not message_id:
            raise MessageIdNotFound("Message ID not found in config.")

        message = await channel.fetch_message(message_id)
        # format the embed for the message
        embed = await format_message_embed(server_statuses)
        # edit the message with the new embed
        return await message.edit(embed=embed)

    async def _remove_channel_from_config(self, channel_id):
        self.logger.info(f"Removing channel {channel_id} from config.")
        await self.config.channel_from_id(channel_id).clear()

    @perform_check.before_loop
    async def before_checker(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    # region: commands
    @commands.group(name="mcinfo", aliases=["mc"], invoke_without_command=True)
    async def mcinfo(self, ctx: commands.Context):
        """Minecraft server status commands."""
        await ctx.send_help()

    @mcinfo.command(name="setmode")
    @commands.admin_or_can_manage_channel()
    async def set_mode(
        self,
        ctx: commands.Context,
        mode: Mode,
        channel: Optional[discord.TextChannel] = None,
    ):
        """Set the mode for the specified channel, or the current channel.

        Modes:
        - `desc`: Channel description mode (only one server supported)
        - `msg`: Message edit mode (multiple servers supported)
        """
        # if no channel is specified, use the current channel
        if channel is None:
            channel = ctx.channel
        # check if the channel is valid
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("Invalid channel specified.")
            return
        # check if the mode is valid
        if mode not in Mode:
            await ctx.send("Invalid mode specified. Use `desc` or `msg`.")
            return
        # update the config for the channel
        await self.config.channel(channel).mode.set(mode)
        await ctx.send(f"Set mode to {mode} for channel {channel.mention}.")
        # if the mode is MESSAGE, check if a message id is set
        if mode == Mode.MESSAGE:
            return await self._initialize_channel_message(ctx, channel)
        else:
            return await self._initialize_channel_description(ctx, channel)

    async def _initialize_channel_description(self, ctx, channel):
        # check if we have permissions to edit the channel description
        permissions = channel.permissions_for(ctx.guild.me)
        if not permissions.manage_channels:
            await ctx.send(
                "I do not have permission to edit the channel description, please check my permissions."
            )
            return
        await ctx.send(
            "Channel description mode does not support multiple servers, will only use the first one in the list.\n"
            "Switch to `msg` mode to use multiple servers."
        )
        await self._execute_channel_check(
            channel.id, await self.config.channel(channel).all()
        )

    async def _initialize_channel_message(self, ctx, channel):
        # check if we have permissions to send messages in the channel
        permissions = channel.permissions_for(ctx.guild.me)
        if not permissions.send_messages:
            await ctx.send(
                "I do not have permission to send messages in the channel, please check my permissions."
            )
            return
        message_id = await self.config.channel(channel).message_id()
        # if we don't have a message id, or the message doesn't exist, send a message to the channel for editing
        if message_id is None or not await channel.fetch_message(message_id):
            # send the message with the new embed
            embed = await format_message_embed({})
            message = await channel.send(embed=embed)
            try:
                # pin the message if we can
                await message.pin(reason="Initial message for mcinfo cog.")
            except Exception:
                pass
            # update the config with the message id
            await self.config.channel(channel).message_id.set(message.id)
            await ctx.send(
                f"Message id is set to {message.id} for channel {channel.mention}."
            )
            # run the checker to update the message for the channel
        else:
            await ctx.send(
                f"Message id is set to {message_id} for channel {channel.mention}."
            )
        await self._execute_channel_check(
            channel.id, await self.config.channel(channel).all()
        )

    # manage servers for this channel via a menu
    @mcinfo.command(name="manageservers")
    @commands.admin_or_can_manage_channel()
    async def manage_servers(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """Manage servers for the specified channel, or the current channel.

        Use reactions to add or remove servers from the list.
        """
        # if no channel is specified, use the current channel
        if channel is None:
            channel = ctx.channel

        # check if the channel is valid
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("Invalid channel specified.")
            return

        async def generate_pages() -> list[str]:
            """Generate the pages for the menu."""
            # get the servers from the config
            servers = await self.config.channel(channel).servers()
            if not servers:
                return ["No servers found in config for this channel."]
            # format the server list as discord embeds with the channel name and server address
            server_list = []
            for server in servers:
                # create an embed for each server
                embed = discord.Embed(
                    title="Manage servers",
                    color=discord.Color.blue(),
                    description=f"Managing servers for {channel.name}",
                )
                # add the server address to the embed
                embed.add_field(name="Address", value=server, inline=False)
                # add some help text
                embed.set_footer(text="Use the reactions to add or remove servers.")
                server_list.append(embed)
            return server_list

        async def generate_page_menu(ctx, controls, message, page, timeout):
            pages = await generate_pages()
            page = min(page, len(pages) - 1)
            return await menu(ctx, pages, controls, message, page, timeout)

        async def add_server_action(
            ctx, pages, controls, message, page, timeout, emoji
        ):
            """Action to add a new server to the list."""
            # get the server address from the user
            await ctx.send("Please enter the server address:")
            try:
                response = await self.bot.wait_for(
                    "message",
                    timeout=60.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                )
            except asyncio.TimeoutError:
                await ctx.send("Timed out waiting for server address.")
                return
            # quick check to ensure the address is valid
            if not response.content or " " in response.content:
                await ctx.send("Likely invalid server address.")
                return
            # check if the server is already in the list
            async with self.config.channel(channel).servers() as servers:
                # add the server to the list if it doesn't already exist
                if response.content not in servers:
                    servers.append(response.content)
                    await ctx.send(f"Added server {response.content} to the list.")
                else:
                    await ctx.send(
                        f"Server {response.content} already exists in the list."
                    )

            # update the menu with the new server list
            return await generate_page_menu(ctx, controls, message, page, timeout)

        async def remove_server_action(
            ctx, pages, controls, message, page: int, timeout: float, emoji
        ):
            """Action to remove current server from the list."""
            # current page's server will be removed, check with user first
            await ctx.send(
                f"Are you sure you want to remove {pages[page].fields[0].value} from the list? (yes/no)"
            )
            try:
                response = await self.bot.wait_for(
                    "message",
                    timeout=60.0,
                    check=lambda m: m.author == ctx.author
                    and m.channel == ctx.channel
                    and m.content.lower() in ["yes", "no"],
                )
            except asyncio.TimeoutError:
                await ctx.send("Timed out waiting for confirmation.")
                return
            if response.content.lower() == "no":
                await ctx.send("Cancelled removal of server.")
                return
            async with self.config.channel(channel).servers() as servers:
                # remove the server from the list
                if servers:
                    server = servers.pop(page)
                    await ctx.send(f"Removed server {server} from the list.")
                else:
                    await ctx.send("No servers to remove.")
            # update the menu with the new server list
            return await generate_page_menu(ctx, controls, message, page, timeout)

        # create menu controls
        controls = {
            **DEFAULT_CONTROLS,
            "\N{SQUARED NEW}": add_server_action,
            "\N{WASTEBASKET}\N{VARIATION SELECTOR-16}": remove_server_action,
        }
        # create the menu
        pages = await generate_pages()
        await menu(
            ctx,
            pages,
            controls,
            page=0,
            timeout=60.0,
        )

        # trigger the checker to update the channel description or message
        await self._execute_channel_check(
            channel.id, await self.config.channel(channel).all()
        )

    @mcinfo.command(name="setinterval")
    @commands.is_owner()
    async def set_interval(self, ctx: commands.Context, interval: int):
        """Set the interval for the server check in minutes."""
        if interval < 1:
            await ctx.send("Interval must be at least 1 minute.")
            return
        # update the config with the new interval
        self.logger.info("Setting server check interval to %d minutes", interval)
        await self.config.interval.set(interval)
        # update the task loop with the new interval
        self.perform_check.change_interval(minutes=interval)
        await ctx.send(f"Set server check interval to {interval} minutes.")

    # simple command to get a single server's status and send it as a message
    @mcinfo.command(name="status")
    async def status(self, ctx: commands.Context, address: str):
        """Get the status of a single server and send it as a message."""
        # fetch the server status
        server_status = await fetch_servers([address])
        # format the embed for the message
        embed = await format_message_embed(server_status)
        # send the message with the embed
        await ctx.send(embed=embed)
        # log the status for debugging
        self.logger.info(f"Server status for {address}: {server_status}")

    # endregion
