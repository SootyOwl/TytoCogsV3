from html2image import Html2Image
from x2image.x2image import get_twitter_embed, convert_html_to_image
import pytest


@pytest.mark.skip(reason="Skipped due to deprecated / disabled cog.")
@pytest.mark.asyncio
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
