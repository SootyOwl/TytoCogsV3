"""Ignore message tool for Discord."""

from pydantic import BaseModel, Field
from typing import Optional


class IgnoreMessageArgs(BaseModel):
    """Arguments for the ignore message tool."""

    reason: str = Field(..., description="The reason for ignoring the message.")
    category: Optional[str] = Field(
        default="bot",
        description="Category of the ignored message (e.g., 'bot', 'spam', 'not_relevant').",
    )


def ignore_message(reason: str, category: str = "bot") -> str:
    """
    Not every message warrants a reply (especially if the message isn't directed at you).
    Call this tool to ignore the message.

    Args:
        reason (str): The reason for ignoring the message.
        category (str): Category of the ignored message (default: 'bot').

    Returns:
        str: Confirmation message indicating the message has been ignored.
    """
    return f"IGNORED_MESSAGE::{category}::{reason}"
