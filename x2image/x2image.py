import asyncio
import io

import requests
from discord import File
from html2image import Html2Image
from redbot.core import Config, commands, data_manager
from redbot.core.bot import Red
from wand.image import Image


class X2Image(commands.Cog):
    """Convert an X.com link to an image using html2image."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        # get the data folder for the cog
        path = data_manager.cog_data_path(self)
        self.hti = Html2Image(
            output_path=f"{path}/images/",  # where to save the images
            temp_path=f"{path}/tmp/",  # where to save temporary files
            custom_flags=[
                "--virtual-time-budget=2000",
                "--hide-scrollbars",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-software-rasterizer",
                "--headless",
            ],
        )

    @commands.hybrid_command(name="x2image", aliases=["xti"])
    async def convert(self, ctx: commands.Context, link: str, dark: bool = True, spoiler: bool = False):
        """Convert an X.com link to an image using html2image.

        `link`: The X.com link to convert.
        `dark`: Whether to use the dark theme for the tweet.
        `spoiler`: Whether to send the image as a spoiler.
        """
        await ctx.defer()  # defer the response to avoid the 3 second timeout for the interaction
        if not "x.com" in link and not "twitter.com" in link:
            return await ctx.reply("That's not an X.com link.", ephemeral=True)

        try:
            # get the embed HTML for the tweet
            embed = await get_twitter_embed(link, dark)
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
            content = f"[Original Tweet]({link})"
            await ctx.reply(
                content=content, file=File(image_file, filename="tweet.png", spoiler=spoiler), suppress_embeds=True
            )
            # close the file once we're done with it
            image_file.close()
        except Exception as e:
            return await ctx.reply(str(e), ephemeral=True)

    @commands.hybrid_command(name="fixup")
    async def fixup(self, ctx: commands.Context, link: str, spoiler: bool = False):
        """Convert an X.com link to a fixupx.com link.

        `link`: The X.com link to convert.
        `spoiler`: Whether to send the link as a spoiler.
        """
        if not "x.com" in link:
            return await ctx.reply("That's not an X.com link.", ephemeral=True)
        # replace x.com link with fixupx.com link
        link = link.replace("x.com", "fixupx.com")
        if spoiler:
            link = f"||{link}||"
        await ctx.reply(link)


async def get_twitter_embed(link: str, dark: bool = True) -> dict:
    """Get the Twitter embed for a tweet using the Twitter API."""
    embed_endpoint = f"https://publish.twitter.com/oembed?url={link}&theme={'dark' if dark else 'light'}"
    response = requests.get(embed_endpoint)
    response.raise_for_status()
    return response.json()


async def convert_html_to_image(hti: Html2Image, html: str) -> bytes:
    """Convert HTML to an image using html2image."""
    # convert the html to an image with an asyncio.to_thread, with a timeout
    res = await asyncio.wait_for(asyncio.to_thread(hti.screenshot, html), timeout=20)
    path = res[0]
    image = await trim_border(path)
    return image


async def trim_border(path: str):
    """Trim the border from an image using wand."""
    with Image(filename=path) as img:
        img.trim()
        out = img.make_blob()
    return out
