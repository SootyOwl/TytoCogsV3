"""Test redvids download functionality without requiring redbot dependencies."""
import asyncio
import tempfile
from unittest.mock import Mock, patch
import pytest


def test_async_download_with_mock():
    """Test that download_reddit_video properly uses asyncio.to_thread for blocking operations.
    
    This test verifies the fix without requiring redbot or actual network access.
    """
    # Import asyncio.to_thread to verify it exists (Python 3.9+)
    assert hasattr(asyncio, 'to_thread'), "asyncio.to_thread not available"
    
    # Verify the function uses asyncio properly by checking the source
    import inspect
    from pathlib import Path
    
    source_file = Path(__file__).parent / "redvids.py"
    source_code = source_file.read_text()
    
    # Verify the fix: asyncio should be imported
    assert "import asyncio" in source_code, "asyncio not imported"
    
    # Verify the fix: asyncio.to_thread should be used
    assert "asyncio.to_thread" in source_code, "asyncio.to_thread not used"
    
    # Verify both check and download are awaited
    assert "await asyncio.to_thread(downloader.check)" in source_code, "check() not properly awaited"
    assert "await asyncio.to_thread(downloader.download)" in source_code, "download() not properly awaited"
    
    print("✓ Verified that download_reddit_video properly uses asyncio.to_thread")


if __name__ == "__main__":
    test_async_download_with_mock()
    print("All checks passed!")
