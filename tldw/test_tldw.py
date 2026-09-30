import json
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

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
    return tldw.YouTubeTranscriptFetcher()


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


# ---------------------------------------------------------------------------
# Offline tests for the transcript fetching (no network access needed)
# ---------------------------------------------------------------------------

WATCH_PAGE_HTML = (
    '<html><script>var ytcfg = {"INNERTUBE_API_KEY":"AIzaTestKey_123"};</script></html>'
)
CONSENT_PAGE_HTML = (
    '<html><form action="https://consent.youtube.com/s">'
    '<input type="hidden" name="v" value="cb.20260101-00-p0.en+FX+000" />'
    "</form></html>"
)
TIMEDTEXT_XML = (
    '<?xml version="1.0" encoding="utf-8" ?><transcript>'
    '<text start="0" dur="1.5">Hello &amp;#39;world&amp;#39;</text>'
    '<text start="1.5" dur="1">Second line</text>'
    "</transcript>"
)
JSON3_PAYLOAD = json.dumps(
    {
        "events": [
            {"segs": [{"utf8": "Hello "}, {"utf8": "world\n"}]},
            {"segs": []},
            {"segs": [{"utf8": "Second   line"}]},
        ]
    }
)
TRACK_URL = "https://www.youtube.com/api/timedtext?v=vid&fmt=srv3"


