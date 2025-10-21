"""Unit tests for Aurora prompt template system."""

from aurora.utils.prompts import (
    build_mention_prompt,
    build_dm_prompt,
    build_prompt,
)


class TestBuildMentionPrompt:
    """Tests for build_mention_prompt function."""

    def test_basic_mention_prompt(self):
        """Test building a basic mention prompt."""
        metadata = {
            "message_id": "123456",
            "timestamp": "2025-10-16T12:30:00",
            "author": {
                "id": "111222",
                "display_name": "Test User",
                "roles": ["Member"],
            },
            "channel": {
                "id": "987654",
                "name": "general",
            },
            "guild": {
                "id": "555666",
                "name": "Test Server",
            },
        }

        content = "Hello @bot, how are you?"

        prompt = build_mention_prompt(
            message_content=content,
            metadata=metadata,
            reply_chain=[],
            include_mcp_guidance=True,
        )

        # Verify key components are in prompt
        assert "Test User" in prompt
        assert "general" in prompt
        assert "Test Server" in prompt
        assert "Hello @bot, how are you?" in prompt
        assert "discord_read_messages" in prompt  # MCP tool guidance
        assert "discord_send" in prompt  # MCP tool guidance

    def test_mention_prompt_with_reply_chain(self):
        """Test mention prompt with reply chain context."""
        metadata = {
            "message_id": "123456",
            "timestamp": "2025-10-16T12:30:00",
            "author": {
                "id": "111222",
                "display_name": "Test User",
                "roles": [],
            },
            "channel": {
                "id": "987654",
                "name": "tech-talk",
            },
            "guild": {
                "id": "555666",
                "name": "Dev Server",
            },
        }

        reply_chain = [
            {
                "message_id": "111111",
                "author": "Alice",
                "content": "What's the best Python linter?",
                "timestamp": "2025-10-16T12:25:00",
                "is_bot": False,
                "has_attachments": False,
                "has_embeds": False,
            },
            {
                "message_id": "222222",
                "author": "Bob",
                "content": "I recommend Ruff",
                "timestamp": "2025-10-16T12:28:00",
                "is_bot": False,
                "has_attachments": False,
                "has_embeds": False,
            },
        ]
        content = "@bot what do you think?"

        prompt = build_mention_prompt(
            message_content=content,
            metadata=metadata,
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

    def test_basic_dm_prompt(self):
        """Test building a basic DM prompt."""
        metadata = {
            "message_id": "123456",
            "timestamp": "2025-10-16T12:30:00",
            "author": {
                "id": "111222",
                "display_name": "Test User",
                "roles": [],
            },
            "channel": {
                "id": "987654",
                "name": "DM",
            },
            "guild": None,
        }

        content = "Hey bot, can you help me?"

        prompt = build_dm_prompt(
            message_content=content,
            metadata=metadata,
            reply_chain=[],
            include_mcp_guidance=True,
        )

        # Verify key components
        assert "Test User" in prompt
        assert "Hey bot, can you help me?" in prompt
        assert (
            "direct message" in prompt.lower() or "DM" in prompt
        )  # Should mention it's a DM

    def test_dm_prompt_with_reply_chain(self):
        """Test DM prompt with reply chain."""
        metadata = {
            "message_id": "123456",
            "timestamp": "2025-10-16T12:30:00",
            "author": {
                "id": "111222",
                "display_name": "Alice",
                "roles": [],
            },
            "channel": {
                "id": "987654",
                "name": "DM",
            },
            "guild": None,
        }

        reply_chain = [
            {
                "message_id": "111111",
                "author": "Bot",
                "content": "How can I help?",
                "timestamp": "2025-10-16T12:25:00",
                "is_bot": True,
                "has_attachments": False,
                "has_embeds": False,
            },
            {
                "message_id": "222222",
                "author": "Alice",
                "content": "I need info about X",
                "timestamp": "2025-10-16T12:28:00",
                "is_bot": False,
                "has_attachments": False,
                "has_embeds": False,
            },
        ]
        content = "Actually, can you explain Y instead?"

        prompt = build_dm_prompt(
            message_content=content,
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

    def test_build_mention_event_prompt(self):
        """Test that build_prompt correctly routes mention events."""
        context = {
            "metadata": {
                "message_id": "123456",
                "timestamp": "2025-10-16T12:30:00",
                "author": {"id": "111", "display_name": "User", "roles": []},
                "channel": {"id": "987", "name": "general"},
                "guild": {"id": "555", "name": "Server"},
            },
            "reply_chain": [],
        }

        prompt = build_prompt("mention", "Test mention", context)

        # Should contain mention-specific elements
        assert "Test mention" in prompt
        assert "discord_read_messages" in prompt  # Server mentions get MCP guidance

    def test_build_dm_event_prompt(self):
        """Test that build_prompt correctly routes DM events."""
        context = {
            "metadata": {
                "message_id": "123456",
                "timestamp": "2025-10-16T12:30:00",
                "author": {"id": "111", "display_name": "User", "roles": []},
                "channel": {"id": "987", "name": "DM"},
                "guild": None,
            },
            "reply_chain": [],
        }

        prompt = build_prompt("dm", "Test DM", context)

        # Should contain DM-specific elements
        assert "Test DM" in prompt
        assert "direct message" in prompt.lower() or "DM" in prompt

    def test_build_prompt_with_reply_chain(self):
        """Test build_prompt includes reply chain context."""
        context = {
            "metadata": {
                "message_id": "123456",
                "timestamp": "2025-10-16T12:30:00",
                "author": {"id": "111", "display_name": "User", "roles": []},
                "channel": {"id": "987", "name": "general"},
                "guild": {"id": "555", "name": "Server"},
            },
            "reply_chain": [
                {
                    "message_id": "111111",
                    "author": "Alice",
                    "content": "First message",
                    "timestamp": "2025-10-16T12:20:00",
                    "is_bot": False,
                    "has_attachments": False,
                    "has_embeds": False,
                },
                {
                    "message_id": "222222",
                    "author": "Bob",
                    "content": "Second message",
                    "timestamp": "2025-10-16T12:25:00",
                    "is_bot": False,
                    "has_attachments": False,
                    "has_embeds": False,
                },
            ],
        }

        prompt = build_prompt("mention", "Reply message", context)

        # Verify reply chain is formatted and included
        assert "Alice" in prompt
        assert "First message" in prompt
        assert "Bob" in prompt
        assert "Second message" in prompt
