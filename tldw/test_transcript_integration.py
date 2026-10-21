"""Regression coverage for the cog's synchronous transcript client boundary."""

import asyncio
import threading
from types import SimpleNamespace

import pytest
import requests
from yt_transcript_fetcher import NoTranscriptError, VideoNotFoundError
from yt_transcript_fetcher.exceptions import NoLanguageError, NoSegmentsError, YouTubeAPIError
from yt_transcript_fetcher.models import Language, LanguageList

from tldw import tldw


class Fetcher:
    """Model the network boundary without contacting YouTube."""

    def __init__(self, error=None, stage="discovery", text="Transcript text"):
        self.error = error
        self.stage = stage
        self.text = text
        self.calls = []
        self.session = SimpleNamespace(close=lambda: None)

    def list_languages(self, video_id):
        self.calls.append(("discovery", video_id))
        if self.error and self.stage == "discovery":
            raise self.error
        return LanguageList(
            [
                Language("en", "English", _continuation_token="manual"),
                Language("de", "German", _continuation_token="german"),
            ]
        )

    def get_transcript(self, video_id, language):
        self.calls.append(("transcript", video_id, language))
        if self.error and self.stage == "transcript":
            raise self.error
        return SimpleNamespace(text=self.text)


def http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError("private upstream details", response=response)


@pytest.mark.parametrize("stage", ["discovery", "transcript"])
@pytest.mark.parametrize(
    "error, expected",
    [
        (NoTranscriptError("private upstream details"), "no transcript"),
        (NoSegmentsError("private upstream details"), "no transcript"),
        (NoLanguageError("private upstream details"), "no transcript"),
        (VideoNotFoundError("private upstream details"), "accessible"),
        (YouTubeAPIError("private upstream details"), "YouTube"),
        (http_error(429), "rate limit"),
        (http_error(403), "YouTube"),
        (http_error(503), "YouTube"),
        (requests.HTTPError("private upstream details"), "YouTube"),
        (requests.Timeout("private upstream details"), "timed out"),
        (requests.ConnectionError("private upstream details"), "connect"),
        (requests.RequestException("private upstream details"), "network"),
    ],
)
async def test_transcript_failures_are_actionable_and_keep_the_cause(stage, error, expected):
    fetcher = Fetcher(error=error, stage=stage)
    with pytest.raises(ValueError) as caught:
        await tldw.get_transcript(fetcher, "dQw4w9WgXcQ")
    assert expected.lower() in str(caught.value).lower()
    assert "private upstream details" not in str(caught.value)
    assert caught.value.__cause__ is error
    # The cog must not retry the entire discovery/panel operation on top of the client.
    assert len(fetcher.calls) == (1 if stage == "discovery" else 2)


async def test_language_preferences_select_the_first_available_language():
    fetcher = Fetcher()
    text = await tldw.get_transcript(fetcher, "dQw4w9WgXcQ", languages=["fr", "de", "en"])
    assert text == "Transcript text"
    assert fetcher.calls[-1] == ("transcript", "dQw4w9WgXcQ", "de")


@pytest.mark.parametrize("languages", [["fr"], []])
async def test_unavailable_preferences_do_not_fetch_another_language(languages):
    fetcher = Fetcher()
    with pytest.raises(ValueError, match="Available languages:.*en.*de"):
        await tldw.get_transcript(fetcher, "dQw4w9WgXcQ", languages=languages)
    assert fetcher.calls == [("discovery", "dQw4w9WgXcQ")]


@pytest.mark.parametrize("text", ["", "   "])
async def test_empty_transcript_is_not_sent_for_summarization(text):
    with pytest.raises(ValueError, match="[Nn]o transcript"):
        await tldw.get_transcript(Fetcher(text=text), "dQw4w9WgXcQ")


async def test_transcript_fetching_leaves_the_event_loop_responsive():
    heartbeat = threading.Event()
    progressed = []

    class SlowFetcher(Fetcher):
        def list_languages(self, video_id):
            progressed.append(heartbeat.wait(timeout=1))
            return super().list_languages(video_id)

    asyncio.get_running_loop().call_soon(heartbeat.set)
    assert await tldw.get_transcript(SlowFetcher(), "dQw4w9WgXcQ") == "Transcript text"
    assert progressed == [True], "YouTube requests blocked the Discord event loop"