class CookieJarStub:
    """Minimal stand-in for aiohttp's cookie jar."""

    def __init__(self):
        self.cookies = {}

    def update_cookies(self, cookies, response_url=None):
        self.cookies.update(cookies)


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def text(self):
        return self._body

    async def json(self, content_type=None):
        return json.loads(self._body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class FakeSession:
    """A fake aiohttp session that replays scripted responses per request URL."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.cookie_jar = CookieJarStub()

    def _response(self, method, url):
        self.calls.append((method, url))
        for (route_method, needle), responses in self.routes.items():
            if route_method == method and needle in url:
                return responses.pop(0) if len(responses) > 1 else responses[0]
        raise AssertionError(f"unexpected request: {method} {url}")

    def get(self, url, **kwargs):
        return self._response("GET", url)

    def post(self, url, **kwargs):
        return self._response("POST", url)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def caption_track(code, kind=None, base_url=TRACK_URL):
    """Build a captionTracks entry as YouTube returns it."""
    track = {
        "languageCode": code,
        "name": {"runs": [{"text": code.upper()}]},
        "baseUrl": base_url,
    }
    if kind:
        track["kind"] = kind
    return track


def player_json(tracks, status="OK", reason=None):
    """Build a /youtubei/v1/player response."""
    playability = {"status": status}
    if reason:
        playability["reason"] = reason
    return json.dumps(
        {
            "playabilityStatus": playability,
            "captions": {"playerCaptionsTracklistRenderer": {"captionTracks": tracks}},
        }
    )


def test_timedtext_url_replaces_format_parameter():
    url = tldw._timedtext_url("https://x/api/timedtext?v=1&fmt=srv3&lang=en", "json3")
    assert url == "https://x/api/timedtext?v=1&lang=en&fmt=json3"


def test_parse_json3():
    assert tldw._parse_json3(JSON3_PAYLOAD) == "Hello world Second line"


def test_parse_json3_invalid_payload():
    assert tldw._parse_json3("<html>not json</html>") == ""


def test_parse_timedtext_xml_unescapes_entities():
    assert tldw._parse_timedtext_xml(TIMEDTEXT_XML) == "Hello 'world' Second line"


def test_parse_timedtext_xml_invalid_payload():
    assert tldw._parse_timedtext_xml("not xml") == ""


def test_select_caption_track_prefers_manual_captions():
    tracks = [
        tldw.CaptionTrack("en", "English", True, "asr-url"),
        tldw.CaptionTrack("en", "English", False, "manual-url"),
    ]
    selected = tldw._select_caption_track(tracks, ["en-US", "en"], "vid")
    assert selected.base_url == "manual-url"
    assert selected.is_generated is False


def test_select_caption_track_matches_primary_subtag():
    tracks = [tldw.CaptionTrack("pt-BR", "Portuguese (Brazil)", False, "url")]
    assert tldw._select_caption_track(tracks, ["pt-PT"], "vid").language_code == "pt-BR"


def test_select_caption_track_raises_for_unknown_language():
    tracks = [tldw.CaptionTrack("de", "German", True, "url")]
    with pytest.raises(tldw.TranscriptError):
        tldw._select_caption_track(tracks, ["en"], "vid")


@pytest.mark.asyncio
async def test_list_tracks_uses_api_key_from_watch_page():
    session = FakeSession(
        {
            ("GET", "/watch"): [FakeResponse(200, WATCH_PAGE_HTML)],
            ("POST", "/youtubei/v1/player"): [
                FakeResponse(200, player_json([caption_track("en")]))
            ],
        }
    )
    fetcher = tldw.YouTubeTranscriptFetcher()
    tracks = await fetcher.list_tracks(session, "vid")
    assert [track.language_code for track in tracks] == ["en"]
    assert any(
        "AIzaTestKey_123" in url for method, url in session.calls if method == "POST"
    )


@pytest.mark.asyncio
async def test_list_tracks_accepts_consent_wall():
    session = FakeSession(
        {
            ("GET", "/watch"): [
                FakeResponse(200, CONSENT_PAGE_HTML),
                FakeResponse(200, WATCH_PAGE_HTML),
            ],
            ("POST", "/youtubei/v1/player"): [
                FakeResponse(200, player_json([caption_track("en")]))
            ],
        }
    )
    fetcher = tldw.YouTubeTranscriptFetcher()
    tracks = await fetcher.list_tracks(session, "vid")
    assert len(tracks) == 1
    assert session.cookie_jar.cookies["CONSENT"].startswith("YES+")


@pytest.mark.asyncio
async def test_list_tracks_retries_with_the_next_client():
    rejected = json.dumps({"error": {"code": 400, "status": "FAILED_PRECONDITION"}})
    session = FakeSession(
        {
            ("GET", "/watch"): [FakeResponse(200, WATCH_PAGE_HTML)],
            ("POST", "/youtubei/v1/player"): [
                FakeResponse(400, rejected),
                FakeResponse(200, player_json([caption_track("en")])),
            ],
        }
    )
    fetcher = tldw.YouTubeTranscriptFetcher()
    tracks = await fetcher.list_tracks(session, "vid")
    assert len(tracks) == 1
    assert sum(1 for method, _ in session.calls if method == "POST") == 2


@pytest.mark.asyncio
async def test_list_tracks_reports_outdated_client_versions():
    rejected = json.dumps({"error": {"code": 400, "status": "FAILED_PRECONDITION"}})
    session = FakeSession(
        {
            ("GET", "/watch"): [FakeResponse(200, WATCH_PAGE_HTML)],
            ("POST", "/youtubei/v1/player"): [FakeResponse(400, rejected)],
        }
    )
    fetcher = tldw.YouTubeTranscriptFetcher()
    with pytest.raises(tldw.YouTubeClientError):
        await fetcher.list_tracks(session, "vid")


@pytest.mark.asyncio
async def test_list_tracks_reports_ip_block():
    payload = player_json(
        [], status="LOGIN_REQUIRED", reason="Sign in to confirm you're not a bot"
    )
    session = FakeSession(
        {
            ("GET", "/watch"): [FakeResponse(200, WATCH_PAGE_HTML)],
            ("POST", "/youtubei/v1/player"): [FakeResponse(200, payload)],
        }
    )
    fetcher = tldw.YouTubeTranscriptFetcher()
    with pytest.raises(tldw.YouTubeBlockedError):
        await fetcher.list_tracks(session, "vid")


@pytest.mark.asyncio
async def test_list_tracks_reports_missing_captions():
    session = FakeSession(
        {
            ("GET", "/watch"): [FakeResponse(200, WATCH_PAGE_HTML)],
            ("POST", "/youtubei/v1/player"): [FakeResponse(200, player_json([]))],
        }
    )
    fetcher = tldw.YouTubeTranscriptFetcher()
    with pytest.raises(tldw.TranscriptsDisabledError):
        await fetcher.list_tracks(session, "vid")


@pytest.mark.asyncio
async def test_download_track_falls_back_to_xml():
    track = tldw.CaptionTrack("en", "English", False, TRACK_URL)
    session = FakeSession(
        {
            ("GET", "fmt=json3"): [FakeResponse(200, "{}")],
            ("GET", "fmt=srv3"): [FakeResponse(200, TIMEDTEXT_XML)],
        }
    )
    fetcher = tldw.YouTubeTranscriptFetcher()
    assert await fetcher._download_track(session, track, "vid") == (
        "Hello 'world' Second line"
    )


@pytest.mark.asyncio
async def test_fetch_returns_transcript_text(monkeypatch):
    session = FakeSession(
        {
            ("GET", "/watch"): [FakeResponse(200, WATCH_PAGE_HTML)],
            ("POST", "/youtubei/v1/player"): [
                FakeResponse(
                    200, player_json([caption_track("en"), caption_track("en", "asr")])
                )
            ],
            ("GET", "fmt=json3"): [FakeResponse(200, JSON3_PAYLOAD)],
        }
    )
    monkeypatch.setattr(tldw.aiohttp, "ClientSession", lambda *args, **kwargs: session)
    fetcher = tldw.YouTubeTranscriptFetcher()
    assert await fetcher.fetch("vid", ["en-US", "en"]) == "Hello world Second line"


@pytest.mark.asyncio
async def test_get_transcript_wraps_errors_in_value_error(monkeypatch):
    payload = player_json([], status="ERROR", reason="This video is unavailable")
    session = FakeSession(
        {
            ("GET", "/watch"): [FakeResponse(200, WATCH_PAGE_HTML)],
            ("POST", "/youtubei/v1/player"): [FakeResponse(200, payload)],
        }
    )
    monkeypatch.setattr(tldw.aiohttp, "ClientSession", lambda *args, **kwargs: session)
    fetcher = tldw.YouTubeTranscriptFetcher()
    with pytest.raises(ValueError):
        await tldw.get_transcript(fetcher, "vid")
