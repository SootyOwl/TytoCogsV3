"Tests for helpers."

import copy
import pytest
from mcinfo.helpers import (
    fetch_server_status,
    fetch_servers,
    format_channel_desc,
    format_message_embed,
)
from mcstatus.status_response import (
    JavaStatusResponse,
    RawJavaResponse,
    JavaStatusPlayer,
)


@pytest.mark.asyncio
async def test_get_status_returns_status_response():
    resp = await fetch_server_status("mc.tyto.cc:25565")
    assert isinstance(resp, JavaStatusResponse)
    assert resp.latency
    assert resp.players.max == 20
    assert resp.version


@pytest.mark.asyncio
async def test_get_status_bad_address():
    with pytest.raises(ConnectionError):
        await fetch_server_status(address="notvalid:25565")


@pytest.mark.asyncio
async def test_get_status_not_online():
    with pytest.raises(ConnectionError):
        await fetch_server_status(address="www.google.com:25565")


@pytest.mark.asyncio
async def test_fetch_servers():
    addresses = ["mc.tyto.cc:25565", "mc.hypixel.net"]
    results = await fetch_servers(addresses)
    assert len(results) == 2
    assert isinstance(results["mc.tyto.cc:25565"], JavaStatusResponse)
    assert isinstance(results["mc.hypixel.net"], JavaStatusResponse)
    assert results["mc.tyto.cc:25565"].latency
    assert results["mc.hypixel.net"].latency


@pytest.mark.asyncio
async def test_fetch_servers_with_invalid_address():
    addresses = ["mc.tyto.cc:25565", "notvalid:25565"]
    results = await fetch_servers(addresses)
    assert len(results) == 2
    assert isinstance(results["mc.tyto.cc:25565"], JavaStatusResponse)
    assert results["notvalid:25565"] is None


@pytest.fixture
def server_status():
    """Fixture to create a mock server status response."""
    return JavaStatusResponse.build(
        raw=RawJavaResponse(
            {
                "version": {"name": "Paper 1.21.1", "protocol": 767},
                "enforcesSecureChat": True,
                "description": {
                    "text": "Let's kill the dragon at the weekend!",
                    "extra": [{"text": "", "color": "aqua"}],
                },
                "players": {
                    "max": 20,
                    "online": 1,
                    "sample": [
                        {
                            "id": "b2dd52a0-8284-4c23-8deb-ed980904959a",
                            "name": "Player1",
                        }
                    ],
                },
            }
        )
    )


@pytest.mark.asyncio
async def test_format_channel_desc(server_status: JavaStatusResponse):
    """Test formatting of channel description for server status.

    ```
    Server info for mc.tyto.cc:25565:

    Online: Yes
    Online count: 0/20
    Online players: Player1
    Version: Paper 1.21.1
    ```
    """
    desc = await format_channel_desc(address="mc.tyto.cc:25565", status=server_status)
    assert desc == (
        "Server info for mc.tyto.cc:25565:\n\n"
        "Online: Yes\n"
        "Online count: 1/20\n"
        "Online players: Player1\n"
        "Version: Paper 1.21.1"
    )


@pytest.mark.asyncio
async def test_format_channel_desc_multiple_players(server_status: JavaStatusResponse):
    """Test formatting of channel description for server status with multiple players.

    ```
    Server info for mc.tyto.cc:25565:
    Online: Yes
    Online count: 2/20
    Online players: Player1, Player2
    Version: Paper 1.21.1
    ```
    """
    server_status.players.sample.append(
        JavaStatusPlayer(name="Player2", id="b2dd52a0-8284-4c23-8deb-ed980904959b")
    )  # type: ignore
    server_status.players.online += 1
    desc = await format_channel_desc(address="mc.tyto.cc:25565", status=server_status)
    assert desc == (
        "Server info for mc.tyto.cc:25565:\n\n"
        "Online: Yes\n"
        "Online count: 2/20\n"
        "Online players: Player1, Player2\n"
        "Version: Paper 1.21.1"
    )


@pytest.mark.asyncio
async def test_format_channel_desc_server_offline():
    """If the server is offline then the status will be None."""
    desc = await format_channel_desc(address="mc.tyto.cc:25565", status=None)
    assert desc == "Server info for mc.tyto.cc:25565:\n\nOnline: No"


@pytest.mark.asyncio
async def test_format_message_embed(server_status: JavaStatusResponse):
    """Test formatting of message embed for server status."""
    embed = await format_message_embed({"mc.tyto.cc:25565": server_status})
    assert embed.title == "Minecraft Server Status"
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "mc.tyto.cc:25565"
    assert embed.fields[0].value == (
        "Online: Yes\n"
        "Online count: 1/20\n"
        "Online players: Player1\n"
        "Version: Paper 1.21.1"
    )


@pytest.mark.asyncio
async def test_format_message_embed_multiple_servers(server_status: JavaStatusResponse):
    """Test formatting of message embed for multiple server statuses."""
    server_status_2 = copy.deepcopy(server_status)
    server_status_2.players.sample.append(
        JavaStatusPlayer(name="Player2", id="b2dd52a0-8284-4c23-8deb-ed980904959b")
    )
    server_status_2.players.online += 1
    embed = await format_message_embed(
        {"mc.tyto.cc:25565": server_status, "mc.hypixel.net": server_status_2}
    )
    assert embed.title == "Minecraft Server Status"
    assert len(embed.fields) == 2
    assert embed.fields[0].name == "mc.tyto.cc:25565"
    assert embed.fields[0].value == (
        "Online: Yes\n"
        "Online count: 1/20\n"
        "Online players: Player1\n"
        "Version: Paper 1.21.1"
    )
    assert embed.fields[1].name == "mc.hypixel.net"
    assert embed.fields[1].value == (
        "Online: Yes\n"
        "Online count: 2/20\n"
        "Online players: Player1, Player2\n"
        "Version: Paper 1.21.1"
    )
