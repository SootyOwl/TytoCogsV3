"""Unit tests for Aurora context extraction utilities."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock
import discord

from aurora.utils.context import (
    extract_message_metadata,
    extract_reply_chain,
    format_reply_chain,
    format_metadata_for_prompt,
    build_event_context,
)
from aurora.utils.dataclasses import (
    AuthorMetadata,
    ChannelMetadata,
    GuildMetadata,
    MessageMetadata,
    MessageRecord,
    ReplyChain,
)


@pytest.fixture
def mock_guild():
    """Create a mock Discord guild."""
    guild = Mock(spec=discord.Guild)
    guild.id = 123456789
    guild.name = "Test Server"
    return guild


@pytest.fixture
def mock_channel(mock_guild):
    """Create a mock Discord text channel."""
    channel = Mock(spec=discord.TextChannel)
    channel.id = 987654321
    channel.name = "general"
    channel.type = discord.ChannelType.text
    channel.guild = mock_guild
    return channel


@pytest.fixture
def mock_author(mock_guild):
    """Create a mock Discord member."""
    author = Mock(spec=discord.Member)
    author.id = 111222333
    author.name = "testuser"
    author.display_name = "Test User"
    author.bot = False

    # Mock roles
    role1 = Mock(spec=discord.Role)
    role1.name = "Member"
    role2 = Mock(spec=discord.Role)
    role2.name = "@everyone"
    author.roles = [role2, role1]

    return author


@pytest.fixture
def mock_message(mock_channel, mock_author):
    """Create a mock Discord message."""
    message = Mock(spec=discord.Message)
    message.id = 555666777
    message.content = "Test message content"
    message.channel = mock_channel
    message.author = mock_author
    message.guild = mock_channel.guild
    message.created_at = datetime(2025, 10, 16, 12, 30, 0)
    message.reference = None
    message.attachments = []
    message.embeds = []
    return message


@pytest.fixture
def mock_dm_channel():
    """Create a mock Discord DM channel."""
    channel = Mock(spec=discord.DMChannel)
    channel.id = 888999000
    channel.type = discord.ChannelType.private
    return channel


@pytest.fixture
def mock_dm_message(mock_dm_channel):
    """Create a mock Discord DM message."""
    author = Mock(spec=discord.User)
    author.id = 111222333
    author.name = "testuser"
    author.display_name = "Test User"
    author.bot = False

    message = Mock(spec=discord.Message)
    message.id = 555666777
    message.content = "Test DM content"
    message.channel = mock_dm_channel
    message.author = author
    message.guild = None
    message.created_at = datetime(2025, 10, 16, 12, 30, 0)
    message.reference = None
    message.attachments = []
    message.embeds = []
    return message


class TestExtractMessageMetadata:
    """Tests for extract_message_metadata function."""

    @pytest.mark.asyncio
    async def test_guild_message_metadata(self, mock_message):
        """Test extracting metadata from a guild message."""
        metadata = await extract_message_metadata(mock_message)

        assert metadata.message_id == 555666777
        assert metadata.timestamp == "2025-10-16T12:30:00"
        assert metadata.author.id == 111222333
        assert metadata.author.username == "testuser"
        assert metadata.author.display_name == "Test User"
        assert metadata.author.is_bot is False
        assert metadata.author.roles == ["Member"]
        assert metadata.channel.id == 987654321
        assert metadata.channel.name == "general"
        assert metadata.guild.id == 123456789
        assert metadata.guild.name == "Test Server"

    @pytest.mark.asyncio
    async def test_dm_message_metadata(self, mock_dm_message):
        """Test extracting metadata from a DM message."""
        metadata = await extract_message_metadata(mock_dm_message)

        assert metadata.message_id == 555666777
        assert metadata.author.id == 111222333
        assert metadata.channel.id == 888999000
        assert metadata.channel.name == "DM"
        assert metadata.guild is None
        assert metadata.author.roles == []

    @pytest.mark.asyncio
    async def test_bot_message_metadata(self, mock_message):
        """Test extracting metadata from a bot message."""
        mock_message.author.bot = True
        metadata = await extract_message_metadata(mock_message)

        assert metadata.author.is_bot is True


class TestExtractReplyChain:
    """Tests for extract_reply_chain function."""

    @pytest.mark.asyncio
    async def test_no_reply_chain(self, mock_message):
        """Test message with no reply chain."""
        chain = await extract_reply_chain(mock_message, max_depth=5)

        assert len(chain) == 0

    @pytest.mark.asyncio
    async def test_single_parent_reply(self, mock_message, mock_channel, mock_author):
        """Test message with one parent."""
        # Create parent message
        parent = Mock(spec=discord.Message)
        parent.id = 444555666
        parent.content = "Parent message"
        parent.author = mock_author
        parent.created_at = datetime(2025, 10, 16, 12, 25, 0)
        parent.reference = None
        parent.attachments = []
        parent.embeds = []

        # Setup reference
        message_ref = Mock(spec=discord.MessageReference)
        message_ref.message_id = parent.id
        mock_message.reference = message_ref

        # Mock fetch_message
        mock_channel.fetch_message = AsyncMock(return_value=parent)

        chain = await extract_reply_chain(mock_message, max_depth=5)

        assert len(chain) == 1
        assert chain[0].message_id == 444555666
        assert chain[0].content == "Parent message"
        assert chain[0].author == "Test User"
        assert chain[0].is_bot is False

    @pytest.mark.asyncio
    async def test_multiple_parent_replies(
        self, mock_message, mock_channel, mock_author
    ):
        """Test message with multiple parents (thread)."""
        # Create parent messages
        parent1 = Mock(spec=discord.Message)
        parent1.id = 111111111
        parent1.content = "First message"
        parent1.author = mock_author
        parent1.created_at = datetime(2025, 10, 16, 12, 20, 0)
        parent1.reference = None
        parent1.attachments = []
        parent1.embeds = []

        parent2 = Mock(spec=discord.Message)
        parent2.id = 222222222
        parent2.content = "Second message"
        parent2.author = mock_author
        parent2.created_at = datetime(2025, 10, 16, 12, 25, 0)
        parent2.attachments = []
        parent2.embeds = []

        # Setup references
        ref2 = Mock(spec=discord.MessageReference)
        ref2.message_id = parent1.id
        parent2.reference = ref2

        ref3 = Mock(spec=discord.MessageReference)
        ref3.message_id = parent2.id
        mock_message.reference = ref3

        # Mock fetch_message to return appropriate parent
        async def fetch_side_effect(msg_id):
            if msg_id == parent2.id:
                return parent2
            elif msg_id == parent1.id:
                return parent1

        mock_channel.fetch_message = AsyncMock(side_effect=fetch_side_effect)

        chain = await extract_reply_chain(mock_message, max_depth=5)

        assert len(chain) == 2
        assert chain[0].message_id == 111111111  # Oldest first
        assert chain[1].message_id == 222222222

    @pytest.mark.asyncio
    async def test_reply_chain_max_depth(self, mock_message, mock_channel, mock_author):
        """Test that reply chain respects max_depth."""
        # Create a long chain
        parents = []
        for i in range(10):
            parent = Mock(spec=discord.Message)
            parent.id = 100000000 + i
            parent.content = f"Message {i}"
            parent.author = mock_author
            parent.created_at = datetime(2025, 10, 16, 12, i, 0)
            parent.attachments = []
            parent.embeds = []
            parents.append(parent)

        # Setup references (each points to previous)
        for i in range(len(parents)):
            if i == 0:
                parents[i].reference = None
            else:
                ref = Mock(spec=discord.MessageReference)
                ref.message_id = parents[i - 1].id
                parents[i].reference = ref

        # Setup mock message to point to last parent
        last_ref = Mock(spec=discord.MessageReference)
        last_ref.message_id = parents[-1].id
        mock_message.reference = last_ref

        # Mock fetch_message
        async def fetch_side_effect(msg_id):
            for parent in parents:
                if parent.id == msg_id:
                    return parent
            raise discord.NotFound(Mock(), "Message not found")

        mock_channel.fetch_message = AsyncMock(side_effect=fetch_side_effect)

        # Test with max_depth=3
        chain = await extract_reply_chain(mock_message, max_depth=3)

        assert len(chain) == 3

    @pytest.mark.asyncio
    async def test_reply_chain_deleted_message(self, mock_message, mock_channel):
        """Test handling of deleted parent message."""
        ref = Mock(spec=discord.MessageReference)
        ref.message_id = 999999999
        mock_message.reference = ref

        # Mock fetch_message to raise NotFound
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(Mock(), "Message not found")
        )

        chain = await extract_reply_chain(mock_message, max_depth=5)

        # Should handle gracefully and return empty chain
        assert len(chain) == 0


class TestFormatReplyChain:
    """Tests for format_reply_chain function."""

    @pytest.fixture
    def chain(self) -> ReplyChain:
        """Setup common reply chain for tests."""
        rc = ReplyChain()
        msg1 = MessageRecord(
            message_id=123456,
            author="Test User",
            author_id=111222,
            content="Hello world",
            clean_content="Hello world",
            timestamp="2025-10-16T12:30:00",
            is_bot=False,
            has_attachments=False,
            has_embeds=False,
        )
        msg2 = MessageRecord(
            message_id=654321,
            author="Another User",
            author_id=333444,
            content="Replying to you",
            clean_content="Replying to you",
            timestamp="2025-10-16T12:32:00",
            is_bot=False,
            has_attachments=True,
            has_embeds=False,
        )
        rc.messages = [msg1, msg2]
        return rc

    def test_empty_chain(self):
        """Test formatting empty reply chain."""
        result = format_reply_chain(ReplyChain())
        assert result == "No reply chain."

    def test_single_message_chain(self, chain):
        """Test formatting single message in chain."""
        single_chain = ReplyChain()
        single_chain.messages = [chain.messages[0]]

        result = format_reply_chain(single_chain)

        assert "Test User" in result
        assert "author_id: 111222" in result
        assert "Hello world" in result
        assert "message_id: 123456" in result

    def test_chain_with_attachments(self, chain):
        """Test formatting message with attachments."""
        result = format_reply_chain(chain)

        assert "has_attachments: True" in result


class TestFormatMetadataForPrompt:
    """Tests for format_metadata_for_prompt function."""

    @pytest.fixture
    def metadata(self) -> MessageMetadata:
        """Setup common metadata for tests."""
        return MessageMetadata(
            message_id=123456,
            timestamp="2025-10-16T12:30:00",
            author=AuthorMetadata(
                id=111222,
                username="testuser",
                display_name="Test User",
                is_bot=False,
                roles=["Admin", "Member"],
            ),
            channel=ChannelMetadata(
                id=987654,
                name="general",
                type="text",
            ),
            guild=GuildMetadata(
                id=555666,
                name="Test Server",
            ),
        )

    def test_guild_metadata_formatting(self, metadata):
        """Test formatting guild message metadata."""
        result = format_metadata_for_prompt(metadata)

        assert "Test User" in result
        assert "(ID: 111222)" in result
        assert "[Roles: Admin, Member]" in result
        assert "Test Server" in result
        assert "general" in result

    def test_dm_metadata_formatting(self, metadata):
        """Test formatting DM message metadata."""
        metadata.guild = None
        metadata.channel = ChannelMetadata(
            id=888999,
            name="DM",
            type="private",
        )
        result = format_metadata_for_prompt(metadata)

        assert "Test User" in result
        assert "DM" in result
        assert "Server:" not in result


class TestBuildEventContext:
    """Tests for build_event_context function."""

    @pytest.mark.asyncio
    async def test_build_complete_context(
        self, mock_message, mock_channel, mock_author
    ):
        """Test building complete event context."""
        # Setup a reply chain
        parent = Mock(spec=discord.Message)
        parent.id = 444555666
        parent.content = "Parent message"
        parent.author = mock_author
        parent.created_at = datetime(2025, 10, 16, 12, 25, 0)
        parent.reference = None
        parent.attachments = []
        parent.embeds = []

        message_ref = Mock(spec=discord.MessageReference)
        message_ref.message_id = parent.id
        mock_message.reference = message_ref

        mock_channel.fetch_message = AsyncMock(return_value=parent)

        context = await build_event_context(mock_message, max_reply_depth=5)

        assert isinstance(context[0], MessageMetadata)
        assert isinstance(context[1], ReplyChain)
        assert context[0].message_id == 555666777
        assert len(context[1].messages) == 1
