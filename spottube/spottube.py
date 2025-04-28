from typing import Optional, Tuple

import pyyoutube
import spotify
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
from spotify import Client
from spotify.utils import to_id

YT_STRING = "https://www.youtube.com/watch?v="


class APIKeyNotFoundError(KeyError):
    def __init__(self, platform: str, key: str, help_link: Optional[str] = None):
        self.platform = platform
        self.key = key
        self.help_link = help_link

    def __str__(self):
        base_str = (
            f"No {self.platform.capitalize()} API `{self.key.lower()}` set.\n"
            f"Set with `[p]set api {self.platform.lower()} {self.key.lower()},<{self.key.upper()}>`"
        )
        extra_str = f"\n\nSee {self.help_link} for details on getting your API key(s)." if self.help_link else ""
        return base_str + extra_str


class SpotifyKeyNotFoundError(APIKeyNotFoundError):
    def __init__(self, key):
        super().__init__(
            platform="spotify", key=key, help_link="https://developer.spotify.com/documentation/web-api/quick-start/"
        )


class YouTubeKeyNotFoundError(APIKeyNotFoundError):
    def __init__(self, key):
        super().__init__(
            platform="youtube",
            key=key,
            help_link="https://sns-sdks.lkhardy.cn/python-youtube/getting_started/#prerequisite",
        )


class SpotTube(commands.Cog):
    """Convert spotify links to YouTube links."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=250390443)  # randomly generated identifier

    @commands.command()
    async def convert(self, ctx: commands.Context, link: str):
        """Convert a Spotify track link to a YouTube video link.

        https://open.spotify.com/track/65ShmiE5aLBdcIGr7tHX35?si=d2e8de8114f5422b

        the part after track/ and before ?si is the id, I think
            in this case:
        """
        try:
            async with ctx.typing(), Client(*await self._get_spotify_api_keys()) as spoticlient:
                track_id = to_id(value=link.split(sep="?si=")[0])
                track = await spoticlient.get_track(track_id)

                ytapi = pyyoutube.Api(api_key=await self._get_youtube_api_key())
                result: list = ytapi.search(
                    search_type="video", q=f"{track.artist.name} - {track.name}", count=5, limit=5
                ).items
        except APIKeyNotFoundError as e:
            return await ctx.reply(e)
        except spotify.errors.HTTPException as e:
            return await ctx.reply(f"`{e}`")

        links = [YT_STRING + vid.id.videoId for vid in result if vid.id.videoId]
        if not links:
            return await ctx.reply("No valid YouTube video links found.")
        return await menu(ctx=ctx, pages=links, controls=DEFAULT_CONTROLS)

    async def _get_spotify_api_keys(self) -> Tuple[str, str]:
        spotify_api = await self.bot.get_shared_api_tokens("spotify")
        if not (client_id := spotify_api.get("client_id")):
            raise SpotifyKeyNotFoundError("client_id")
        elif not (client_secret := spotify_api.get("client_secret")):
            raise SpotifyKeyNotFoundError("client_secret")

        return client_id, client_secret

    async def _get_youtube_api_key(self) -> str:
        youtube_api = await self.bot.get_shared_api_tokens("youtube")
        if not (api_key := youtube_api.get("api_key")):
            raise YouTubeKeyNotFoundError("api_key")

        return api_key
