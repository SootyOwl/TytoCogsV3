"""Helpers for mcinfo cog."""

import socket
import discord
from redbot.core.utils import bounded_gather
from mcstatus import JavaServer
from mcstatus.status_response import JavaStatusResponse


async def fetch_server_status(address: str) -> JavaStatusResponse:
    # lookup the server
    server = await JavaServer.async_lookup(address)
    # query the server and return the response
    try:
        return await server.async_status()
    except socket.gaierror as e:
        raise ConnectionError(f"Could not resolve address {address}: {e}")
    except TimeoutError as e:
        raise ConnectionError(f"Connection timed out for address {address}: {e}")

async def fetch_servers(addresses: list[str]) -> dict[str, JavaStatusResponse | None]:
    """Fetch multiple server status simultaneously."""
    # Create a list of tasks for each server address
    tasks = [fetch_server_status(address) for address in addresses]
    # Use bounded_gather to limit the number of concurrent tasks
    results = await bounded_gather(*tasks, return_exceptions=True, limit=5)

    # Create a dictionary to store the results
    server_status = {}
    for address, result in zip(addresses, results):
        if isinstance(result, Exception):
            server_status[address] = None
        else:
            server_status[address] = result

    return server_status


async def format_channel_desc(address, status: JavaStatusResponse | None) -> str:
    """Format the server status for channel description."""
    # if status is None, return a message indicating the server is offline
    if status is None:
        description = ("Server info for {address}:\n\n" "Online: No").format(address=address)
        return description

    # format the server status
    description = (
        "Server info for {address}:\n\n"
        "Online: Yes\n"
        "Online count: {online_count}/{max_count}\n"
        "Online players: {online_players}\n"
        "Version: {version}"
    )
    fillers = {
        "address": address,
        "online_count": status.players.online,
        "max_count": status.players.max,
        "online_players": (
            ", ".join(player.name for player in status.players.sample) if status.players.sample else "None"
        ),
        "version": status.version.name,
    }

    # format the description
    description = description.format(**fillers)
    return description


async def format_message_embed(statuses: dict[str, JavaStatusResponse | None]) -> discord.Embed:
    """Format the server status for a message embed."""
    # create an embed object
    embed = discord.Embed(title="Minecraft Server Status", color=discord.Color.green())

    # iterate over the statuses and add fields to the embed
    for address, status in statuses.items():
        if status is None:
            embed.add_field(name=address, value="Offline", inline=False)
        else:
            online_players = (
                ", ".join(player.name for player in status.players.sample) if status.players.sample else "None"
            )
            embed.add_field(
                name=address,
                value=f"Online: Yes\nOnline count: {status.players.online}/{status.players.max}\nOnline players: {online_players}\nVersion: {status.version.name}",
                inline=False,
            )

    return embed
