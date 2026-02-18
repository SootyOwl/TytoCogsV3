import pytest
from unittest.mock import Mock, patch

from redvids.redvids import (
    RedVidsError,
    download_reddit_video,
    check_video_result,
    video_path_to_discord_file,
)


@pytest.fixture
def REDDITURL():
    return "https://www.reddit.com/r/Minecraft/comments/1eszhxx/finally_minecarts_are_getting_updated_24w33a/"


@pytest.mark.asyncio
async def test_download_reddit_video(REDDITURL, tmp_path):
    """Test that download_reddit_video properly runs blocking operations in thread pool.
    
    This test mocks the Downloader class to avoid needing network access,
    and verifies that the async function properly handles the blocking operations.
    """
    # Create a mock video file path
    video_path = str(tmp_path / "test_video.mp4")
    
    # Create a mock Downloader
    mock_downloader = Mock()
    mock_downloader.check = Mock()
    mock_downloader.download = Mock(return_value=video_path)
    
    with patch('redvids.redvids.Downloader', return_value=mock_downloader):
        video = await download_reddit_video(
            REDDITURL, max_size=(1 << 12), path=str(tmp_path)
        )
        
        # Verify the downloader methods were called
        mock_downloader.check.assert_called_once()
        mock_downloader.download.assert_called_once()
        
        # Verify the result is the video path
        assert video == video_path


@pytest.mark.asyncio
async def test_download_reddit_video_size_exceeds(REDDITURL, tmp_path):
    """Test that SIZE_EXCEEDS_MAXIMUM error code is properly handled."""
    mock_downloader = Mock()
    mock_downloader.check = Mock()
    mock_downloader.download = Mock(return_value=0)  # Size exceeds error code
    
    with patch('redvids.redvids.Downloader', return_value=mock_downloader):
        video = await download_reddit_video(
            REDDITURL, max_size=(1 << 12), path=str(tmp_path)
        )
        
        # Verify the result is the error enum
        assert video == RedVidsError.SIZE_EXCEEDS_MAXIMUM


@pytest.mark.asyncio
async def test_download_reddit_video_duration_exceeds(REDDITURL, tmp_path):
    """Test that DURATION_EXCEEDS_MAXIMUM error code is properly handled."""
    mock_downloader = Mock()
    mock_downloader.check = Mock()
    mock_downloader.download = Mock(return_value=1)  # Duration exceeds error code
    
    with patch('redvids.redvids.Downloader', return_value=mock_downloader):
        video = await download_reddit_video(
            REDDITURL, max_size=(1 << 12), path=str(tmp_path)
        )
        
        # Verify the result is the error enum
        assert video == RedVidsError.DURATION_EXCEEDS_MAXIMUM


@pytest.mark.asyncio
async def test_download_reddit_video_file_exists(REDDITURL, tmp_path):
    """Test that FILE_EXISTS error code is properly handled."""
    mock_downloader = Mock()
    mock_downloader.check = Mock()
    mock_downloader.download = Mock(return_value=2)  # File exists error code
    
    with patch('redvids.redvids.Downloader', return_value=mock_downloader):
        video = await download_reddit_video(
            REDDITURL, max_size=(1 << 12), path=str(tmp_path)
        )
        
        # Verify the result is the error enum
        assert video == RedVidsError.FILE_EXISTS


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
    video = tmp_path / "video.mp4"
    video.touch()
    path = video.as_posix()
    
    # Mock discord.File
    with patch('redvids.redvids.discord.File') as mock_file:
        result = video_path_to_discord_file(path)
        mock_file.assert_called_once_with(path, filename="video.mp4")
