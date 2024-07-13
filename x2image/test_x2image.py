from html2image import Html2Image
from x2image.x2image import get_twitter_embed, convert_html_to_image


def test_get_twitter_embed():
    link = "https://x.com/elonmusk/status/1812102074588426669"
    embed = get_twitter_embed(link)
    assert embed['html'].startswith('<blockquote class="twitter-tweet">')
    assert embed['author_name'] == "Elon Musk"
    assert embed['author_url'] == "https://twitter.com/elonmusk"


def test_convert_html_to_image():
    hti = Html2Image(custom_flags=["--virtual-time-budget=1000", "--hide-scrollbars"])
    link = "https://x.com/elonmusk/status/1812102074588426669"
    embed = get_twitter_embed(link)
    image = convert_html_to_image(hti, embed['html'], width=embed['width'])

    assert image.startswith(b"\x89PNG\r\n\x1a\n")  # PNG magic
