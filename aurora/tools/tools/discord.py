from typing import Any
from . import register_tool


@register_tool
def list_servers() -> list:
    """
    List all guilds (servers) the Discord bot is a member of.

    Returns:
        list: A list of dictionaries containing guild information (id, name, member_count).
    """
    import os
    import requests

    bot_token = os.environ.get("DISCORD_TOKEN")

    if not bot_token:
        raise ValueError("DISCORD_TOKEN environment variable is not set.")

    url = "https://discord.com/api/v10/users/@me/guilds"
    headers = {"Authorization": f"Bot {bot_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(
            f"Failed to fetch guilds: {response.status_code} - {response.text}"
        )
    guilds = response.json()
    return [
        {
            "id": guild["id"],
            "name": guild["name"],
            "member_count": guild.get("approximate_member_count", "N/A"),
        }
        for guild in guilds
    ]


# search a guild's messages
@register_tool
def search_guild_messages(guild_id: str, **params: dict[str, Any]) -> tuple[str, list]:
    """
    Search messages in a guild (server) for a specific query.

    Args:
        guild_id (str): The ID of the guild to search in.
        params (dict): Additional search parameters (e.g., content, author_id, channel_id).

    Returns:
        list: A list of dictionaries containing message information (id, content, author, timestamp).
    """
    import os
    import requests

    bot_token = os.environ.get("DISCORD_TOKEN")

    if not bot_token:
        raise ValueError("DISCORD_TOKEN environment variable is not set.")

    url = f"https://discord.com/api/v10/guilds/{guild_id}/messages/search"
    headers = {"Authorization": f"Bot {bot_token}"}
    default_params = {
        "limit": 25,
        "offset": 0,
        "sort_by": "timestamp",
        "sort_order": "desc",
    }
    default_params.update(params)
    params = {k: v for k, v in default_params.items() if v is not None}
    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        raise Exception(
            f"Failed to search messages: {response.status_code} - {response.text}"
        )
    messages = response.json().get("messages", [])
    results = []
    total_results = response.json().get("total_results", 0)
    for message_group in messages:
        for message in message_group:
            results.append(
                {
                    "id": message["id"],
                    "content": message["content"],
                    "author": {
                        "id": message["author"]["id"],
                        "username": message["author"]["username"],
                        "bot": message["author"].get("bot", False),
                    },
                    "timestamp": message["timestamp"],
                }
            )
    return f"Found {total_results} messages. Showing {len(results)} messages.", results
