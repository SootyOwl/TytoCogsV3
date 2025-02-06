import pytest
from redbot.core import commands
from redbot.core.bot import Red
from anthropic import AsyncAnthropic
import discord
from historylesson.historylesson import HistoryLesson

@pytest.fixture
def bot(mocker) -> Red:
    """Fixture for a Red bot instance."""
    return mocker.MagicMock(spec=Red)


@pytest.fixture
def context(bot: Red, mocker) -> commands.Context:
    """Fixture for a commands.Context instance."""
    ctx = mocker.MagicMock(spec=commands.Context)
    ctx.bot = bot
    ctx.author = mocker.MagicMock(spec=discord.Member)
    ctx.guild = mocker.MagicMock(spec=discord.Guild)
    return ctx


@pytest.fixture
def historylesson_cog(bot: Red, mocker) -> "HistoryLesson":
    """Fixture for the HistoryLesson cog."""

    mock_anthropic_client = mocker.AsyncMock(spec=AsyncAnthropic)
    cog = HistoryLesson(bot, mock_anthropic_client)
    cog.config = mocker.AsyncMock()
    cog.config.api_key = mocker.AsyncMock(return_value="test_api_key")
    cog.config.system_prompt = mocker.AsyncMock(return_value="You are a helpful assistant.")
    return cog