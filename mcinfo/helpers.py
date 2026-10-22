"""Helpers for mcinfo cog."""

import socket

import discord
from dns.exception import DNSException
from dns.exception import Timeout as DNSTimeout
from mcstatus import JavaServer
from mcstatus.responses import JavaStatusResponse
from redbot.core.utils import bounded_gather


async def fetch_server_status(address: str) -> JavaStatusResponse:
    try:
        server = await JavaServer.async_lookup(address)
        return await server.async_status()
    except (TimeoutError, DNSTimeout) as e:
        raise ConnectionError(f"Connection timed out for address {address}: {e}") from e
    except (socket.gaierror, DNSException) as e:
        raise ConnectionError(f"Could not resolve address {address}: {e}") from e


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


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _format_server_details(status: JavaStatusResponse) -> str:
    online = "Online: Yes" + (" · 🧩 Modded" if status.is_modded else "")
    players = (
        ", ".join(player.name for player in status.players.sample)
        if status.players.sample
        else "None"
    )
    details = (
        f"{online}\nOnline count: {status.players.online}/{status.players.max}"
        f"\nOnline players: {players}\nVersion: {status.version.name}"
    )
    motd = status.motd.to_plain().strip()
    if motd:
        motd = discord.utils.escape_markdown(discord.utils.escape_mentions(motd))
        details += f"\nMOTD: {motd}"
    return details


async def format_channel_desc(address, status: JavaStatusResponse | None) -> str:
    """Format the server status within Discord's channel topic limit."""
    details = "Online: No" if status is None else _format_server_details(status)
    return _truncate(f"Server info for {address}:\n\n{details}", 1024)


async def format_message_embed(
    statuses: dict[str, JavaStatusResponse | None],
) -> discord.Embed:
    """Format status and MOTD while respecting Discord's field and embed limits."""
    embed = discord.Embed(title="Minecraft Server Status", color=discord.Color.green())
    for address, status in statuses.items():
        name = _truncate(address, 256)
        # Reserve room to explain omitted servers if the embed fills up.
        available = min(1024, 6000 - len(embed) - len(name) - 50)
        if len(embed.fields) >= 25 or available < 1:
            break
        details = "Offline" if status is None else _format_server_details(status)
        embed.add_field(name=name, value=_truncate(details, available), inline=False)
    omitted = len(statuses) - len(embed.fields)
    if omitted:
        noun = "server" if omitted == 1 else "servers"
        embed.set_footer(text=f"{omitted} additional {noun} not shown.")
    return embed
