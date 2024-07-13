from io import BytesIO

import requests
from bs4 import BeautifulSoup
from discord import File
from redbot.core import Config, app_commands, commands
from redbot.core.bot import Red


class IspyFJ(commands.Cog):
    """Extract the raw video content from a funnyjunk link."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @commands.hybrid_command(name="fj")
    async def convert(self, ctx: commands.Context, link: str):
        """Extract the raw video content from a funnyjunk link."""
        if not "funnyjunk.com" in link:
            return await ctx.reply("That's not a funnyjunk link.", ephemeral=True)
        try:
            # make the request with the fake user agent
            response = requests.get(link, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
        except requests.HTTPError:
            return await ctx.reply("Failed to fetch the page.", ephemeral=True)
        if not response.text:
            return await ctx.reply("Failed to fetch the page.", ephemeral=True)

        try:
            video_url = get_video_url(response.text)
        except VideoNotFoundError as e:
            replied = await ctx.react_quietly("❌")
            if not replied:
                return await ctx.reply(str(e), ephemeral=True)

        try:
            # try to remove the preview embed from the triggering message
            await ctx.message.edit(suppress=True)
        except:
            pass  # we probably don't have permission to edit the message

        try:
            # send the video file
            video_file = video_url_to_file(video_url)
            await ctx.reply(file=video_file)
            # close the file once we're done with it
            video_file.close()
        except requests.HTTPError:
            # just send the URL if we can't download the file
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


def video_url_to_file(url: str) -> File:
    """Turn a video URL into a discord.File object."""
    video_response = requests.get(url)
    video_response.raise_for_status()
    video_file = BytesIO(video_response.content)
    return File(video_file, filename=url.split("/")[-1])
