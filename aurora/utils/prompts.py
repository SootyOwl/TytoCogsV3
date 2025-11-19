"""Prompt templates for Aurora event system.

This module provides functions to construct context-rich prompts for the Letta agent
based on different event types (mentions, DMs).
"""

import logging

from aurora.utils.dataclasses import MessageMetadata, ReplyChain

from .context import format_metadata_for_prompt, format_reply_chain

log = logging.getLogger("red.tyto.aurora.prompts")


def build_mention_prompt(
    message_content: str,
    metadata: MessageMetadata,
    reply_chain: ReplyChain,
    include_mcp_guidance: bool = True,
) -> str:
    """Build prompt for mention/reply events in server channels.

    Args:
        message_content: The actual message content
        metadata: Message metadata from context.extract_message_metadata()
        reply_chain: Reply chain from context.extract_reply_chain()
        include_mcp_guidance: Whether to include MCP tool usage hints (default: True)

    Returns:
        Formatted prompt string for the Letta agent
    """
    author_name = f"{metadata.author.display_name} | {metadata.author.global_name}"
    author_id = metadata.author.id
    channel_id = metadata.channel.id
    guild_id = metadata.guild.id if metadata.guild else ""
    message_id = metadata.message_id

    # Build prompt sections
    prompt_parts = [
        "[Message Notification]",
        f"You received a mention or reply on Discord from {author_name} ({author_id})",
        "",
        "**Context:**",
        format_metadata_for_prompt(metadata),
    ]

    # Add reply chain if present
    if reply_chain:
        prompt_parts.extend(
            [
                "",
                "**Reply Thread:**",
                "This message is part of a conversation thread. The previous messages are (YAML):",
                "```yaml",
                format_reply_chain(reply_chain),
                "```",
            ]
        )

    # Add current message
    prompt_parts.extend(
        [
            "",
            "**Current Message (the mention you're responding to):**",
            f"{author_name}: {message_content}",
        ]
    )

    # Add MCP tool guidance if enabled
    if include_mcp_guidance:
        prompt_parts.extend(
            [
                "",
                "**Available Tools:**",
                "You have access to MCP Discord tools to gather context and respond:",
                f'- discord_get_server_info(guildId="{guild_id}"): Get detailed server information',
                f'- discord_read_messages(channelId="{channel_id}", limit=20): Read recent channel messages for context',
                f'- discord_search_messages(guildId="{guild_id}", ...): Search server-wide messages for relevant info, if needed',
                f'- discord_send(channelId="{channel_id}", message="your response", replyToMessageId="{message_id}"): Send your response',
                "- discord_add_reaction(channelId, messageId, emoji): React to messages",
                "...and more.",
                "",
                "You also have access to web search and browsing tools to gather external information if needed, as well as the ability to run code.",
                "**To Reply:**",
                "1. First, consider calling tools to understand the recent conversation context",
                "2. Then call `discord_send` to respond",
                "   - Set replyToMessageId to reply directly to the mention",
                "   - For most responses, a single `discord_send` call is sufficient",
                "   - Only use multiple calls if you're addressing multiple distinct messages or topics",
            ]
        )

    return "\n".join(prompt_parts)


def build_dm_prompt(
    message_content: str,
    metadata: MessageMetadata,
    reply_chain: ReplyChain,
    include_mcp_guidance: bool = True,
) -> str:
    """Build prompt for direct message events.

    Args:
        message_content: The actual message content
        metadata: Message metadata from context.extract_message_metadata()
        reply_chain: Reply chain from context.extract_reply_chain()
        include_mcp_guidance: Whether to include MCP tool usage hints (default: True)

    Returns:
        Formatted prompt string for the Letta agent
    """
    channel_id = metadata.channel.id
    message_id = metadata.message_id

    # Build prompt sections
    prompt_parts = [
        "You received a direct message on Discord.",
        "",
        "**Context:**",
        format_metadata_for_prompt(metadata),
    ]

    # Add reply chain if present
    if reply_chain:
        prompt_parts.extend(
            [
                "",
                "**Previous Messages in Thread:**",
                "```yaml",
                format_reply_chain(reply_chain),
                "```",
            ]
        )

    # Add current message
    prompt_parts.extend(
        [
            "",
            "**Current Message:**",
            message_content,
        ]
    )

    # Add MCP tool guidance if enabled
    if include_mcp_guidance:
        prompt_parts.extend(
            [
                "",
                "**Available Tools:**",
                "You have access to MCP Discord tools:",
                f'- discord_read_messages(channelId="{channel_id}", limit=20): Review your DM conversation history',
                f'- discord_send(channelId="{channel_id}", message="your response", replyToMessageId="{message_id}"): Send your response',
                "",
                "**To Reply:**",
                "1. If you wish to, call `discord_read_messages` to review recent conversation context",
                "2. Call `discord_send` to respond to this direct message",
                "   - For most responses, a single `discord_send` call is sufficient",
                "   - Set replyToMessageId if you want to reply to a specific message",
            ]
        )

    return "\n".join(prompt_parts)


def build_prompt(
    interaction_type: str,
    message_content: str,
    context: tuple[MessageMetadata, ReplyChain],
    include_mcp_guidance: bool = True,
) -> str:
    """Build appropriate prompt based on event type.

    This is the main entry point for prompt construction.

    Args:
        event_type: Type of event ("mention" or "dm")
        message_content: The actual message content
        context: Event context from context.build_event_context()
        include_mcp_guidance: Whether to include MCP tool usage hints (default: True)

    Returns:
        Formatted prompt string for the Letta agent

    Raises:
        ValueError: If event_type is not recognized
    """
    metadata, reply_chain = context

    if interaction_type == "mention":
        return build_mention_prompt(
            message_content, metadata, reply_chain, include_mcp_guidance
        )
    elif interaction_type == "dm":
        return build_dm_prompt(
            message_content, metadata, reply_chain, include_mcp_guidance
        )
    else:
        raise ValueError(f"Unknown event type: {interaction_type}")
