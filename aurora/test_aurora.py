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
        MockLetta.assert_called_once_with(base_url="https://api.letta.ai/v1", api_key="valid_token")


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
        # Verify mark_processed is called for the synthesis event type (timestamps now tracked via queue, not config)
        aurora_cog.queue.mark_processed.assert_called()


@pytest.mark.asyncio
async def test_synthesis_no_letta_client(aurora_cog, mock_bot):
    """Test synthesis returns early when Letta client is not configured."""
    guild_id = 123
    aurora_cog.letta = None  # No Letta client

    with patch("aurora.aurora.attach_blocks", new_callable=AsyncMock) as mock_attach:
        await aurora_cog.synthesis(guild_id)

        # Should not attempt to attach blocks or process
        mock_attach.assert_not_called()
        # mark_processed should still be called (in finally block)
        aurora_cog.queue.mark_processed.assert_not_called()


@pytest.mark.asyncio
async def test_synthesis_guild_not_found(aurora_cog, mock_bot, mock_config):
    """Test synthesis stops task when guild is not found."""
    guild_id = 123
    aurora_cog.letta = AsyncMock()
    mock_bot.get_guild.return_value = None  # Guild not found

    # Track task removal
    aurora_cog._remove_task = Mock()

    with patch("aurora.aurora.attach_blocks", new_callable=AsyncMock) as mock_attach:
        await aurora_cog.synthesis(guild_id)

        # Should stop the task
        aurora_cog._remove_task.assert_called_once()
        # Should not attach blocks
        mock_attach.assert_not_called()


@pytest.mark.asyncio
async def test_synthesis_no_agent_id(aurora_cog, mock_bot, mock_config):
    """Test synthesis stops task when agent_id is not configured."""
    guild_id = 123
    aurora_cog.letta = AsyncMock()

    mock_guild = Mock(spec=discord.Guild)
    mock_guild.id = guild_id
    mock_bot.get_guild.return_value = mock_guild

    # No agent_id in config
    mock_config.guild(mock_guild).all.return_value = {
        "enabled": True,
        "agent_id": None,
    }

    aurora_cog._remove_task = Mock()

    with patch("aurora.aurora.attach_blocks", new_callable=AsyncMock) as mock_attach:
        await aurora_cog.synthesis(guild_id)

        # Should stop the task
        aurora_cog._remove_task.assert_called_once()
        # Should not attach blocks
        mock_attach.assert_not_called()


@pytest.mark.asyncio
async def test_synthesis_block_attach_failure_continues(aurora_cog, mock_bot, mock_config):
    """Test synthesis continues even if block attach fails."""
    guild_id = 123
    agent_id = "agent-123"

    mock_guild = Mock(spec=discord.Guild)
    mock_guild.id = guild_id
    mock_bot.get_guild.return_value = mock_guild

    mock_config.guild(mock_guild).all.return_value = {
        "agent_id": agent_id,
        "enabled": True,
    }

    mock_letta = AsyncMock()
    aurora_cog.letta = mock_letta

    mock_stream = AsyncMock()
    mock_stream.__aiter__.return_value = []
    mock_letta.agents.messages.create.return_value = mock_stream

    with (
        patch("aurora.aurora.attach_blocks", new_callable=AsyncMock) as mock_attach,
        patch("aurora.aurora.detach_blocks", new_callable=AsyncMock) as mock_detach,
    ):
        # Block attach fails
        mock_attach.return_value = (False, set())
        mock_detach.return_value = (True, set())

        await aurora_cog.synthesis(guild_id)

        # Should still call Letta agent
        mock_letta.agents.messages.create.assert_called_once()
        # Should not try to detach (attached is False/empty set)
        mock_detach.assert_not_called()
        # mark_processed should still be called
        aurora_cog.queue.mark_processed.assert_called()


