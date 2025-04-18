import json
import pytest
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


# test get_transcript function
@pytest.fixture
def https_proxy():
    # open the .proxies file and read the https proxy
    proxies = json.load(open(".proxies"))["https"]
    # choose a random one to return if it's a list
    if isinstance(proxies, list):
        import random

        proxies = random.choice(proxies)
    # if it's a string, return it as is
    elif isinstance(proxies, str):
        return proxies
    # if it's neither, raise an exception
    else:
        raise ValueError("Invalid proxy format in .proxies file")

@pytest.mark.parametrize(
    "video_id, expected",
    [
        ("75WFTHpOw8Y", "hello it is Christmas time"), # bjork talking about tv
        ("j04IAbWCszg", "in short this equation derived and published by"), # en-GB only, Matt Parker talking about tariffs
        ("NcZxaFfxloo", "JON STEWART: Is that the\nresult of their $5 million\nplanning fund"), # en-US only
    ],
)
@pytest.mark.asyncio
async def test_get_transcript(https_proxy, video_id, expected):
    transcript = await tldw.get_transcript(video_id, https_proxy)
    assert expected in transcript


# test get_transcript function with invalid video id
@pytest.mark.asyncio
async def test_get_transcript_invalid_video_id(https_proxy):
    video_id = "invalid_video_id"
    with pytest.raises(ValueError):
        await tldw.get_transcript(video_id, https_proxy)


# test cleanup_summary function
def test_cleanup_summary():
    # Mock the TextBlock object
    class MockTextBlock:
        def __init__(self, text):
            self.text = text

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
