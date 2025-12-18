"""Unit tests for Aurora prompt template system."""

import pytest

from aurora.utils.dataclasses import (
    AuthorMetadata,
    ChannelMetadata,
    GuildMetadata,
    MessageMetadata,
    MessageRecord,
    ReplyChain,
)
from aurora.utils.prompts import (
    build_dm_prompt,
    build_mention_prompt,
    build_prompt,
)


@pytest.fixture
def message_metadata():
    """Fixture for common message metadata."""
    return MessageMetadata(
        **{
            "message_id": 123456,
            "timestamp": "2025-10-16T12:30:00",
            "author": AuthorMetadata(
                **{
                    "id": 111222,
                    "username": "testuser",
                    "display_name": "Test User",
                    "global_name": "Test User",
                    "is_bot": False,
                    "roles": [],
                }
            ),
            "channel": ChannelMetadata(
                **{
                    "id": 987654,
                    "name": "general",
                    "type": "text",
                }
            ),
            "guild": GuildMetadata(
                **{
                    "id": 555666,
                    "name": "Test Server",
                }
            ),
        }
    )


@pytest.fixture
def reply_chain():
    """Fixture for common reply chain."""
    return ReplyChain(
        messages=[
            MessageRecord(
                message_id=111111,
                author="Alice",
                author_id=222222,
                content="What's the best Python linter?",
                clean_content="What's the best Python linter?",
                timestamp="2025-10-16T12:25:00",
                is_bot=False,
                has_attachments=False,
                has_embeds=False,
            ),
            MessageRecord(
                message_id=222222,
                author="Bob",
                author_id=333333,
                content="I recommend Ruff",
                clean_content="I recommend Ruff",
                timestamp="2025-10-16T12:28:00",
                is_bot=False,
                has_attachments=False,
                has_embeds=False,
            ),
        ]
    )


@pytest.fixture
def mock_message():
    """Fixture for a mock message record."""
    message = MessageRecord(
        message_id=333333,
        author="Test User",
        author_id=111222,
        content="Hello @bot, how are you?",
        clean_content="Hello @bot, how are you?",
        timestamp="2025-10-16T12:30:00",
        is_bot=False,
        has_attachments=False,
        has_embeds=False,
    )
    return message


class TestBuildMentionPrompt:
    """Tests for build_mention_prompt function."""

    def test_basic_mention_prompt(self, message_metadata, mock_message):
        """Test building a basic mention prompt."""
        prompt = build_mention_prompt(
            message=mock_message,
            metadata=message_metadata,
            reply_chain=ReplyChain(),
            include_mcp_guidance=True,
        )

        # Verify key components are in prompt
        assert "Test User" in prompt
        assert "general" in prompt
        assert "Test Server" in prompt
        assert "Hello @bot, how are you?" in prompt
        assert "discord_read_messages" in prompt  # MCP tool guidance
        assert "discord_send" in prompt  # MCP tool guidance

    def test_mention_prompt_with_reply_chain(
        self, message_metadata, reply_chain, mock_message
    ):
        """Test mention prompt with reply chain context."""
        # update mock_message content to reference reply chain
        mock_message.content = "@bot what do you think?"
        mock_message.clean_content = "@bot what do you think?"

        prompt = build_mention_prompt(
            message=mock_message,
            metadata=message_metadata,
            reply_chain=reply_chain,
            include_mcp_guidance=True,
        )

        # Verify reply chain is included
        assert "Alice" in prompt
        assert "What's the best Python linter?" in prompt
        assert "Bob" in prompt
        assert "I recommend Ruff" in prompt
        assert "@bot what do you think?" in prompt


