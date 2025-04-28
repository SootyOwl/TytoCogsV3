import io
import os
import pytest
import requests
import unittest.mock as mock
import aiohttp

from ispyfj.ispyfj import IspyFJ, VideoNotFoundError


# Mock responses for testing
class MockResponse:
    def __init__(self, text, status_code=200, content=b"test content"):
        self.text = text
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP Error: {self.status_code}")

    def iter_content(self, chunk_size=1):
        yield self.content


# HTML templates for testing
VIDEO_TAG_HTML = """
<html>
<body>
<video id="content-video" src="https://example.com/video.mp4"></video>
</body>
</html>
"""

DATA_ATTR_HTML = """
<html>
<body>
<div class="contentContainer videoEle">
    <div class="flashmovie player videoContent">
        <a class="cnt-video-cont" 
           onclick="return content.makeVideo(this);" 
           data-cachedvideosrc="https://example.com/cached-video.mp4" 
           data-poster="https://example.com/poster.jpg">
            <div class="cnt-video-play"><!--  --></div>
            <img style="max-width: 100%; display: block;" src="https://example.com/poster.jpg" 
                 alt="Video title" title="Video title"/>
        </a>
    </div>
</div>
</body>
</html>
"""

JSON_LD_HTML = """
<html>
<body>
<script type="application/ld+json">
{
    "@context":"http://schema.org",
    "@type":"VideoObject",
    "description":"Video Description",
    "thumbnailUrl":"https://example.com/thumb.jpg",
    "contentUrl":"https://example.com/jsonld-video.mp4",
    "duration":"T10S",
    "uploadDate":"2023-01-01T00:00:00+00:00",
    "height":"1080",
    "width":"1920",
    "name":"Video Title"
}
</script>
</body>
</html>
"""

SCRIPT_VARS_HTML = """
<html>
<body>
<script>
    var videoUrl = "https://example.com/script-video.mp4";
    function playVideo() {
        // Some function
    }
</script>
</body>
</html>
"""

META_TAG_HTML = """
<html>
<head>
<meta property="og:video" content="https://example.com/meta-video.mp4" />
</head>
<body>
</body>
</html>
"""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "html_content, expected_url, extraction_method",
    [
        (VIDEO_TAG_HTML, "https://example.com/video.mp4", "_extract_from_video_tag"),
        (DATA_ATTR_HTML, "https://example.com/cached-video.mp4", "_extract_from_anchor"),
        (JSON_LD_HTML, "https://example.com/jsonld-video.mp4", "_extract_from_json_ld"),
        (SCRIPT_VARS_HTML, "https://example.com/script-video.mp4", "_extract_from_scripts"),
        (META_TAG_HTML, "https://example.com/meta-video.mp4", "_extract_from_meta"),
    ],
)
async def test_extraction_methods(html_content, expected_url, extraction_method):
    """Test different extraction methods."""
    # Create bot and cog instance
    mock_bot = mock.MagicMock()
    cog = IspyFJ(mock_bot)

    # Call the specific extraction method
    method = getattr(cog, extraction_method)
    result = method(html_content)

    # Verify result
    assert result == expected_url


@pytest.mark.asyncio
async def test_video_url_to_file():
    """Test file creation from video URL."""
    # Create mock response
    mock_resp = mock.AsyncMock()
    mock_resp.status = 200
    mock_resp.ok = True
    mock_resp.read = mock.AsyncMock(return_value=b"test video content")
    # Mock raise_for_status to do nothing for a successful mock
    mock_resp.raise_for_status = mock.Mock()


    # Create mock session
    mock_session = mock.AsyncMock()
    mock_session.get.return_value = mock_resp

    # Create bot and cog instance
    mock_bot = mock.MagicMock()
    cog = IspyFJ(mock_bot)

    # Assign the mock session to the cog
    cog.session = mock_session
    # Test file creation
    url = "https://example.com/test_video.mp4"
    file = await cog.video_url_to_file(url)

    # Assertions
    assert file.filename == "test_video.mp4"
    assert file.spoiler is False
    assert isinstance(file.fp, io.BytesIO)

    # Clean up
    file.close()


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling in get_video_url."""
    # Setup mock of aiohttp.ClientSession.get
    mock_get = mock.AsyncMock(side_effect=aiohttp.ClientError)
    with mock.patch("aiohttp.ClientSession.get", mock_get):
        # Create bot and cog instance
        mock_bot = mock.MagicMock()
        cog = IspyFJ(mock_bot)

        # Test error handling
        with pytest.raises(VideoNotFoundError):
            await cog.get_video_url("https://example.com")


@pytest.mark.asyncio
async def test_find_video_url():
    """Test the combined _find_video_url method."""
    # Create bot and cog instance
    mock_bot = mock.MagicMock()
    cog = IspyFJ(mock_bot)

    # Test the method
    video_url = cog._find_video_url(html=DATA_ATTR_HTML)

    # Assertions
    assert video_url == "https://example.com/cached-video.mp4"


@pytest.fixture
def funnyjunk_credentials():
    from dotenv import load_dotenv

    load_dotenv()

    return {
        "username": os.getenv("FUNNYJUNK_USERNAME", "test_username"),
        "password": os.getenv("FUNNYJUNK_PASSWORD", "test_password"),
    }


# try with actual url: https://funnyjunk.com/Crose+rid/wrrcTje/
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,input_url, expected_url",
    [
        (
            "Crose Rid",
            "https://funnyjunk.com/Crose+rid/wrrcTje/",
            "https://bigmemes123.funnyjunk.com/movies/Crose+rid_5be80c_12352736.mp4",
        ),
        # TODO: Add more real URLs to test the various extraction methods
        (  # normal video URL
            "How dreaming feels like",
            "https://funnyjunk.com/How+dreaming+feels+like/vttzRig/",
            "https://bigmemes123.funnyjunk.com/hdgifs/How+dreaming+feels+like_247d10_11748871.mp4",
        ),
        (  # spaces in the video URL are replaced with '+'
            "Unkempt luckless rapidfire",
            "https://funnyjunk.com/Unkempt+luckless+rapidfire/GivzRTv/",
            "https://loginportal123.funnyjunk.com/hdgifs/Unkempt+luckless+rapgym+boyzire_4c3d1f_11751038.mp4",
        ),
    ],
)
async def test_get_video_url(name, input_url, expected_url):
    """Test the get_video_url method"""
    # Create bot and cog instance
    mock_bot = mock.MagicMock()
    cog = IspyFJ(mock_bot)

    # Test the method
    video_url = await cog.get_video_url(input_url)

    # Assertions
    assert video_url == expected_url


@pytest.mark.asyncio
async def test_get_video_url_login_required(funnyjunk_credentials):
    url = "https://funnyjunk.com/White+people+things/jcveTwp/"
    expected = "https://loginportal123.funnyjunk.com/hdgifs/White+people+things_5635e1_12450679.mp4"

    # Create bot and cog instance
    mock_bot = mock.MagicMock()
    cog = IspyFJ(mock_bot)

    # login to the site
    await cog.login_to_funnyjunk(**funnyjunk_credentials)

    # assert the session's cookies are set
    assert cog.session.cookie_jar.filter_cookies("https://funnyjunk.com").get("fjsession") is not None
    assert cog.session.cookie_jar.filter_cookies("https://funnyjunk.com").get("userId") is not None

    # Test the method
    video_url = await cog.get_video_url(url)

    # Assertions
    assert video_url == expected