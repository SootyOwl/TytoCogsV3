"""Use `redvid` to embed Reddit videos in Discord messages."""

# create an enum for the error codes
import asyncio
import enum
import logging
import tempfile

import discord
from redbot.core import commands, data_manager
from redbot.core.bot import Red
from redvid import Downloader

logger = logging.getLogger("redvids")
logger.setLevel(logging.DEBUG)


class RedVidsError(enum.IntEnum):
    """0: Size exceeds maximum
    1: Duration exceeds maximum
    2: File exists
    """

    SIZE_EXCEEDS_MAXIMUM = 0
    DURATION_EXCEEDS_MAXIMUM = 1
    FILE_EXISTS = 2


class RedVids(commands.Cog):
    """Use `redvid` to embed Reddit videos in Discord messages."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.max_size = 7 * (1 << 20)  # 7 MiB
        """The maximum size of a video file to download."""
        self.data_path = data_manager.cog_data_path(self)

    @commands.hybrid_command(name="redvid")
    async def redvid(self, ctx: commands.Context, url: str):
        """Download and send a Reddit video."""
        if not check_url(url):
            return await ctx.reply("That's not a Reddit video URL.", ephemeral=True)

        logger.debug("Downloading video.")
        async with ctx.typing():
            with tempfile.TemporaryDirectory(dir=self.data_path) as tempdir:
                try:
                    video = await download_reddit_video(url, self.max_size, tempdir)
                except Exception:
                    logger.exception("Failed to download video.")
                    return await ctx.reply("Failed to download the video.", ephemeral=True)

                if isinstance(video, RedVidsError):
                    if video == RedVidsError.SIZE_EXCEEDS_MAXIMUM:
                        return await ctx.reply("The video is too large.", ephemeral=True)
                    elif video == RedVidsError.DURATION_EXCEEDS_MAXIMUM:
                        return await ctx.reply("The video is too long.", ephemeral=True)
                    elif video == RedVidsError.FILE_EXISTS:
                        return await ctx.reply("The video already exists.", ephemeral=True)
                if not video:
                    return await ctx.reply("Failed to download the video.", ephemeral=True)

                await ctx.reply(file=video_path_to_discord_file(video))
        logger.debug("Sent video file.")


async def download_reddit_video(url: str, max_size: int = 7 * (1 << 20), path: str = ".") -> RedVidsError | str:
    """Download a Reddit video."""
    downloader = Downloader(url, max_s=max_size, path=path, auto_max=True)
    # Run blocking operations in thread pool to avoid blocking the event loop
    await asyncio.to_thread(downloader.check)
    video = await asyncio.to_thread(downloader.download)
    return check_video_result(video)


def check_video_result(video: int | str) -> RedVidsError | str:
    """Handle the result of a video download."""
    if isinstance(video, int):
        return RedVidsError(video)
    return video


def video_path_to_discord_file(video_path: str) -> discord.File:
    """Convert a video file path to a Discord File."""
    return discord.File(video_path, filename=video_path.split("/")[-1])


def check_url(url: str) -> bool:
    """Check if the URL is a valid Reddit URL."""
    from urllib.parse import urlparse

    try:
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname
        # Allow "reddit.com" and subdomains like "www.reddit.com"
        return hostname == "reddit.com" or (hostname and hostname.endswith(".reddit.com"))
    except Exception:
        return False