@pytest.mark.asyncio
async def test_synthesis_exception_still_updates_timestamp(aurora_cog, mock_bot, mock_config):
    """Test that mark_processed is called even when synthesis throws an exception."""
    guild_id = 123
    agent_id = "agent-123"

    mock_guild = Mock(spec=discord.Guild)
    mock_guild.id = guild_id
    mock_bot.get_guild.return_value = mock_guild

    mock_config.guild(mock_guild).all.return_value = {
        "agent_id": agent_id,
        "enabled": True,
    }

    mock_letta = AsyncMock()
    aurora_cog.letta = mock_letta

    # Make Letta API call raise an exception
    mock_letta.agents.messages.create.side_effect = Exception("API Error")

    with (
        patch("aurora.aurora.attach_blocks", new_callable=AsyncMock) as mock_attach,
        patch("aurora.aurora.detach_blocks", new_callable=AsyncMock) as mock_detach,
    ):
        mock_attach.return_value = (True, {"block1"})
        mock_detach.return_value = (True, {"block1"})

        # Should not raise - exception is caught
        await aurora_cog.synthesis(guild_id)

        # mark_processed should still be called (in finally block)
        aurora_cog.queue.mark_processed.assert_called()
        # Blocks should still be detached
        mock_detach.assert_called_once()


@pytest.mark.asyncio
async def test_synthesis_detach_failure_logged(aurora_cog, mock_bot, mock_config):
    """Test that block detach failure is handled gracefully."""
    guild_id = 123
    agent_id = "agent-123"

    mock_guild = Mock(spec=discord.Guild)
    mock_guild.id = guild_id
    mock_bot.get_guild.return_value = mock_guild

    mock_config.guild(mock_guild).all.return_value = {
        "agent_id": agent_id,
        "enabled": True,
    }

    mock_letta = AsyncMock()
    aurora_cog.letta = mock_letta

    mock_stream = AsyncMock()
    mock_stream.__aiter__.return_value = []
    mock_letta.agents.messages.create.return_value = mock_stream

    with (
        patch("aurora.aurora.attach_blocks", new_callable=AsyncMock) as mock_attach,
        patch("aurora.aurora.detach_blocks", new_callable=AsyncMock) as mock_detach,
    ):
        mock_attach.return_value = (True, {"block1"})
        # Detach fails
        mock_detach.return_value = (False, set())

        # Should not raise
        await aurora_cog.synthesis(guild_id)

        # Detach was attempted
        mock_detach.assert_called_once()
        # mark_processed should still be called
        aurora_cog.queue.mark_processed.assert_called()


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
    # Verify mark_processed is called for the event type (timestamps now tracked via queue, not config)
    aurora_cog.queue.mark_processed.assert_called()


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


@pytest.mark.asyncio
async def test_track_server_activity_reenqueues_below_threshold(aurora_cog, mock_bot, mock_config):
    """Test that events from channels below the activity threshold are re-enqueued."""
    from aurora.utils.queue import Event

    # Setup
    guild_id = 123
    agent_id = "agent-123"

    mock_guild = Mock(spec=discord.Guild)
    mock_guild.id = guild_id
    mock_bot.get_guild.return_value = mock_guild

    # Config setup with threshold of 3 messages
    mock_config.guild(mock_guild).all.return_value = {
        "agent_id": agent_id,
        "enabled": True,
        "activity_threshold": 3,  # Need 3 messages to trigger notification
    }

    # Letta setup
    mock_letta = AsyncMock()
    aurora_cog.letta = mock_letta

    # Mock stream response
    mock_stream = AsyncMock()
    mock_stream.__aiter__.return_value = []
    mock_letta.agents.messages.create.return_value = mock_stream

    # Create mock events for two channels:
    # Channel 456 has 2 messages (below threshold)
    # Channel 789 has 3 messages (meets threshold)
    mock_events = []

    # Channel 456 - 2 messages (below threshold)
    for i in range(2):
        event = Event.from_dict(
            {
                "event_type": f"server_activity_{guild_id}",
                "channel_id": 456,
                "message_id": 1000 + i,
            }
        )
        mock_events.append(event)

    # Channel 789 - 3 messages (meets threshold)
    for i in range(3):
        event = Event.from_dict(
            {
                "event_type": f"server_activity_{guild_id}",
                "channel_id": 789,
                "message_id": 2000 + i,
            }
        )
        mock_events.append(event)

    aurora_cog.queue.consume_all.return_value = mock_events

    # Mock message fetching for both channels
    def get_channel_mock(channel_id):
        mock_channel = AsyncMock(spec=discord.TextChannel)
        mock_channel.id = channel_id
        mock_channel.name = f"channel-{channel_id}"

        async def fetch_message_mock(message_id):
            mock_message = Mock(spec=discord.Message)
            mock_message.channel = mock_channel
            mock_message.author.id = 999
            mock_message.author.display_name = "User"
            mock_message.author.global_name = "UserGlobal"
            mock_message.created_at = datetime.now()
            return mock_message

        mock_channel.fetch_message = fetch_message_mock
        return mock_channel

    mock_bot.get_channel.side_effect = get_channel_mock

    # Mock the queue.enqueue method to track re-enqueued events
    enqueued_events = []

    async def mock_enqueue(event, allow_duplicates=False):
        enqueued_events.append((event, allow_duplicates))
        return True

    aurora_cog.queue.enqueue = mock_enqueue

    # Execute
    await aurora_cog.track_server_activity(guild_id)

    # Verify
    # Should have consumed all events
    aurora_cog.queue.consume_all.assert_called_once()

    # Should have re-enqueued the 2 events from channel 456 (below threshold)
    assert len(enqueued_events) == 2, f"Expected 2 re-enqueued events, got {len(enqueued_events)}"

    # All re-enqueued events should be from channel 456
    for event, allow_duplicates in enqueued_events:
        assert event.data["channel_id"] == 456, "Re-enqueued event should be from channel 456"
        assert allow_duplicates is True, "Re-enqueued events should allow duplicates"

    # Should have sent notification for channel 789 (which met the threshold)
    mock_letta.agents.messages.create.assert_called_once()
    call_args = mock_letta.agents.messages.create.call_args
    messages = call_args.kwargs["messages"]
    assert len(messages) == 1
    # The message content should contain the activity notification header
    message_content = messages[0]["content"]
    assert "Server Activity Notification" in message_content, "Message should contain activity notification header"


