from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI
from pytest_mock import MockerFixture
from yt_transcript_fetcher import YouTubeTranscriptFetcher

from tldw import tldw


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
    fetcher = YouTubeTranscriptFetcher()
    yield fetcher
    fetcher.session.close()


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
    # YouTube's modern panels can group caption lines differently.
    assert " ".join(expected.split()) in " ".join(transcript.split())


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
    response = mocker.Mock()
    response.choices = [mocker.Mock()]
    response.choices[0].message.content = "This is a test summary.```"
    cleaned_summary = tldw.cleanup_summary(response)
    assert cleaned_summary.description == "This is a test summary."

    # Test case 2: Summary with multiple ```
    response = mocker.Mock()
    response.choices = [mocker.Mock()]
    response.choices[0].message.content = "This is a test summary.```More text```"
    cleaned_summary = tldw.cleanup_summary(response)
    assert cleaned_summary.description == "This is a test summary."

    # Test case 3: Summary without ```
    response = mocker.Mock()
    response.choices = [mocker.Mock()]
    response.choices[0].message.content = "This is a test summary."
    cleaned_summary = tldw.cleanup_summary(response)
    assert cleaned_summary.description == "This is a test summary."

    # Test case 4: Empty summary
    with pytest.raises(ValueError):
        response = mocker.Mock()
        response.choices = [mocker.Mock()]
        response.choices[0].message.content = "   "
        tldw.cleanup_summary(response)

    # Test case 5: Summary with ``` at the beginning
    with pytest.raises(ValueError):
        response = mocker.Mock()
        response.choices = [mocker.Mock()]
        response.choices[0].message.content = "```This is a test summary."
        tldw.cleanup_summary(response)

    # Test case 6: Summary with markdown title
    response = mocker.Mock()
    response.choices = [mocker.Mock()]
    response.choices[0].message.content = "# Title\nThis is a test summary.```"
    cleaned_summary = tldw.cleanup_summary(response)
    assert cleaned_summary.description == "This is a test summary."
    assert cleaned_summary.title == "Title"


# test cleanup_summary function with invalid input
def test_cleanup_summary_invalid_input():
    with pytest.raises(ValueError):
        tldw.cleanup_summary(None)


# test get_llm_response coroutine
@pytest.mark.asyncio
async def test_get_llm_response(mocker: MockerFixture):
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
    assert response.choices[0].message.content == "Test response"
    assert isinstance(response, tldw.ChatCompletion)
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
    # strip out reasoning parts
    stripped_content = tldw.cleanup_summary(response)
    assert stripped_content.description == "Test response"


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
    response: tldw.ChatCompletion = await tldw.get_llm_response(
        llm_client=llm_client,
        text="Test prompt",
        system_prompt=(
            "You are a YouTube video note taker and summarizer under test. Respond *only* with 'Test response'."
        ),
        model="openai/gpt-oss-safeguard-20b",
    )
    assert response.choices[0].message.content == "Test response"


@pytest.mark.asyncio
@pytest.mark.parametrize("setting", [None, False, True])
async def test_reasoning_setting_reaches_openrouter(setting):
    import json

    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "# Summary"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    async with AsyncOpenAI(
        api_key="test",
        base_url="https://openrouter.test/api/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    ) as client:
        if setting is None:
            await tldw.get_llm_response(client, "Transcript", "Summarize")
        else:
            await tldw.get_llm_response(
                client, "Transcript", "Summarize", reasoning=setting
            )
    if setting is None:
        assert "reasoning" not in requests[0]
    else:
        assert requests[0]["reasoning"] == {"enabled": setting}
    assert requests[0]["models"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("setting", [False, True])
async def test_reasoning_command_updates_requests(mocker, setting):
    cog = object.__new__(tldw.TLDWatch)
    stored = {"value": None}

    async def read_setting():
        return stored["value"]

    async def write_setting(value):
        stored["value"] = value

    cog.config = SimpleNamespace(
        model=mocker.AsyncMock(return_value="test-model"),
        other_models=mocker.AsyncMock(return_value=[]),
        system_prompt=mocker.AsyncMock(return_value="Summarize"),
    )

    # Special methods are looked up on the type rather than the instance.
    class Setting:
        __call__ = staticmethod(read_setting)
        set = staticmethod(write_setting)

    cog.config.reasoning = Setting()
    cog.llm_client = SimpleNamespace(api_key="test")
    ctx = SimpleNamespace(send=mocker.AsyncMock())
    await tldw.TLDWatch.set_reasoning.callback(cog, ctx, setting)
    assert stored["value"] is setting
    request = mocker.patch.object(
        tldw, "get_llm_response", new_callable=mocker.AsyncMock
    )
    await cog.generate_summary("Transcript")
    assert request.call_args.kwargs["reasoning"] is setting
    await tldw.TLDWatch.set_reasoning.callback(cog, ctx)
    assert ("enabled" if setting else "disabled") in ctx.send.call_args.args[0].lower()
