import json
import pytest
from tldw import tldw

# test video url conversion
@pytest.mark.parametrize("video_url, expected", [
    ("https://www.youtube.com/watch?v=12345", "12345"),
    ("https://www.youtube.com/watch?v=12345&feature=youtu.be", "12345"),
    ("https://youtu.be/12345", "12345"),
    ("https://www.youtube.com/watch?v=12345&list=12345", "12345"),
    ("https://youtu.be/bD6PSBtQwww?si=zhDJtoJUxpzzQlic", "bD6PSBtQwww"),
    ("https://www.youtube.com/watch?v=12345&feature=youtu.be&list=12345", "12345"),
    ("https://www.youtube.com/watch?v=12345&feature=youtu.be&list=12345&index=1", "12345"),
])
def test_get_video_id(video_url, expected):
    assert tldw.get_video_id(video_url) == expected

# test video url conversion with invalid input raises an exception
@pytest.mark.parametrize("video_url", [
    "https://www.youtube.com/",
    "https://www.youtube.com/watch",
    "google.com",
    "some random text",
    "12345",
])
def test_get_video_id_invalid_input(video_url):
    with pytest.raises(ValueError):
        tldw.get_video_id(video_url)



# test get_transcript function
@pytest.fixture
def https_proxy():
    # open the .proxies file and read the https proxy
    return json.load(open(".proxies"))["https"]

@pytest.mark.asyncio
async def test_get_transcript(https_proxy):
    video_id = "75WFTHpOw8Y"  # bjork talking about tv
    transcript = await tldw.get_transcript(video_id, https_proxy)
    assert "hello it is Christmas time" in transcript

# test get_transcript function with invalid video id
@pytest.mark.asyncio
async def test_get_transcript_invalid_video_id(https_proxy):
    video_id = "invalid_video_id"
    with pytest.raises(ValueError):
        await tldw.get_transcript(video_id, https_proxy)
