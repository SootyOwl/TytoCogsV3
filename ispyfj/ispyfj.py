from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red

import requests

from bs4 import BeautifulSoup


class IspyFJ(commands.Cog):
    """Extract the raw video content from a funnyjunk link."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @commands.hybrid_command(name="fj")
    async def convert(self, ctx: commands.Context, link: str):
        """Extract the raw video content from a funnyjunk link."""
        if not "funnyjunk.com" in link:
            return await ctx.reply("That's not a funnyjunk link.")
        try:
            # make the request with the fake user agent
            response = requests.get(link, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
        except requests.HTTPError:
            return await ctx.reply("Failed to fetch the page.")
        if not response.text:
            return await ctx.reply("Failed to fetch the page.")

        try:
            video_url = get_video_url(response.text)
        except VideoNotFoundError as e:
            return await ctx.react_quietly("❌", message=str(e))
        
        try:
            # try to remove the preview embed from the triggering message
            await ctx.message.edit(suppress=True)
        except:
            pass  # we probably don't have permission to edit the message

        await ctx.reply(video_url)


class VideoNotFoundError(Exception):
    pass

def get_video_url(html: str) -> str:
    """Look for video#content-video.hdgif video tag and extract the src= or data-original= attribute."""
    soup = BeautifulSoup(html, "html.parser")
    video_tag = soup.find("video", id="content-video")
    if not video_tag:
        video_tag = soup.find("video", class_="hdgif")
    if not video_tag:
        raise VideoNotFoundError("Could not find video tag. May be due to javascript loading (currently unfixable).")
    video_url = video_tag.get("src") or video_tag.get("data-original")
    if not video_url:
        raise VideoNotFoundError("Could not find video URL.")
    return video_url.replace(" ", "+")