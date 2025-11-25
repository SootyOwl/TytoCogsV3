"""Unit tests for the Aurora cog."""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime
import discord
from aurora.aurora import Aurora


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.get_shared_api_tokens = AsyncMock(return_value={"token": "test_token"})
    bot.wait_until_ready = AsyncMock()
    bot.get_guild = Mock()
    bot.get_context = AsyncMock()
    return bot


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.register_global = Mock()
    config.register_guild = Mock()
    config.letta_base_url = AsyncMock(return_value="https://api.letta.ai/v1")

    # Mock guild config
    guild_config = MagicMock()
    guild_config.all = AsyncMock(return_value={})
    guild_config.agent_id = AsyncMock()
    guild_config.enabled = AsyncMock()
    guild_config.last_synthesis = AsyncMock()
    guild_config.last_server_activity = AsyncMock()

    # Handle config.guild(guild) calls
    config.guild.return_value = guild_config

    # Handle config.all_guilds() calls
    config.all_guilds = AsyncMock(return_value={})

    return config


@pytest.fixture
def aurora_cog(mock_bot, mock_config):
    with (
        patch("aurora.aurora.Config.get_conf", return_value=mock_config),
        patch("aurora.aurora.cog_data_path", return_value=MagicMock()),
    ):
        cog = Aurora(mock_bot)
        # Mock the queue to avoid file I/O
        cog.queue = MagicMock()
        cog.queue.put = AsyncMock()
        cog.queue.enqueue = AsyncMock()
        cog.queue.consume_all = AsyncMock(return_value=[])
        return cog


@pytest.mark.asyncio
async def test_initialize_letta_success(aurora_cog, mock_bot):
    """Test successful Letta client initialization."""
    # Setup
    mock_bot.get_shared_api_tokens.return_value = {"token": "valid_token"}

    # Execute
    with patch("aurora.aurora.AsyncLetta") as MockLetta:
        client = await aurora_cog.initialize_letta()

        # Verify
        assert client is not None
        assert aurora_cog.letta is not None
        MockLetta.assert_called_once_with(
            base_url="https://api.letta.ai/v1", api_key="valid_token"
        )


@pytest.mark.asyncio
async def test_initialize_letta_no_token(aurora_cog, mock_bot):
    """Test initialization failure when no token is present."""
    # Setup
    mock_bot.get_shared_api_tokens.return_value = {}

    # Execute
    client = await aurora_cog.initialize_letta()

    # Verify
    assert client is None
    assert aurora_cog.letta is None


@pytest.mark.asyncio
async def test_synthesis_execution(aurora_cog, mock_bot, mock_config):
    """Test the synthesis task execution."""
    # Setup
    guild_id = 123
    agent_id = "agent-123"

    mock_guild = Mock(spec=discord.Guild)
    mock_guild.id = guild_id
    mock_bot.get_guild.return_value = mock_guild

    # Config setup
    mock_config.guild(mock_guild).all.return_value = {
        "agent_id": agent_id,
        "enabled": True,
        "synthesis_interval": 3600,
    }

    # Letta setup
    mock_letta = AsyncMock()
    aurora_cog.letta = mock_letta

    # Mock stream response
    mock_stream = AsyncMock()
    mock_stream.__aiter__.return_value = []
    mock_letta.agents.messages.create.return_value = mock_stream

    # Mock attach/detach blocks
    with (
        patch("aurora.aurora.attach_blocks", new_callable=AsyncMock) as mock_attach,
        patch("aurora.aurora.detach_blocks", new_callable=AsyncMock) as mock_detach,
    ):
        mock_attach.return_value = (True, {"block1"})
        mock_detach.return_value = (True, {"block1"})

        # Execute
        await aurora_cog.synthesis(guild_id)

        # Verify
        mock_attach.assert_called_once()
        mock_letta.agents.messages.create.assert_called_once()
        mock_detach.assert_called_once()
        mock_config.guild(mock_guild).last_synthesis.set.assert_called_once()