@pytest.fixture
async def cog(mocker):
    # Red's configuration storage and Discord's command tree are external services.
    mocker.patch.object(tldw.Config, "get_conf")
    cog = tldw.TLDWatch(mocker.Mock())
    cog.config.languages = mocker.AsyncMock(return_value=["en"])
    yield cog
    await cog.cog_unload()


async def test_summary_flow_caches_success_and_keeps_transcript_text(cog, mocker):
    fetcher = Fetcher()
    cog.yt_transcript_fetcher = fetcher
    cog.generate_summary = mocker.AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="# A title\nA summary."))],
            model="test-model",
            usage=None,
            created=0,
        )
    )
    summary = await cog.handlesummarize("https://youtu.be/dQw4w9WgXcQ")
    assert summary.title == "A title"
    assert summary.description == "A summary."
    assert summary.url == "https://youtu.be/dQw4w9WgXcQ"
    assert await cog.handlesummarize(summary.url) is summary
    cog.generate_summary.assert_awaited_once_with("Transcript text")
    assert len(fetcher.calls) == 2


async def test_failed_transcript_is_not_cached_or_sent_to_the_llm(cog, mocker):
    fetcher = Fetcher(error=http_error(429))
    cog.yt_transcript_fetcher = fetcher
    cog.generate_summary = mocker.AsyncMock()
    with pytest.raises(ValueError, match="rate limit"):
        await cog.handlesummarize("https://youtu.be/dQw4w9WgXcQ")
    assert not cog._summary_cache
    cog.generate_summary.assert_not_awaited()


async def test_cog_serializes_shared_session_even_after_cancellation(cog, mocker):
    started = threading.Event()
    release = threading.Event()
    second_started = threading.Event()

    class BlockingFetcher(Fetcher):
        def list_languages(self, video_id):
            if video_id == "first":
                started.set()
                release.wait(timeout=3)
            else:
                second_started.set()
            return super().list_languages(video_id)

    cog.yt_transcript_fetcher = BlockingFetcher()
    cog.generate_summary = mocker.AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="# Title\nSummary"))],
            model="test-model",
            usage=None,
            created=0,
        )
    )
    first = asyncio.create_task(cog.handlesummarize("https://youtu.be/first"))
    second = None
    try:
        assert await asyncio.to_thread(started.wait, 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(cog.handlesummarize("https://youtu.be/second"))
        # Allow the second command to reach its network boundary while the first worker is busy.
        assert not await asyncio.to_thread(second_started.wait, 0.1)
    finally:
        release.set()
        await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
    assert second_started.is_set()


async def test_unload_closes_the_owned_transcript_session(cog):
    closed = threading.Event()
    cog.yt_transcript_fetcher = Fetcher()
    cog.yt_transcript_fetcher.session.close = closed.set
    await cog.cog_unload()
    assert await asyncio.to_thread(closed.wait, 1)


async def test_command_waiting_for_config_does_not_fetch_after_unload(cog, mocker):
    entered = asyncio.Event()
    resume = asyncio.Event()
    fetcher = Fetcher()
    cog.yt_transcript_fetcher = fetcher
    cog.generate_summary = mocker.AsyncMock(side_effect=AssertionError("LLM invoked after unload"))

    async def languages():
        entered.set()
        await resume.wait()
        return ["en"]

    cog.config.languages = languages
    task = asyncio.create_task(cog.handlesummarize("https://youtu.be/dQw4w9WgXcQ"))
    try:
        await entered.wait()
        await cog.cog_unload()
    finally:
        resume.set()
    with pytest.raises(ValueError, match="reload"):
        await task
    assert not fetcher.calls


async def test_unload_during_fetch_does_not_use_the_closed_llm_client(cog, mocker):
    started = threading.Event()
    release = threading.Event()
    closed = threading.Event()

    class BlockingFetcher(Fetcher):
        def list_languages(self, video_id):
            started.set()
            release.wait(timeout=3)
            return super().list_languages(video_id)

    cog.yt_transcript_fetcher = BlockingFetcher()
    cog.yt_transcript_fetcher.session.close = closed.set
    cog.generate_summary = mocker.AsyncMock(side_effect=AssertionError("LLM invoked after unload"))
    task = asyncio.create_task(cog.handlesummarize("https://youtu.be/dQw4w9WgXcQ"))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        await cog.cog_unload()
        assert not closed.is_set(), "The session must stay open while its request is running"
        release.set()
        with pytest.raises(ValueError, match="reload"):
            await task
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    cog.generate_summary.assert_not_awaited()
    assert await asyncio.to_thread(closed.wait, 1)
