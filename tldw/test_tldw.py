import os

import pytest

from tldw import tldw
from yt_transcript_fetcher import YouTubeTranscriptFetcher

# test video url conversion
@pytest.mark.parametrize(
    "video_url, expected",
    [
        ("https://www.youtube.com/watch?v=12345", "12345"),
        ("https://www.youtube.com/watch?v=12345&feature=youtu.be", "12345"),
        ("https://youtu.be/12345", "12345"),
        ("https://www.youtube.com/watch?v=12345&list=12345", "12345"),
        ("https://youtu.be/bD6PSBtQwww?si=zhDJtoJUxpzzQlic", "bD6PSBtQwww"),
        ("https://www.youtube.com/watch?v=12345&feature=youtu.be&list=12345", "12345"),
        ("https://www.youtube.com/watch?v=12345&feature=youtu.be&list=12345&index=1", "12345"),
        ("Check out this video: https://www.youtube.com/watch?v=12345", "12345"),
        ("https://youtube.com/shorts/_4Bon7eYvOQ?si=aOrNjcgpLHGGXOry", "_4Bon7eYvOQ"),
    ],
)
def test_get_video_id(video_url, expected):
    assert tldw.get_video_id(video_url) == expected


# test video url conversion with invalid input raises an exception
@pytest.mark.parametrize(
    "video_url",
    [
        "https://www.youtube.com/",
        "https://www.youtube.com/watch",
        "google.com",
        "some random text",
        "12345",
    ],
)
def test_get_video_id_invalid_input(video_url):
    with pytest.raises(ValueError):
        tldw.get_video_id(video_url)


@pytest.fixture
def ytt_api():
    return YouTubeTranscriptFetcher()


@pytest.mark.parametrize(
    "video_id, expected",
    [
        ("75WFTHpOw8Y", "hello it is Christmas time"),  # bjork talking about tv
        # ("j04IAbWCszg", "in short this equation derived and published by"), # en-GB only, Matt Parker talking about tariffs
        ("NcZxaFfxloo", "JON STEWART: Is that the\nresult of their $5 million planning fund"),  # en-US only
    ],
)
@pytest.mark.asyncio
async def test_get_transcript(ytt_api, video_id, expected):
    transcript = await tldw.get_transcript(ytt_api, video_id)
    assert expected in transcript

@pytest.mark.asyncio
async def test_get_transcript_languages(ytt_api):
    video_id = "rnCVlVSE5pI"  # de
    transcript = await tldw.get_transcript(ytt_api, video_id, languages=["en", "de"])
    assert "da bin ich wieder" in transcript


# test get_transcript function with invalid video id
@pytest.mark.asyncio
async def test_get_transcript_invalid_video_id(ytt_api):
    video_id = "invalid_video_id"
    with pytest.raises(ValueError):
        await tldw.get_transcript(ytt_api, video_id)


# test cleanup_summary function
def test_cleanup_summary(mocker):
    # Mock the TextBlock object so it can be used in the test
    class MockTextBlock:
        def __init__(self, text):
            self.text = text

        def __str__(self):
            return self.text

    # Mock the TextBlock class in the tldw module so type checking works
    mocker.patch("tldw.tldw.ContentBlock", MockTextBlock)
    mocker.patch("tldw.tldw.TextBlock", MockTextBlock)

    # Test case 1: Basic test
    summary = [MockTextBlock("This is a test summary.```")]
    cleaned_summary = tldw.cleanup_summary(summary)
    assert cleaned_summary == "This is a test summary."

    # Test case 2: Summary with multiple ```
    summary = [MockTextBlock("This is a test summary.```More text```")]
    cleaned_summary = tldw.cleanup_summary(summary)
    assert cleaned_summary == "This is a test summary."

    # Test case 3: Summary without ```
    summary = [MockTextBlock("This is a test summary.")]
    cleaned_summary = tldw.cleanup_summary(summary)
    assert cleaned_summary == "This is a test summary."

    # Test case 4: Empty summary
    summary = [MockTextBlock("")]
    cleaned_summary = tldw.cleanup_summary(summary)
    assert cleaned_summary == ""

    # Test case 5: Summary with ``` at the beginning
    summary = [MockTextBlock("```This is a test summary.")]
    cleaned_summary = tldw.cleanup_summary(summary)
    assert cleaned_summary == ""


# test cleanup_summary function with invalid input
def test_cleanup_summary_invalid_input():
    with pytest.raises(ValueError):
        tldw.cleanup_summary(None)


# test get_llm_response coroutine
@pytest.mark.asyncio
async def test_get_llm_response(mocker):
    from tldw.tldw import TextBlock

    # Mock the Anthropic LLM Client (tldw.AsyncLLM)
    mock_client = mocker.Mock()
    # mock the messages.create method to return a mock response
    mock_response = mocker.Mock()
    mock_response.content = [TextBlock(text="Test response", type="text")]
    # make the .messages.create a coroutine
    mock_client.messages.create = mocker.AsyncMock(return_value=mock_response)
    # Mock the Anthropic LLM Client (tldw.AsyncLLM) in the tldw module
    mocker.patch("tldw.tldw.AsyncLLM", return_value=mock_client)
    # Test the get_llm_response function
    response = await tldw.get_llm_response(
        llm_client=mock_client, text="Test prompt", system_prompt=("You are a YouTube video note taker and summarizer.")
    )
    assert response[0].text == "Test response"
    assert isinstance(response[0], TextBlock)
    assert mock_client.messages.create.called_once_with(
        model="claude-3-5-sonnet-latest",
        max_tokens=2048,
        temperature=0,
        system="You are a YouTube video note taker and summarizer.",
        tool_choice={"type": "none"},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Test prompt"},
                    {
                        "type": "text",
                        "text": "Summarise the key points in this video transcript in the form of markdown-formatted concise notes.",
                    },
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "Here are the key points from the video transcript:\n\n```markdown",
                    }
                ],
            },
        ],
    )


# test without mocking
@pytest.fixture
def llm_client():
    # load the .env file and get the api key
    from dotenv import load_dotenv

    from tldw.tldw import AsyncLLM

    load_dotenv()

    return AsyncLLM()


@pytest.mark.asyncio
async def test_get_llm_response_without_mocker(llm_client):
    from tldw.tldw import TextBlock

    # Test the get_llm_response function
    response = await tldw.get_llm_response(
        llm_client=llm_client,
        text="Test prompt",
        system_prompt=("You are a YouTube video note taker and summarizer, under test. Respond *only* with 'Test response'."),  # type: ignore
    )
    assert isinstance(response[0], TextBlock)
    assert response[0].text == "\nTest response\n```"
