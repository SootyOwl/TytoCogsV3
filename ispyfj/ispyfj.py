from redbot.core import commands, Config
from redbot.core.bot import Red

import requests

class IspyFJ(commands.Cog):
    """Extract the raw video content from a funnyjunk link."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=250390443)  # randomly generated identifier

    @commands.command(name="fj")
    async def convert(self, ctx: commands.Context, link: str):
        """Extract the raw video content from a funnyjunk link."""
        if not "funnyjunk.com" in link:
            return await ctx.send("That's not a funnyjunk link.")
        try:
            response = requests.get(link)
            response.raise_for_status()
        except requests.HTTPError:
            return await ctx.send("Failed to fetch the page.")
        if not response.text:
            return await ctx.send("Failed to fetch the page.")

        # the video is contained within the HTML of the page
        #<video class="hdgif lzloaded" style="height: 558px; width: 460px; background: rgb(57, 57, 57); min-height: initial;" preload="none" id="content-video" autoplay="" loop="" muted="" data-original="https://bigmemes123.funnyjunk.com/hdgifs/How+dreaming+feels+like_247d10_11748871.mp4" src="https://bigmemes123.funnyjunk.com/hdgifs/How+dreaming+feels+like_247d10_11748871.mp4"></video>
        video_url = response.text.split('data-original="')[1].split('"')[0]
        await ctx.send(video_url)