import io

import pytest
import requests

from ispyfj.ispyfj import get_video_url, video_url_to_file


@pytest.mark.parametrize(
    "url, expected",
    [
        (  # normal video URL
            "https://funnyjunk.com/How+dreaming+feels+like/vttzRig/",
            "https://bigmemes123.funnyjunk.com/hdgifs/How+dreaming+feels+like_247d10_11748871.mp4",
        ),
        (  # spaces in the video URL are replaced with '+'
            "https://funnyjunk.com/Unkempt+luckless+rapidfire/GivzRTv/",
            "https://loginportal123.funnyjunk.com/hdgifs/Unkempt+luckless+rapgym+boyzire_4c3d1f_11751038.mp4",
        ),
    ],
)
def test_get_video_url(url, expected):
    response = requests.get(url)
    response.raise_for_status()
    assert get_video_url(response.text) == expected, f"Expected {expected}, got {get_video_url(response.text)}"


def test_video_url_to_file():
    url = "https://bigmemes123.funnyjunk.com/hdgifs/How+dreaming+feels+like_247d10_11748871.mp4"
    file = video_url_to_file(url)
    assert file.filename == "How+dreaming+feels+like_247d10_11748871.mp4"
    assert file.spoiler is False
    assert isinstance(file.fp, io.BytesIO)
