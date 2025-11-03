"""Test relative time formatting for Aurora timestamps."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import discord

from aurora.utils.dataclasses import MessageRecord, MessageMetadata, AuthorMetadata, ChannelMetadata, GuildMetadata


class TestRelativeTimeFormatting:
    """Tests for relative time formatting in message display."""

    def test_message_record_includes_relative_time(self):
        """Test that MessageRecord.format() includes relative time."""
        # Create a message record from 5 minutes ago
        five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        
        msg_record = MessageRecord(
            message_id=123456,
            author="Test User",
            author_id=111222,
            content="Hello world",
            clean_content="Hello world",
            timestamp=five_min_ago.isoformat(),
            is_bot=False,
            has_attachments=False,
            has_embeds=False,
        )
        
        result = msg_record.format()
        
        # Should contain both absolute and relative time
        assert "UTC" in result
        assert "ago" in result
        assert "Test User" in result
        assert "Hello world" in result

    def test_message_record_with_hours(self):
        """Test MessageRecord with hours-old timestamp."""
        # Create a message record from 3 hours ago
        three_hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)
        
        msg_record = MessageRecord(
            message_id=789012,
            author="Another User",
            author_id=333444,
            content="Old message",
            clean_content="Old message",
            timestamp=three_hours_ago.isoformat(),
            is_bot=False,
            has_attachments=False,
            has_embeds=False,
        )
        
        result = msg_record.format()
        
        # Should contain relative time with hours
        assert "ago" in result
        assert "hour" in result or "3 hours" in result

    def test_message_record_with_days(self):
        """Test MessageRecord with days-old timestamp."""
        # Create a message record from 2 days ago
        two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
        
        msg_record = MessageRecord(
            message_id=345678,
            author="Old User",
            author_id=555666,
            content="Very old message",
            clean_content="Very old message",
            timestamp=two_days_ago.isoformat(),
            is_bot=False,
            has_attachments=False,
            has_embeds=False,
        )
        
        result = msg_record.format()
        
        # Should contain relative time with days
        assert "ago" in result
        assert "day" in result or "2 days" in result

    def test_message_metadata_includes_current_time(self):
        """Test that MessageMetadata.format() includes current time reference."""
        metadata = MessageMetadata(
            message_id=123456,
            timestamp=datetime.now(timezone.utc).isoformat(),
            author=AuthorMetadata(
                id=111222,
                username="testuser",
                display_name="Test User",
                global_name="Test User",
                is_bot=False,
                roles=[],
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
        
        result = metadata.format()
        
        # Should include current time reference
        assert "Current Time:" in result
        assert "Message Time:" in result
        assert "UTC" in result

    def test_message_metadata_includes_relative_time(self):
        """Test that MessageMetadata.format() includes relative time."""
        # Create metadata from 10 minutes ago
        ten_min_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
        
        metadata = MessageMetadata(
            message_id=123456,
            timestamp=ten_min_ago.isoformat(),
            author=AuthorMetadata(
                id=111222,
                username="testuser",
                display_name="Test User",
                global_name="Test User",
                is_bot=False,
                roles=[],
            ),
            channel=ChannelMetadata(
                id=987654,
                name="general",
                type="text",
            ),
            guild=None,
        )
        
        result = metadata.format()
        
        # Should include relative time
        assert "ago" in result
        assert "Message Time:" in result

    def test_invalid_timestamp_handling(self):
        """Test that invalid timestamps are handled gracefully."""
        msg_record = MessageRecord(
            message_id=123456,
            author="Test User",
            author_id=111222,
            content="Message",
            clean_content="Message",
            timestamp="invalid-timestamp",
            is_bot=False,
            has_attachments=False,
            has_embeds=False,
        )
        
        # Should not crash, just use the raw timestamp
        result = msg_record.format()
        assert "invalid-timestamp" in result

    def test_future_timestamp_handling(self):
        """Test that future timestamps display 'in X' format."""
        # Create a message record from 10 minutes in the future
        ten_min_future = datetime.now(timezone.utc) + timedelta(minutes=10)
        
        msg_record = MessageRecord(
            message_id=999888,
            author="Time Traveler",
            author_id=777888,
            content="Message from the future",
            clean_content="Message from the future",
            timestamp=ten_min_future.isoformat(),
            is_bot=False,
            has_attachments=False,
            has_embeds=False,
        )
        
        result = msg_record.format()
        
        # Should contain "in" instead of "ago" for future timestamps
        assert "in" in result
        assert "ago" not in result
