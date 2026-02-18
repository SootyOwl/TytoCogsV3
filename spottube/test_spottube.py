import re

import pytest

from spottube import spottube


# Test Spotify link regex pattern
@pytest.mark.parametrize(
    "link, expected_track_id",
    [
        ("https://open.spotify.com/track/65ShmiE5aLBdcIGr7tHX35", "65ShmiE5aLBdcIGr7tHX35"),
        ("https://open.spotify.com/track/65ShmiE5aLBdcIGr7tHX35?si=d2e8de8114f5422b", "65ShmiE5aLBdcIGr7tHX35"),
        ("http://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("Check this out: https://open.spotify.com/track/7qiZfU4dY1lWllzX7mPBI", "7qiZfU4dY1lWllzX7mPBI"),
    ],
)
def test_spotify_track_regex(link, expected_track_id):
    """Test that the Spotify track regex correctly extracts track IDs."""
    matches = spottube.SPOTIFY_TRACK_REGEX.findall(link)
    assert len(matches) == 1
    assert matches[0] == expected_track_id


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
def test_spotify_track_regex_no_match(link):
    """Test that non-track Spotify links don't match the regex."""
    matches = spottube.SPOTIFY_TRACK_REGEX.findall(link)
    assert len(matches) == 0


# Test that multiple Spotify links are detected
def test_spotify_track_regex_multiple_links():
    """Test that multiple Spotify links in a message are detected."""
    message = (
        "Check these out: https://open.spotify.com/track/65ShmiE5aLBdcIGr7tHX35 "
        "and https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp"
    )
    matches = spottube.SPOTIFY_TRACK_REGEX.findall(message)
    assert len(matches) == 2
    assert matches[0] == "65ShmiE5aLBdcIGr7tHX35"
    assert matches[1] == "3n3Ppam7vgaVa1iaRUc9Lp"
