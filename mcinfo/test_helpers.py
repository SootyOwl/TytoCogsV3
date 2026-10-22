"Tests for helpers."

import socket
from dataclasses import replace

import dns.exception
import dns.resolver
import pytest
from mcstatus.responses import (
    JavaStatusPlayer,
    JavaStatusResponse,
)

from mcinfo.helpers import (
    fetch_server_status,
    fetch_servers,
    format_channel_desc,
    format_message_embed,
)


@pytest.mark.asyncio
@pytest.mark.live
async def test_get_status_returns_status_response():
    resp = await fetch_server_status("mc.tyto.cc:25565")
    assert isinstance(resp, JavaStatusResponse)
    assert resp.latency
    assert resp.players.max == 20
    assert resp.version


@pytest.mark.asyncio
@pytest.mark.live
async def test_get_status_bad_address():
    with pytest.raises(ConnectionError):
        await fetch_server_status(address="notvalid:25565")


@pytest.mark.asyncio
@pytest.mark.live
async def test_get_status_not_online():
    with pytest.raises(ConnectionError):
        await fetch_server_status(address="www.google.com:25565")


@pytest.mark.asyncio
@pytest.mark.live
async def test_fetch_servers():
    addresses = ["mc.tyto.cc:25565", "mc.hypixel.net"]
    results = await fetch_servers(addresses)
    assert len(results) == 2
    assert isinstance(results["mc.tyto.cc:25565"], JavaStatusResponse)
    assert isinstance(results["mc.hypixel.net"], JavaStatusResponse)
    assert results["mc.tyto.cc:25565"].latency
    assert results["mc.hypixel.net"].latency


@pytest.mark.asyncio
@pytest.mark.live
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
        raw={
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
    server_status = replace(
        server_status,
        players=replace(
            server_status.players,
            online=2,
            sample=[
                *server_status.players.sample,
                JavaStatusPlayer(
                    name="Player2", id="b2dd52a0-8284-4c23-8deb-ed980904959b"
                ),
            ],
        ),
    )
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
    server_status_2 = replace(
        server_status,
        players=replace(
            server_status.players,
            online=2,
            sample=[
                *server_status.players.sample,
                JavaStatusPlayer(
                    name="Player2", id="b2dd52a0-8284-4c23-8deb-ed980904959b"
                ),
            ],
        ),
    )
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


@pytest.mark.parametrize("phase", ["lookup", "status"])
@pytest.mark.parametrize(
    "failure",
    [
        socket.gaierror("no DNS"),
        TimeoutError("timeout"),
        dns.resolver.NXDOMAIN(),
        dns.resolver.NoAnswer(),
        dns.exception.Timeout(),
    ],
)
async def test_fetch_status_normalizes_network_failures(phase, failure, mocker):
    server = mocker.Mock(async_status=mocker.AsyncMock())
    lookup = mocker.patch(
        "mcinfo.helpers.JavaServer.async_lookup",
        new_callable=mocker.AsyncMock,
        return_value=server,
    )
    if phase == "lookup":
        lookup.side_effect = failure
    else:
        server.async_status.side_effect = failure
    with pytest.raises(ConnectionError) as caught:
        await fetch_server_status("example.org:25565")
    assert caught.value.__cause__ is failure


async def test_fetch_servers_preserves_success_when_another_server_fails(
    server_status, mocker
):
    async def fetch(address):
        if address == "offline.example":
            raise ConnectionError("offline")
        return server_status

    mocker.patch("mcinfo.helpers.fetch_server_status", side_effect=fetch)
    assert await fetch_servers(["online.example", "offline.example"]) == {
        "online.example": server_status,
        "offline.example": None,
    }


@pytest.mark.parametrize("sample", [None, []])
async def test_hidden_player_sample_is_rendered_as_none(server_status, sample):
    status = replace(
        server_status, players=replace(server_status.players, sample=sample)
    )
    assert "Online players: None" in await format_channel_desc("example.org", status)
    embed = await format_message_embed({"example.org": status})
    assert "Online players: None" in embed.fields[0].value


async def test_lookup_handles_real_mcstatus_dns_path(mocker):
    failure = dns.resolver.NoNameservers()
    mocker.patch(
        "dns.asyncresolver.resolve", new_callable=mocker.AsyncMock, side_effect=failure
    )
    with pytest.raises(ConnectionError) as caught:
        await fetch_server_status("offline.example")
    assert caught.value.__cause__ is failure
