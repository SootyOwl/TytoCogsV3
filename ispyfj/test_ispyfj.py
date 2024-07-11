from ispyfj.ispyfj import get_video_url
import pytest
import requests

def test_get_video_url():
    url = "https://funnyjunk.com/How+dreaming+feels+like/vttzRig/"
    response = requests.get(url)
    response.raise_for_status()
    assert get_video_url(response.text) == "https://bigmemes123.funnyjunk.com/hdgifs/How+dreaming+feels+like_247d10_11748871.mp4"