"""Context extraction utilities for Aurora event system.

This module provides functions to extract and format contextual information
from Discord messages for the Letta agent.
"""

import logging

import discord

from aurora.utils.dataclasses import MessageMetadata, ReplyChain

log = logging.getLogger("red.tyto.aurora.context")


async def extract_message_metadata(message: discord.Message) -> MessageMetadata:
    """Extract metadata from a Discord message.

    Args:
        message: The Discord message to extract metadata from

    Returns:
        Dictionary containing message metadata including author, channel, and guild info
    """
    return MessageMetadata.from_message(message)


async def extract_reply_chain(
    message: discord.Message, max_depth: int = 5
) -> ReplyChain:
    """Recursively extract reply chain from a Discord message.

    Fetches parent messages up to max_depth to provide conversation thread context.
    Returns chronologically ordered list (oldest first).

    Args:
        message: The Discord message to extract reply chain from
        max_depth: Maximum number of parent messages to fetch (default: 5)

    Returns:
        List of message dictionaries in chronological order (oldest first)
    """
    chain = ReplyChain()
    current = message.reference
    depth = 0

    while current and current.message_id and depth < max_depth:
        try:
            # Fetch the parent message
            parent = await message.channel.fetch_message(current.message_id)

            # Add to chain (insert at beginning for chronological order)
            chain.insert(parent)

            # Move to next parent
            current = parent.reference
            depth += 1

        except discord.NotFound:
            log.debug(f"Parent message {current.message_id} not found (deleted?)")
            break
        except discord.Forbidden:
            log.warning(f"No permission to fetch message {current.message_id}")
            break
        except Exception as e:
            log.exception(f"Error fetching parent message: {e}")
            break

    if chain:
        log.debug(
            f"Extracted reply chain of {len(chain)} messages for message {message.id}"
        )

    return chain


def format_reply_chain(reply_chain: ReplyChain) -> str:
    """Format reply chain into human-readable text.

    Args:
        reply_chain: ReplyChain dataclass instance

    Returns:
        Formatted string representation of the reply chain
    """
    return reply_chain.format_yaml()


def format_metadata_for_prompt(metadata: MessageMetadata) -> str:
    """Format metadata into human-readable text for prompt.

    Args:
        metadata: Message metadata dictionary from extract_message_metadata()

    Returns:
        Formatted string representation of metadata
    """
    return metadata.format()


async def build_event_context(
    message: discord.Message, max_reply_depth: int = 5
) -> tuple[MessageMetadata, ReplyChain]:
    """Build complete event context for a Discord message.

    This is the main function that combines metadata and reply chain extraction.

    Args:
        message: The Discord message to build context for
        max_reply_depth: Maximum depth for reply chain extraction (default: 5)

    Returns:
        Tuple of (MessageMetadata, ReplyChain)
    """
    metadata = await extract_message_metadata(message)
    reply_chain = await extract_reply_chain(message, max_depth=max_reply_depth)

    return (
        metadata,
        reply_chain,
    )
