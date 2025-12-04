import pytest
from pytest_mock import MockerFixture
from types import SimpleNamespace

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
        (
            "https://www.youtube.com/watch?v=12345&feature=youtu.be&list=12345&index=1",
            "12345",
        ),
        ("Check out this video: https://www.youtube.com/watch?v=12345", "12345"),
        ("https://youtube.com/shorts/_4Bon7eYvOQ?si=aOrNjcgpLHGGXOry", "_4Bon7eYvOQ"),
        ("https://www.youtube.com/live/tWIEv_aksvo?si=cU0bdFlc5141ym_1", "tWIEv_aksvo"),
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
        (
            "NcZxaFfxloo",
            "JON STEWART: Is that the\nresult of their $5 million planning fund",
        ),  # en-US only
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
    # Test case 1: Basic test
    summary = "This is a test summary.```"
    cleaned_summary = tldw.cleanup_summary(summary)
    assert cleaned_summary.description == "This is a test summary."

    # Test case 2: Summary with multiple ```
    summary = "This is a test summary.```More text```"
    cleaned_summary = tldw.cleanup_summary(summary)
    assert cleaned_summary.description == "This is a test summary."

    # Test case 3: Summary without ```
    summary = "This is a test summary."
    cleaned_summary = tldw.cleanup_summary(summary)
    assert cleaned_summary.description == "This is a test summary."

    # Test case 4: Empty summary
    with pytest.raises(ValueError):
        tldw.cleanup_summary("")

    # Test case 5: Summary with ``` at the beginning
    with pytest.raises(ValueError):
        tldw.cleanup_summary("```This is a test summary.")

    # Test case 6: Summary with markdown title
    summary = "# Title\nThis is a test summary."
    cleaned_summary = tldw.cleanup_summary(summary)
    assert cleaned_summary.description == "This is a test summary."
    assert cleaned_summary.title == "Title"


# test cleanup_summary function with invalid input
def test_cleanup_summary_invalid_input():
    with pytest.raises(ValueError):
        tldw.cleanup_summary(None)


# test get_llm_response coroutine
@pytest.mark.asyncio
async def test_get_llm_response(mocker: MockerFixture):
    # FIXME: Update this test for the new AsyncLLM client (OpenRouter)
    # Mock the LLM Client (tldw.AsyncLLM)
    mock_client = mocker.AsyncMock()
    mock_response = mocker.patch(
        "openai.types.chat.chat_completion.ChatCompletion", autospec=True
    )
    mock_response.choices = [mocker.Mock()]
    mock_response.choices[0].message.content = "Test response"
    mock_client.chat.completions.create = mocker.AsyncMock(return_value=mock_response)
    # Test the get_llm_response function
    response = await tldw.get_llm_response(
        llm_client=mock_client,
        text="Test prompt",
        system_prompt=("You are a YouTube video note taker and summarizer."),
    )
    assert response == "Test response"
    assert isinstance(response, str)
    assert mock_client.chat.completions.create.called


@pytest.mark.asyncio
async def test_get_llm_response_strips_reasoning_parts(mocker: MockerFixture):
    mock_client = mocker.AsyncMock()
    reasoning_part = SimpleNamespace(type="reasoning", text="analysis goes here")
    text_part = SimpleNamespace(type="output_text", text="alTest response")

    message = mocker.Mock()
    message.content = [reasoning_part, text_part]

    choice = mocker.Mock()
    choice.message = message

    mock_response = mocker.Mock()
    mock_response.choices = [choice]

    mock_client.chat.completions.create = mocker.AsyncMock(return_value=mock_response)

    response = await tldw.get_llm_response(
        llm_client=mock_client,
        text="Test prompt",
        system_prompt=("You are a YouTube video note taker and summarizer."),
    )

    assert response == "Test response"


# test without mocking
@pytest.fixture
def llm_client():
    # load the .env file and get the api key
    from dotenv import load_dotenv

    from tldw.tldw import AsyncOpenAI

    load_dotenv()

    return AsyncOpenAI(base_url="https://openrouter.ai/api/v1")


@pytest.mark.asyncio
async def test_get_llm_response_without_mocker(llm_client):
    """Test the get_llm_response function without mocking."""
    # Test the get_llm_response function
    response = await tldw.get_llm_response(
        llm_client=llm_client,
        text="Test prompt",
        system_prompt=(
            "You are a YouTube video note taker and summarizer under test. Respond *only* with 'Test response'."
        ),
        model="openai/gpt-oss-safeguard-20b",
    )
    assert isinstance(response, str)
    assert response == "Test response"