@pytest.mark.asyncio
async def test_track_server_activity(aurora_cog, mock_bot, mock_config):
    """Test server activity tracking."""
    # Setup
    guild_id = 123
    agent_id = "agent-123"

    mock_guild = Mock(spec=discord.Guild)
    mock_guild.id = guild_id
    mock_bot.get_guild.return_value = mock_guild

    # Config setup
    mock_config.guild(mock_guild).all.return_value = {
        "agent_id": agent_id,
        "enabled": True,
        "activity_threshold": 1,
    }

    # Letta setup
    mock_letta = AsyncMock()
    aurora_cog.letta = mock_letta

    # Mock stream response
    mock_stream = AsyncMock()
    mock_stream.__aiter__.return_value = []
    mock_letta.agents.messages.create.return_value = mock_stream

    # Mock queue events
    mock_event = MagicMock()
    mock_event.data = {"channel_id": 456, "message_id": 789}
    aurora_cog.queue.consume_all.return_value = [mock_event]

    # Mock message fetching
    mock_channel = AsyncMock(spec=discord.TextChannel)
    mock_channel.id = 456
    mock_channel.name = "general"
    mock_bot.get_channel.return_value = mock_channel

    mock_message = Mock(spec=discord.Message)
    mock_message.channel = mock_channel
    mock_message.author.id = 999
    mock_message.author.display_name = "User"
    mock_message.author.global_name = "UserGlobal"
    mock_message.created_at = datetime.now()
    mock_channel.fetch_message.return_value = mock_message

    # Execute
    await aurora_cog.track_server_activity(guild_id)

    # Verify
    aurora_cog.queue.consume_all.assert_called_once()
    mock_letta.agents.messages.create.assert_called_once()
    mock_config.guild(mock_guild).last_server_activity.set.assert_called_once()


@pytest.mark.asyncio
async def test_on_message_queuing(aurora_cog, mock_bot):
    """Test that messages are queued correctly."""
    # Setup
    aurora_cog.letta = AsyncMock()  # Client initialized
    aurora_cog._events_paused = False

    mock_message = Mock(spec=discord.Message)
    mock_message.author.bot = False
    mock_message.author.display_name = "TestUser"
    mock_message.author.global_name = "TestUserGlobal"
    mock_message.author.id = 999
    mock_message.guild.id = 123
    mock_message.channel.id = 456
    mock_message.id = 789
    mock_message.content = "Hello"
    mock_message.mentions = []
    mock_message.reference = None

    # Mock context to be invalid (not a command)
    mock_ctx = MagicMock()
    mock_ctx.valid = False
    mock_bot.get_context.return_value = mock_ctx

    # Execute
    await aurora_cog.on_message(mock_message)

    # Verify
    aurora_cog.queue.enqueue.assert_called_once()
    call_args = aurora_cog.queue.enqueue.call_args
    event = call_args[0][0]
    assert event["event_type"] == "server_activity_123"  # Assuming format
    assert event["message_id"] == 789
    assert event["channel_id"] == 456


@pytest.mark.asyncio
async def test_on_message_ignore_bots(aurora_cog):
    """Test that bot messages are ignored."""
    # Setup
    aurora_cog.letta = AsyncMock()

    mock_message = Mock(spec=discord.Message)
    mock_message.author.bot = True

    # Execute
    await aurora_cog.on_message(mock_message)

    # Verify
    aurora_cog.queue.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_paused(aurora_cog):
    """Test that messages are ignored when paused."""
    # Setup
    aurora_cog.letta = AsyncMock()
    aurora_cog._events_paused = True

    mock_message = Mock(spec=discord.Message)
    mock_message.author.bot = False

    # Execute
    await aurora_cog.on_message(mock_message)

    # Verify
    aurora_cog.queue.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_active_queuing(aurora_cog, mock_bot, mock_config):
    """Test that mentions are queued as message events."""
    # Setup
    aurora_cog.letta = AsyncMock()
    aurora_cog._events_paused = False

    mock_message = Mock(spec=discord.Message)
    mock_message.author.bot = False
    mock_message.author.display_name = "TestUser"
    mock_message.author.global_name = "TestUserGlobal"
    mock_message.author.id = 999
    mock_message.guild.id = 123

    # Ensure channel is TextChannel so is_dm is False
    mock_channel = Mock(spec=discord.TextChannel)
    mock_channel.id = 456
    mock_message.channel = mock_channel

    mock_message.id = 789
    mock_message.content = "Hello @Aurora"
    mock_message.mentions = [mock_bot.user]  # Bot is mentioned
    mock_message.reference = None
    mock_message.created_at = datetime.now()

    # Mock context
    mock_ctx = MagicMock()
    mock_ctx.valid = False
    mock_bot.get_context.return_value = mock_ctx

    # Mock config
    mock_config.guild(mock_message.guild).all.return_value = {
        "enabled": True,
        "agent_id": "agent-123",
    }

    # Execute
    await aurora_cog.on_message(mock_message)

    # Verify
    aurora_cog.queue.enqueue.assert_called_once()
    call_args = aurora_cog.queue.enqueue.call_args
    event = call_args[0][0]
    assert event["event_type"] == "message"
    assert event["message_id"] == 789
    assert event["agent_id"] == "agent-123"