class TestBuildDMPrompt:
    """Tests for build_dm_prompt function."""

    def test_basic_dm_prompt(self, mock_message):
        """Test building a basic DM prompt."""
        metadata = MessageMetadata(
            **{
                "message_id": "123456",
                "timestamp": "2025-10-16T12:30:00",
                "author": AuthorMetadata(
                    **{
                        "id": 111222,
                        "username": "testuser",
                        "display_name": "Test User",
                        "global_name": "Test User",
                        "is_bot": False,
                        "roles": [],
                    }
                ),
                "channel": ChannelMetadata(
                    **{
                        "id": 987654,
                        "name": "DM",
                        "type": "DM",
                    }
                ),
                "guild": None,
            }
        )

        mock_message.content = "Hey bot, can you help me?"
        mock_message.clean_content = "Hey bot, can you help me?"

        prompt = build_dm_prompt(
            message=mock_message,
            metadata=metadata,
            reply_chain=ReplyChain(),
            include_mcp_guidance=True,
        )

        # Verify key components
        assert "Test User" in prompt
        assert "Hey bot, can you help me?" in prompt
        assert (
            "direct message" in prompt.lower() or "DM" in prompt
        )  # Should mention it's a DM

    def test_dm_prompt_with_reply_chain(self, mock_message):
        """Test DM prompt with reply chain."""
        metadata = MessageMetadata(
            **{
                "message_id": 123456,
                "timestamp": "2025-10-16T12:30:00",
                "author": AuthorMetadata(
                    **{
                        "id": 111222,
                        "username": "alice",
                        "display_name": "Alice",
                        "global_name": "Alice",
                        "is_bot": False,
                        "roles": [],
                    }
                ),
                "channel": ChannelMetadata(
                    **{
                        "id": 987654,
                        "name": "DM",
                        "type": "DM",
                    }
                ),
                "guild": None,
            }
        )

        reply_chain = ReplyChain(
            [
                MessageRecord(
                    **{
                        "message_id": 111111,
                        "author": "Bot",
                        "author_id": 123456,
                        "content": "How can I help?",
                        "clean_content": "How can I help?",
                        "timestamp": "2025-10-16T12:25:00",
                        "is_bot": True,
                        "has_attachments": False,
                        "has_embeds": False,
                    }
                ),
                MessageRecord(
                    **{
                        "message_id": 222222,
                        "author": "Alice",
                        "author_id": 111222,
                        "content": "I need info about X",
                        "clean_content": "I need info about X",
                        "timestamp": "2025-10-16T12:28:00",
                        "is_bot": False,
                        "has_attachments": False,
                        "has_embeds": False,
                    }
                ),
            ]
        )
        mock_message.content = "Actually, can you explain Y instead?"
        mock_message.clean_content = "Actually, can you explain Y instead?"
        prompt = build_dm_prompt(
            message=mock_message,
            metadata=metadata,
            reply_chain=reply_chain,
            include_mcp_guidance=True,
        )

        # Verify reply chain context
        assert "Bot" in prompt or "How can I help?" in prompt
        assert "Alice" in prompt
        assert "I need info about X" in prompt
        assert "Actually, can you explain Y instead?" in prompt


class TestBuildPrompt:
    """Tests for build_prompt function."""

    @pytest.fixture
    def mock_discord_message_factory(self, mocker):
        """Fixture to create a mock message."""

        from discord import Message

        def _factory(content: str) -> Message:
            message = mocker.MagicMock(spec=Message)
            message.id = 444444
            message.content = content
            message.clean_content = content
            message.created_at.isoformat.return_value = "2025-10-16T12:30:00"
            message.attachments = []
            message.embeds = []
            message.author.id = 111222
            message.author.name = "testuser"
            message.author.bot = False
            message.author.display_name = "Test User"
            message.channel.id = 987654
            message.channel.name = "general"
            message.guild.id = 555666
            message.guild.name = "Test Server"
            return message

        return _factory

    def test_build_mention_event_prompt(
        self, message_metadata, reply_chain, mock_discord_message_factory
    ):
        """Test that build_prompt correctly routes mention events."""
        context = (message_metadata, reply_chain)

        mock_message = mock_discord_message_factory("Test mention")

        prompt = build_prompt("mention", mock_message, context)

        # Should contain mention-specific elements
        assert "Test mention" in prompt
        assert "discord_read_messages" in prompt  # Server mentions get MCP guidance

    def test_build_dm_event_prompt(
        self, message_metadata, reply_chain, mock_discord_message_factory
    ):
        """Test that build_prompt correctly routes DM events."""
        context = (message_metadata, reply_chain)
        mock_message = mock_discord_message_factory("Test DM")
        prompt = build_prompt("dm", mock_message, context)

        # Should contain DM-specific elements
        assert "Test DM" in prompt
        assert "direct message" in prompt.lower() or "DM" in prompt

    def test_build_prompt_with_reply_chain(
        self, message_metadata, reply_chain, mock_discord_message_factory
    ):
        """Test build_prompt includes reply chain context."""
        context = (message_metadata, reply_chain)
        mock_message = mock_discord_message_factory("Checking reply chain")
        prompt = build_prompt("mention", mock_message, context)

        # Should include reply chain context
        assert "Alice" in prompt
        assert "What's the best Python linter?" in prompt
        assert "Bob" in prompt
        assert "I recommend Ruff" in prompt
