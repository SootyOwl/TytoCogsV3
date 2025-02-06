import pytest
from redbot.core import commands
from historylesson.historylesson import HistoryLesson
from redbot.core.bot import Red
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_set_api_key(historylesson_cog: HistoryLesson, context: commands.Context):
    """Test setting the API key."""
    context.guild = None  # simulate DM to bypass guild check
    api_key = "test_api_key"
    await historylesson_cog.set_api_key.callback(historylesson_cog, context, api_key)
    assert await historylesson_cog.config.api_key() == api_key
    assert historylesson_cog.anthropic_client is not None


@pytest.mark.asyncio
async def test_set_system_prompt(historylesson_cog: HistoryLesson, context: commands.Context):
    """Test setting the system prompt."""
    prompt = "You are a helpful assistant."
    await historylesson_cog.set_system_prompt.callback(historylesson_cog, context, prompt=prompt)
    assert await historylesson_cog.config.system_prompt() == prompt


@pytest.mark.asyncio
async def test_extract_article_content_success(historylesson_cog: HistoryLesson, mocker):
    """Test successful extraction of article content."""
    mock_article = mocker.MagicMock()
    mock_article.text = "This is a test article."
    mocker.patch("newspaper.Article", return_value=mock_article)

    url = "http://example.com/article"
    content = await historylesson_cog.extract_article_content(url)
    assert content == "This is a test article."


@pytest.mark.asyncio
async def test_extract_article_content_failure(historylesson_cog: HistoryLesson, mocker):
    """Test failure to extract article content."""
    mocker.patch("newspaper.Article", side_effect=Exception("Download failed"))

    url = "http://example.com/article"
    with pytest.raises(commands.UserFeedbackCheckFailure):
        await historylesson_cog.extract_article_content(url)


@pytest.mark.asyncio
async def test_generate_historical_context_success(historylesson_cog: HistoryLesson, mocker):
    """Test successful generation of historical context."""
    mock_anthropic_response = mocker.AsyncMock()
    mock_anthropic_response.content = [mocker.AsyncMock(text="Historical context.")]
    mock_anthropic_client = mocker.patch.object(historylesson_cog, "anthropic_client", new_callable=mocker.AsyncMock)
    mock_anthropic_client.messages.create.return_value = mock_anthropic_response

    news_content = "Test news content."
    context = await historylesson_cog.generate_historical_context(news_content)
    assert context == "Historical context."


@pytest.mark.asyncio
async def test_generate_historical_context_failure(historylesson_cog: HistoryLesson, mocker):
    """Test failure to generate historical context."""
    mocker.patch.object(
        historylesson_cog, "anthropic_client", new_callable=AsyncMock, side_effect=Exception("API error")
    )

    news_content = "Test news content."
    with pytest.raises(commands.UserFeedbackCheckFailure):
        await historylesson_cog.generate_historical_context(news_content)


@pytest.mark.asyncio
async def test_extract_summary_success(historylesson_cog: HistoryLesson):
    """Test successful extraction of summary."""
    text = "   Test summary.   "
    summary = await historylesson_cog.extract_summary(text)
    assert summary == "Test summary."


@pytest.mark.asyncio
async def test_extract_summary_empty(historylesson_cog: HistoryLesson):
    """Test extraction of summary from empty text."""
    text = ""
    summary = await historylesson_cog.extract_summary(text)
    assert summary == ""


@pytest.mark.asyncio
async def test_get_context_command_success(historylesson_cog: HistoryLesson, context, mocker):
    """Test the get_context command with mocked dependencies."""
    # Mock the helper functions to avoid actual API calls and newspaper calls
    mocker.patch.object(
        historylesson_cog, "extract_article_content", return_value="Test article content."
    )  # Mock article extraction
    mocker.patch.object(
        historylesson_cog, "generate_historical_context", return_value="Test historical context."
    )  # Mock Anthropic API call
    mocker.patch.object(historylesson_cog, "extract_summary", return_value="Test summary.")  # Mock summary extraction

    # Mock ctx.send to check the final output
    send_mock = mocker.patch.object(context, "send")

    # Call the command
    await historylesson_cog.get_context.callback(historylesson_cog, context, "http://example.com/article")

    # Assert that ctx.send was called with the expected output
    send_mock.assert_called_once_with("Test summary.")


@pytest.mark.asyncio
async def test_get_context_command_failure(historylesson_cog: HistoryLesson, context, mocker):
    """Test the get_context command with a mocked failure in article extraction."""
    # Mock extract_article_content to raise an exception
    mocker.patch.object(
        historylesson_cog,
        "extract_article_content",
        side_effect=commands.UserFeedbackCheckFailure("Failed to extract article"),
    )

    # Mock ctx.send to capture the error message
    send_mock = mocker.patch.object(context, "send")

    # Call the command
    await historylesson_cog.get_context.callback(historylesson_cog, context, "http://example.com/article")

    # Assert that ctx.send was called with the expected error message
    send_mock.assert_called_once_with("Failed to extract article")