@pytest.mark.asyncio
async def test_track_server_activity_no_notification_when_all_below_threshold(aurora_cog, mock_bot, mock_config):
    """Test that no notification is sent when all channels are below threshold, but events are re-enqueued."""
    from aurora.utils.queue import Event

    # Setup
    guild_id = 123
    agent_id = "agent-123"

    mock_guild = Mock(spec=discord.Guild)
    mock_guild.id = guild_id
    mock_bot.get_guild.return_value = mock_guild

    # Config setup with threshold of 5 messages
    mock_config.guild(mock_guild).all.return_value = {
        "agent_id": agent_id,
        "enabled": True,
        "activity_threshold": 5,  # Need 5 messages to trigger notification
    }

    # Letta setup
    mock_letta = AsyncMock()
    aurora_cog.letta = mock_letta

    # Create mock events for one channel with only 2 messages (below threshold)
    mock_events = []
    for i in range(2):
        event = Event.from_dict(
            {
                "event_type": f"server_activity_{guild_id}",
                "channel_id": 456,
                "message_id": 1000 + i,
            }
        )
        mock_events.append(event)

    aurora_cog.queue.consume_all.return_value = mock_events

    # Mock message fetching
    mock_channel = AsyncMock(spec=discord.TextChannel)
    mock_channel.id = 456
    mock_channel.name = "general"

    async def fetch_message_mock(message_id):
        mock_message = Mock(spec=discord.Message)
        mock_message.channel = mock_channel
        mock_message.author.id = 999
        mock_message.author.display_name = "User"
        mock_message.author.global_name = "UserGlobal"
        mock_message.created_at = datetime.now()
        return mock_message

    mock_channel.fetch_message = fetch_message_mock
    mock_bot.get_channel.return_value = mock_channel

    # Mock the queue.enqueue method to track re-enqueued events
    enqueued_events = []

    async def mock_enqueue(event, allow_duplicates=False):
        enqueued_events.append((event, allow_duplicates))
        return True

    aurora_cog.queue.enqueue = mock_enqueue

    # Execute
    await aurora_cog.track_server_activity(guild_id)

    # Verify
    # Should have consumed all events
    aurora_cog.queue.consume_all.assert_called_once()

    # Should have re-enqueued all 2 events (since they're below threshold)
    assert len(enqueued_events) == 2, f"Expected 2 re-enqueued events, got {len(enqueued_events)}"

    # All re-enqueued events should allow duplicates
    for event, allow_duplicates in enqueued_events:
        assert allow_duplicates is True, "Re-enqueued events should allow duplicates"

    # Should NOT have sent any notification to the agent
    mock_letta.agents.messages.create.assert_not_called()
