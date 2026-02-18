from typing import List, Optional, Tuple
from urllib.parse import urlparse

import discord
import pyyoutube
import spotify
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions
from spotify import Client
from spotify.utils import to_id

YT_STRING = "https://www.youtube.com/watch?v="


def extract_spotify_track_id(url: str) -> Optional[str]:
    """Extract Spotify track ID from a URL using urlparse.

    Args:
        url: Spotify URL to parse

    Returns:
        Track ID if found, None otherwise
    """
    try:
        parsed = urlparse(url)
        if parsed.netloc not in ("open.spotify.com", "spotify.com"):
            return None

        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) >= 2 and path_parts[0] == "track":
            return path_parts[1]

        return None
    except Exception:
        return None


def find_spotify_track_urls(text: str) -> List[str]:
    """Find all Spotify track URLs in text.

    Args:
        text: Text to search for Spotify URLs

    Returns:
        List of Spotify track URLs found
    """
    words = text.split()
    track_urls = []

    for word in words:
        # Strip common surrounding punctuation and Discord angle brackets
        # Discord often formats URLs as <https://...>
        cleaned = word.strip('<>()[]{}.,;:!?"\'')

        # Check if this word looks like a URL (starts with http:// or https://)
        if cleaned.lower().startswith(("http://", "https://")):
            track_id = extract_spotify_track_id(cleaned)
            if track_id:
                # Reconstruct clean URL
                track_urls.append(f"https://open.spotify.com/track/{track_id}")

    return track_urls


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
        extra_str = (
            f"\n\nSee {self.help_link} for details on getting your API key(s)."
            if self.help_link
            else ""
        )
        return base_str + extra_str


class SpotifyKeyNotFoundError(APIKeyNotFoundError):
    def __init__(self, key):
        super().__init__(
            platform="spotify",
            key=key,
            help_link="https://developer.spotify.com/documentation/web-api/quick-start/",
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
        self.config = Config.get_conf(
            self, identifier=250390443
        )  # randomly generated identifier

        # Register channel-level settings for automatic link watching
        default_channel = {
            "autowatch": False,  # Whether to automatically watch for Spotify links
        }
        self.config.register_channel(**default_channel)

    @commands.hybrid_command(name="spotify")
    async def spotify(self, ctx: commands.Context, link: str):
        """Convert a Spotify track link to a YouTube video link.

        Example: https://open.spotify.com/track/65ShmiE5aLBdcIGr7tHX35?si=d2e8de8114f5422b
        """
        try:
            async with ctx.typing():
                links = await self._convert_spotify_to_youtube(link)
        except APIKeyNotFoundError as e:
            return await ctx.reply(e)
        except spotify.errors.HTTPException as e:
            return await ctx.reply(f"`{e}`")

        if not links:
            return await ctx.reply("No valid YouTube video links found.")
        return await menu(ctx=ctx, pages=links, controls=DEFAULT_CONTROLS)

    async def _convert_spotify_to_youtube(self, spotify_link: str) -> List[str]:
        """Convert a Spotify track link to YouTube video links.

        Args:
            spotify_link: Spotify track URL

        Returns:
            List of YouTube video URLs

        Raises:
            APIKeyNotFoundError: If Spotify or YouTube API keys are not set
            spotify.errors.HTTPException: If there's an error fetching from Spotify
        """
        async with Client(*await self._get_spotify_api_keys()) as spoticlient:
            track_id = to_id(value=spotify_link.split(sep="?si=")[0])
            track = await spoticlient.get_track(track_id)

            ytapi = pyyoutube.Api(api_key=await self._get_youtube_api_key())
            result: list = ytapi.search(
                search_type="video",
                q=f"{track.artist.name} - {track.name}",
                count=5,
                limit=5,
            ).items

        links = [YT_STRING + vid.id.videoId for vid in result if vid.id.videoId]
        return links

    @commands.group()
    async def spotset(self, ctx: commands.Context) -> None:
        """Settings for the Spotify to YouTube converter."""
        pass

    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @spotset.command(name="autowatch")
    async def set_autowatch(self, ctx: commands.Context) -> None:
        """Toggle automatic watching for Spotify links in this channel.

        When enabled, the bot will automatically reply to messages containing
        Spotify track links with the YouTube version of the song.
        """
        current_setting = await self.config.channel(ctx.channel).autowatch()
        msg = await ctx.reply(
            f"Current setting: automatic link watching is **{'enabled' if current_setting else 'disabled'}** in this channel.\n\n"
            "Should I automatically reply to Spotify links with YouTube versions in this channel? (react with ✅ or ❌)"
        )
        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        await ctx.bot.wait_for("reaction_add", check=pred)
        if pred.result is True:
            await self.config.channel(ctx.channel).autowatch.set(True)
            await ctx.send(
                "Setting updated: automatic link watching **enabled** for this channel."
            )
        else:
            await self.config.channel(ctx.channel).autowatch.set(False)
            await ctx.send(
                "Setting updated: automatic link watching **disabled** for this channel."
            )

    @commands.Cog.listener("on_message")
    async def _message_listener(self, message: discord.Message):
        """Listen for Spotify links in messages and automatically convert them."""
        # Ignore messages from bots
        if message.author.bot:
            return

        # Only process guild messages
        if not message.guild:
            return

        # Check if this message would trigger a command - if so, ignore it
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # Check if autowatch is enabled for this channel
        if not await self.config.channel(message.channel).autowatch():
            return

        # Search for Spotify track links in the message
        spotify_urls = find_spotify_track_urls(message.content)
        if not spotify_urls:
            return

        # Convert the first Spotify link found
        spotify_link = spotify_urls[0]

        try:
            async with message.channel.typing():
                links = await self._convert_spotify_to_youtube(spotify_link)
        except APIKeyNotFoundError:
            # Silently fail if API keys are not set
            return
        except spotify.errors.HTTPException:
            # Silently fail if there's an error fetching from Spotify
            return

        if links:
            # Reply with the first YouTube link
            await message.reply(
                f"🎵 Found on YouTube: {links[0]}", mention_author=False
            )

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
