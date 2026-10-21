import threading

import pytest
import requests
from html2image import Html2Image

from x2image.x2image import convert_html_to_image, get_twitter_embed


@pytest.mark.parametrize("status", [200, 503])
async def test_oembed_request_does_not_block_discord(status, mocker):
    loop_thread = threading.get_ident()
    response = requests.Response()
    response.status_code = status
    response._content = b'{"html": "<blockquote>Test tweet</blockquote>"}'

    def get(url):
        assert threading.get_ident() != loop_thread
        assert (
            url
            == "https://publish.twitter.com/oembed?url=https://x.com/example/status/1&theme=dark"
        )
        return response

    mocker.patch("x2image.x2image.requests.get", side_effect=get)
    if status == 200:
        assert await get_twitter_embed("https://x.com/example/status/1") == {
            "html": "<blockquote>Test tweet</blockquote>"
        }
    else:
        with pytest.raises(requests.HTTPError) as caught:
            await get_twitter_embed("https://x.com/example/status/1")
        assert caught.value.response is response


@pytest.mark.skip(reason="Skipped due to deprecated / disabled cog.")
@pytest.mark.asyncio
@pytest.mark.live
async def test_get_twitter_embed():
    link = "https://x.com/elonmusk/status/1812102074588426669"
    embed = await get_twitter_embed(link)
    assert embed["html"].startswith('<blockquote class="twitter-tweet">')
    assert embed["author_name"] == "Elon Musk"
    assert embed["author_url"] == "https://twitter.com/elonmusk"


@pytest.mark.xfail(
    run=False,
    reason="This test is expected to fail due to chrome's headless mode changes.",
)
@pytest.mark.asyncio
@pytest.mark.live
async def test_convert_html_to_image():
    hti = Html2Image(
        custom_flags=[
            "--virtual-time-budget=10000",
            "--hide-scrollbars",
            "--disable-gpu",
            "--no-sandbox",
        ]
    )
    link = "https://x.com/elonmusk/status/1812102074588426669"
    embed = await get_twitter_embed(link)
    image = await convert_html_to_image(hti, embed["html"])

    assert image.startswith(b"\x89PNG\r\n\x1a\n")  # PNG magic
