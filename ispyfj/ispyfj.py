from redbot.core import commands, Config
from redbot.core.bot import Red

import requests

class IspyFJ(commands.Cog):
    """Extract the raw video content from a funnyjunk link."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=250390444)  # randomly generated identifier

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
        video_url = get_video_url(response.text)
        await ctx.send(video_url)

def get_video_url(html: str) -> str:
    # find the video tag
    start = html.find('<video')
    if start == -1:
        return "No video found."
    end = html.find('</video>', start)
    if end == -1:
        return "No video found."
    video = html[start:end]
    # find the src= attribute
    start = video.find('src="')
    if start == -1:
        return "No video found."
    start += 5
    end = video.find('"', start)
    if end == -1:
        return "No video found."
    
    return video[start:end]