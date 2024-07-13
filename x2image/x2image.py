import io

import requests
from discord import File
from html2image import Html2Image
from redbot.core import Config, commands
from redbot.core.bot import Red
from wand.image import Image


class X2Image(commands.Cog):
    """Convert an X.com link to an image using html2image."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.hti = Html2Image(
            output_path="x2image/images/",  # where to save the images
            temp_path="x2image/tmp/",  # where to save temporary files
            custom_flags=["--virtual-time-budget=1000", "--hide-scrollbars"]
        )

    @commands.hybrid_command(name="x2image")
    async def convert(self, ctx: commands.Context, link: str):
        """Convert an X.com link to an image using html2image."""
        if not "x.com" in link:
            return await ctx.reply("That's not an X.com link.", ephemeral=True)

        try:
            # get the embed HTML for the tweet
            embed = await get_twitter_embed(link)
        except requests.HTTPError:
            return await ctx.reply("Failed to fetch the tweet.", ephemeral=True)

        try:
            # convert the HTML to an image
            image = await convert_html_to_image(self.hti, embed["html"])
        except Exception as e:
            return await ctx.reply(str(e), ephemeral=True)

        try:
            # make a file from the image bytes and send it
            image_file = io.BytesIO(image)
            await ctx.reply(file=File(image_file, filename="tweet.png"))
            # close the file once we're done with it
            image_file.close()
        except Exception as e:
            return await ctx.reply(str(e), ephemeral=True)


async def get_twitter_embed(link: str) -> dict:
    """Get the Twitter embed for a tweet using the Twitter API."""
    embed_endpoint = f"https://publish.twitter.com/oembed?url={link}"
    response = requests.get(embed_endpoint)
    response.raise_for_status()
    return response.json()


async def convert_html_to_image(hti: Html2Image, html: str) -> bytes:
    """Convert HTML to an image using html2image."""
    # convert the html to an image
    path = hti.screenshot(html_str=html)[0]
    image = await trim_border(path)
    return image


async def trim_border(path: str):
    """Trim the border from an image using wand."""
    with Image(filename=path) as img:
        img.trim()
        img.save(filename=path)
        out = img.make_blob()
    return out
