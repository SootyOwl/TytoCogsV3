import pytest

from redvids.redvids import RedVidsError, download_reddit_video, check_video_result, video_path_to_discord_file

import tempfile


@pytest.fixture
def REDDITURL():
    return "https://www.reddit.com/r/Minecraft/comments/1eszhxx/finally_minecarts_are_getting_updated_24w33a/"


@pytest.mark.asyncio
async def test_download_reddit_video(request, REDDITURL, tmp_path):
    video = await download_reddit_video(REDDITURL, max_size=(1 << 12), path=tmp_path.name)
    assert video is not None


def test_check_video_result(tmp_path):
    """Test the check_video_result function.

    The function should return the video path if the video is valid,
    otherwise it should return a RedVidsError.
    """
    video = tmp_path / "video.mp4"
    video.touch()
    assert check_video_result(video) == video
    assert check_video_result(0) == RedVidsError.SIZE_EXCEEDS_MAXIMUM
    assert check_video_result(1) == RedVidsError.DURATION_EXCEEDS_MAXIMUM
    assert check_video_result(2) == RedVidsError.FILE_EXISTS


def test_video_path_to_discord_file(tmp_path):
    with tempfile.TemporaryFile(dir=tmp_path) as tempdir:
        video = tmp_path / "video.mp4"
        video.touch()
        path = video.as_posix()
        file = video_path_to_discord_file(path)
        assert file.fp.name == path
        assert file.filename == "video.mp4"
