import pytest

from spottube import spottube


# Test Spotify track ID extraction using urlparse
@pytest.mark.parametrize(
    "link, expected_track_id",
    [
        ("https://open.spotify.com/track/65ShmiE5aLBdcIGr7tHX35", "65ShmiE5aLBdcIGr7tHX35"),
        ("https://open.spotify.com/track/65ShmiE5aLBdcIGr7tHX35?si=d2e8de8114f5422b", "65ShmiE5aLBdcIGr7tHX35"),
        ("http://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("https://open.spotify.com/track/7qiZfU4dY1lWllzX7mPBI?si=xyz123", "7qiZfU4dY1lWllzX7mPBI"),
    ],
)
def test_extract_spotify_track_id(link, expected_track_id):
    """Test that the urlparse-based function correctly extracts track IDs."""
    track_id = spottube.extract_spotify_track_id(link)
    assert track_id == expected_track_id


# Test that non-Spotify links don't match
@pytest.mark.parametrize(
    "link",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "https://open.spotify.com/album/4aawyAB9vmqN3uQ7FjRGTy",
        "https://example.com/track/12345",
        "Just some random text",
    ],
)
def test_extract_spotify_track_id_no_match(link):
    """Test that non-track Spotify links don't return a track ID."""
    track_id = spottube.extract_spotify_track_id(link)
    assert track_id is None


# Test finding Spotify URLs in text
def test_find_spotify_track_urls_single():
    """Test finding a single Spotify track URL in text."""
    text = "Check this out: https://open.spotify.com/track/65ShmiE5aLBdcIGr7tHX35?si=abc123"
    urls = spottube.find_spotify_track_urls(text)
    assert len(urls) == 1
    assert urls[0] == "https://open.spotify.com/track/65ShmiE5aLBdcIGr7tHX35"


# Test that multiple Spotify links are detected
def test_find_spotify_track_urls_multiple():
    """Test that multiple Spotify links in a message are detected."""
    text = (
        "Check these out: https://open.spotify.com/track/65ShmiE5aLBdcIGr7tHX35 "
        "and https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp"
    )
    urls = spottube.find_spotify_track_urls(text)
    assert len(urls) == 2
    assert urls[0] == "https://open.spotify.com/track/65ShmiE5aLBdcIGr7tHX35"
    assert urls[1] == "https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp"


# Test that no Spotify links returns empty list
def test_find_spotify_track_urls_none():
    """Test that text without Spotify links returns empty list."""
    text = "Just some random text without any links"
    urls = spottube.find_spotify_track_urls(text)
    assert len(urls) == 0


# Test that playlist/album links are not detected
def test_find_spotify_track_urls_ignores_non_tracks():
    """Test that playlist and album links are ignored."""
    text = (
        "Playlist: https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M "
        "Album: https://open.spotify.com/album/4aawyAB9vmqN3uQ7FjRGTy"
    )
    urls = spottube.find_spotify_track_urls(text)
    assert len(urls) == 0

