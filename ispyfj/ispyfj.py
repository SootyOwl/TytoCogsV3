import asyncio
import json
import logging
import re
import socket
import time
from functools import wraps
from io import BytesIO
from typing import Any, Callable, Dict, Optional

import aiohttp
from bs4 import BeautifulSoup
from discord import File
from redbot.core import Config, commands
from redbot.core.bot import Red
from yarl import URL

logger = logging.getLogger("red.ispyfj")


def exponential_backoff_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exponential_base: float = 2.0,
    max_delay: float = 60.0,
    retry_on_exceptions: tuple = (aiohttp.ClientError,),
    retry_condition: Optional[Callable[[Any], bool]] = None,
):
    """
    Exponential backoff retry decorator for async functions.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        exponential_base: Base for exponential backoff calculation
        max_delay: Maximum delay between retries
        retry_on_exceptions: Tuple of exceptions that should trigger a retry
        retry_condition: Optional function to determine if result should trigger retry
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    result = await func(*args, **kwargs)

                    # Check if we should retry based on the result
                    if (
                        retry_condition
                        and retry_condition(result)
                        and attempt < max_retries
                    ):
                        delay = min(base_delay * (exponential_base**attempt), max_delay)
                        logger.warning(
                            f"Retry condition met for {func.__name__}, attempt {attempt + 1}/{max_retries + 1}. "
                            f"Waiting {delay:.1f}s before retry..."
                        )
                        await asyncio.sleep(delay)
                        continue

                    return result

                except retry_on_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (exponential_base**attempt), max_delay)
                        logger.warning(
                            f"Exception {type(e).__name__} in {func.__name__}, attempt {attempt + 1}/{max_retries + 1}. "
                            f"Waiting {delay:.1f}s before retry..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        # Last attempt failed, re-raise the exception
                        raise e

            # This should not be reached, but just in case
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def _should_retry_login(response_data: dict) -> bool:
    """Check if login response indicates rate limiting."""
    if not isinstance(response_data, dict):
        return False
    return (
        not response_data.get("success", False)
        and "wait" in response_data.get("message", "").lower()
    )


class IspyFJ(commands.Cog):
    """Extract the raw video content from a funnyjunk link."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=12345678)
        self.config.register_global(
            # Cache duration in seconds
            cache_duration=3600,
            # User agent for requests
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            # Request timeout in seconds
            request_timeout=30,
            # Debug mode for extra logging
            debug_mode=False,
            # credentials (we hope there is never a captcha)
            username=None,
            password=None,
        )
        self.cache = {}  # Simple in-memory cache: {url: (timestamp, video_url)}
        conn = aiohttp.TCPConnector(
            family=socket.AF_INET,
            ssl=False,
        )
        self.session = aiohttp.ClientSession(connector=conn)

    async def cog_load(self) -> None:
        """Load the cog."""
        # Set up the aiohttp session with the user agent
        await self.set_user_agent()
        # Load the username and password from the config
        username, password = await self.get_credentials()
        # If username and password are set, login to FunnyJunk
        if username and password:
            await self.login_to_funnyjunk(
                username=username, password=password, remember=True
            )
        else:
            logger.info("No username/password set, skipping login to FunnyJunk.")

    async def get_credentials(self):
        username = await self.config.username()
        password = await self.config.password()
        return username, password

    async def set_user_agent(self):
        user_agent = await self.config.user_agent()
        self.session.headers.update({"User-Agent": user_agent})

    async def _perform_login_request(self, **credentials) -> dict:
        """Perform the actual login request and return parsed response data."""
        # Clear any existing cookies to ensure clean login
        self.session.cookie_jar.clear()

        # Attempt to login to FunnyJunk
        response = await self.session.post(
            "https://funnyjunk.com/members/ajaxlogin",
            data=credentials,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        response_text = await response.text()
        logger.debug(f"Login response status: {response.status}")
        logger.debug(f"Login response text: {response_text}")
        logger.debug(f"Login response cookies: {dict(response.cookies)}")

        if response.status != 200:
            raise aiohttp.ClientError(f"HTTP {response.status}: {response_text}")

        # Parse the response
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError:
            # If it's not JSON, assume success for backward compatibility
            response_data = {"success": True}

        return response_data

    @exponential_backoff_retry(
        max_retries=3,
        base_delay=1.0,
        exponential_base=2.0,
        retry_condition=_should_retry_login,
        retry_on_exceptions=(aiohttp.ClientError,),
    )
    async def login_to_funnyjunk(self, **credentials):
        """Login to FunnyJunk with automatic retry on rate limiting."""
        response_data = await self._perform_login_request(**credentials)

        if not response_data.get("success", False):
            message = response_data.get("message", "Unknown error")
            logger.error(f"Login failed: {message}")
            # Return the response data so retry_condition can check it
            return response_data

        # Login successful - check if we have the expected cookies
        cookies = self.session.cookie_jar.filter_cookies(URL("https://funnyjunk.com"))
        if cookies.get("fjsession"):
            logger.info("Logged in to FunnyJunk successfully.")
        else:
            logger.error("Login appeared successful but no fjsession cookie was set.")

        return response_data

    async def cog_unload(self) -> None:
        """Unload the cog."""
        await self.session.close()

    @commands.hybrid_command(name="fj")
    async def convert(self, ctx: commands.Context, link: str):
        """Extract the raw video content from a funnyjunk link."""
        if "funnyjunk.com" not in link:
            return await ctx.reply("That's not a funnyjunk link.", ephemeral=True)

        # Show typing indicator to indicate processing
        async with ctx.typing():
            try:
                # Try to get video URL
                video_url = await self.get_video_url(link)
                if not video_url:
                    return await ctx.reply(
                        "Failed to extract video URL.", ephemeral=True
                    )

                # Try to remove the preview embed from the triggering message
                try:
                    await ctx.message.edit(suppress=True)
                except Exception as e:
                    logger.debug(f"Failed to suppress embed: {e}")

                # Send the video
                try:
                    video_file = None
                    video_file = await self.video_url_to_file(video_url)
                    await ctx.reply(file=video_file)
                except Exception as e:
                    logger.exception(f"Failed to send video file: {e}")
                    # Just send the URL if we can't download the file
                    await ctx.reply(f"{video_url}")
                finally:
                    # Ensure the file is closed
                    if video_file and hasattr(video_file, "close"):
                        try:
                            video_file.close()
                        except Exception as e:
                            logger.debug(f"Failed to close video file: {e}")
                            pass

            except VideoNotFoundError as e:
                # Handle video not found error
                logger.error(f"Video not found: {e}")
                replied = await ctx.react_quietly("❌")
                if not replied:
                    await ctx.reply(f"Error: {str(e)}", ephemeral=True)

            except Exception as e:
                # Handle general errors
                logger.error(f"Error processing FunnyJunk link: {e}", exc_info=True)
                await ctx.reply(f"An error occurred: {str(e)}", ephemeral=True)

    async def get_video_url(self, link: str) -> str:
        """Get the video URL from a FunnyJunk link, with caching."""
        # Check cache first
        current_time = time.time()
        cache_duration = await self.config.cache_duration()

        if link in self.cache:
            timestamp, video_url = self.cache[link]
            if current_time - timestamp < cache_duration:
                logger.debug(f"Cache hit for {link}")
                return video_url

        # Cache miss or expired, fetch the URL
        settings = await self.get_settings()
        debug_mode = settings["debug_mode"]

        try:
            for attempt in range(3):
                response, response_text = await self.fetch_video_page(link, settings)
                if not response_text:
                    raise VideoNotFoundError("Empty response from server.")
                if debug_mode:
                    logger.debug(f"Response status: {response.status}")
                    logger.debug(f"Response length: {len(response_text)} characters")
                # Extract the video URL using multiple methods
                video_url = self._find_video_url(response_text)
                if not video_url:
                    raise VideoNotFoundError(
                        "Could not find video URL in the page HTML."
                    )
                if video_url.strip() == link.strip():
                    u, p = await self.get_credentials()
                    await self.login_to_funnyjunk(username=u, password=p, remember=True)
                    # retry the request
                    continue
                break
            else:
                raise VideoNotFoundError(
                    "Failed to extract video URL after multiple attempts."
                )
            # If the video url has 'user_uploaded_content', replace that with 'loginportal123' - this fixes an issue with discord embedding
            video_url = video_url.replace("user_uploaded_content", "loginportal123")
            # Cache the result
            self.cache[link] = (current_time, video_url)
            return video_url
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching FunnyJunk link: {e}")
            raise VideoNotFoundError("Failed to fetch the page.")

    async def fetch_video_page(self, link, settings):
        response = await self.session.get(
            link,
            headers={"User-Agent": settings["user_agent"]},
            timeout=settings["request_timeout"],
        )
        response_text = await response.text()
        # check if response is empty or contains "Login"
        return response, response_text

    def _find_video_url(self, html: str) -> Optional[str]:
        """Find video URL using multiple strategies."""
        # Try different extraction methods in order of reliability
        video_url = None

        # Try extraction methods one by one
        extraction_methods = [
            self._extract_from_video_tag,
            self._extract_from_anchor,
            self._extract_from_content_div,
            self._extract_from_json_ld,
            self._extract_from_scripts,
            self._extract_from_meta,
        ]

        for method in extraction_methods:
            try:
                video_url = method(html)
                if video_url:
                    # Clean and validate the URL
                    video_url = video_url.replace(" ", "+")
                    if not video_url.startswith("http"):
                        # Handle relative URLs
                        video_url = (
                            "https:" + video_url
                            if video_url.startswith("//")
                            else "https://funnyjunk.com" + video_url
                        )
                    return video_url
            except Exception as e:
                logger.debug(f"Error in extraction method {method.__name__}: {e}")
                continue

        return None

    def _extract_from_video_tag(self, html: str) -> Optional[str]:
        """Extract video URL from <video> tags."""
        soup = BeautifulSoup(html, "html.parser")

        # Try to find the video tag with different selectors
        selectors = [
            {"id": "content-video"},
            {"class_": "hdgif"},
            {"src": True},
            {"data-original": True},
        ]

        for selector in selectors:
            video_tag = soup.find("video", **selector)
            if video_tag:
                # Try src attribute first
                video_url = video_tag.get("src")
                if not video_url:
                    # Try data-original attribute
                    video_url = video_tag.get("data-original")

                # If still no URL, check for source tags
                if not video_url and video_tag.find("source"):
                    source_tag = video_tag.find("source")
                    video_url = source_tag.get("src")

                if video_url:
                    return video_url

        return None

    def _extract_from_anchor(self, html: str) -> Optional[str]:
        """Extract video URL from anchor tags with data-cachedvideosrc."""
        soup = BeautifulSoup(html, "html.parser")

        # Look for anchor with data-cachedvideosrc (common pattern)
        video_anchor = soup.find("a", class_="cnt-video-cont")
        if video_anchor and video_anchor.has_attr("data-cachedvideosrc"):
            return video_anchor["data-cachedvideosrc"]

        # Look for any anchor with data-cachedvideosrc
        video_anchor = soup.find("a", attrs={"data-cachedvideosrc": True})
        if video_anchor:
            return video_anchor["data-cachedvideosrc"]

        return None

    def _extract_from_content_div(self, html: str) -> Optional[str]:
        """Extract video URL from content divs and containers."""
        soup = BeautifulSoup(html, "html.parser")

        # Check for contentContainer videoEle
        content_container = soup.find("div", class_="contentContainer videoEle")
        if content_container:
            # Look for anchor within this container
            anchor = content_container.find("a", attrs={"data-cachedvideosrc": True})
            if anchor:
                return anchor["data-cachedvideosrc"]

            # Look for video tag within this container
            video = content_container.find("video")
            if video:
                return video.get("src") or video.get("data-original")

        # Check for cImg container
        content_div = soup.find("div", class_="cImg")
        if content_div:
            # Look for anchor within this container
            anchor = content_div.find("a", attrs={"data-cachedvideosrc": True})
            if anchor:
                return anchor["data-cachedvideosrc"]

        # Check for flashmovie container
        flash_div = soup.find("div", class_="flashmovie")
        if flash_div:
            anchor = flash_div.find("a", attrs={"data-cachedvideosrc": True})
            if anchor:
                return anchor["data-cachedvideosrc"]

        return None

    def _extract_from_json_ld(self, html: str) -> Optional[str]:
        """Extract video URL from JSON-LD data in scripts."""
        soup = BeautifulSoup(html, "html.parser")

        # Look for application/ld+json scripts
        ld_json_scripts = soup.find_all("script", type="application/ld+json")
        for script in ld_json_scripts:
            if not script.string:
                continue

            try:
                # Parse the JSON data
                json_data = json.loads(script.string)

                # Handle different JSON-LD structures
                if isinstance(json_data, dict):
                    # Case 1: Direct VideoObject
                    if (
                        json_data.get("@type") == "VideoObject"
                        and "contentUrl" in json_data
                    ):
                        return json_data["contentUrl"]

                    # Case 2: Nested VideoObject
                    if "@graph" in json_data:
                        for item in json_data["@graph"]:
                            if (
                                item.get("@type") == "VideoObject"
                                and "contentUrl" in item
                            ):
                                return item["contentUrl"]

            except (json.JSONDecodeError, TypeError, AttributeError) as e:
                logger.debug(f"Error parsing JSON-LD: {e}")
                continue

        return None

    def _extract_from_scripts(self, html: str) -> Optional[str]:
        """Extract video URL from script contents using regex."""
        soup = BeautifulSoup(html, "html.parser")

        # Get all script tags
        scripts = soup.find_all("script")

        for script in scripts:
            if not script.string:
                continue

            script_text = str(script.string)

            # Pattern 1: Look for direct MP4/WebM URLs
            video_matches = re.findall(r'(https?://[^"\']+\.(mp4|webm))', script_text)
            if video_matches:
                return video_matches[0][0]

            # Pattern 2: Look for data-cachedvideosrc attributes
            cached_matches = re.findall(
                r'data-cachedvideosrc=["\']([^"\']+)["\']', script_text
            )
            if cached_matches:
                return cached_matches[0]

            # Pattern 3: Look for videoSrc or videoUrl variables
            variable_matches = re.findall(
                r'(videoUrl|videoSrc)\s*=\s*[\'"]([^"\']+\.(?:mp4|webm))[\'"]',
                script_text,
            )
            if variable_matches:
                return variable_matches[0][1]

        return None

    def _extract_from_meta(self, html: str) -> Optional[str]:
        """Extract video URL from meta tags."""
        soup = BeautifulSoup(html, "html.parser")

        # Look for og:video meta tag
        og_video = soup.find("meta", property="og:video")
        if og_video and og_video.has_attr("content"):
            return og_video["content"]

        # Look for og:video:url meta tag
        og_video_url = soup.find("meta", property="og:video:url")
        if og_video_url and og_video_url.has_attr("content"):
            return og_video_url["content"]

        # Look for twitter:player:stream meta tag
        twitter_video = soup.find("meta", attrs={"name": "twitter:player:stream"})
        if twitter_video and twitter_video.has_attr("content"):
            return twitter_video["content"]

        return None

    async def video_url_to_file(self, url: str) -> File:
        """Turn a video URL into a discord.File object with proper resource handling."""
        settings = await self.get_settings()

        # Download the video with proper timeout and chunk handling
        async with self.session.get(
            url,
            timeout=settings["request_timeout"],
            headers={"User-Agent": settings["user_agent"]},
            allow_redirects=True,
        ) as video_response:
            video_response.raise_for_status()
            # check the size of the file
            if video_response.content_length is not None:
                if (
                    video_response.content_length > 25 * 1024 * 1024
                ):  # 25 MB limit on discord
                    # we should send the url instead, so raise an exception
                    raise VideoTooLargeError("Video too large to send directly.")

            # Create a BytesIO object to hold the video in memory
            video_file = BytesIO()
            async for chunk in video_response.content.iter_chunked(1024):
                video_file.write(chunk)

        # Reset the position to the beginning of the file
        video_file.seek(0)
        # Extract filename from URL
        filename = url.split("/")[-1]
        # Create and return the file
        return File(video_file, filename=filename)

    async def get_settings(self) -> Dict:
        """Get the current settings."""
        return {
            "user_agent": await self.config.user_agent(),
            "request_timeout": await self.config.request_timeout(),
            "cache_duration": await self.config.cache_duration(),
            "debug_mode": await self.config.debug_mode(),
            "username": await self.config.username(),
            "password?": True if await self.config.password() else False,
        }

    @commands.group(name="fjset")
    @commands.is_owner()
    async def fjset(self, ctx: commands.Context):
        """Configure the FunnyJunk converter."""
        if ctx.invoked_subcommand is None:
            settings = await self.get_settings()
            settings_str = "\n".join([f"{k}: {v}" for k, v in settings.items()])
            await ctx.send(f"Current settings:\n```\n{settings_str}\n```")

    @fjset.command(name="credentials")
    async def set_credentials(
        self, ctx: commands.Context, username: str, password: str
    ):
        """Set your FunnyJunk credentials."""
        # delete the ctx message immediately
        try:
            await ctx.message.delete()
        except Exception as e:
            logger.debug(f"Failed to delete message: {e}")
        # Set the credentials in the config
        await self.config.username.set(username)
        await self.config.password.set(password)
        await ctx.send("Credentials set.")
        await self.login_to_funnyjunk(
            username=username, password=password, remember=True
        )

    @fjset.command(name="useragent")
    async def set_useragent(self, ctx: commands.Context, *, user_agent: str):
        """Set the User-Agent header for requests."""
        await self.config.user_agent.set(user_agent)
        await ctx.send(f"User-Agent set to: {user_agent}")

    @fjset.command(name="timeout")
    async def set_timeout(self, ctx: commands.Context, seconds: int):
        """Set the timeout for requests in seconds."""
        await self.config.request_timeout.set(seconds)
        await ctx.send(f"Request timeout set to {seconds} seconds.")

    @fjset.command(name="cache")
    async def set_cache(self, ctx: commands.Context, seconds: int):
        """Set the cache duration in seconds."""
        await self.config.cache_duration.set(seconds)
        await ctx.send(f"Cache duration set to {seconds} seconds.")

    @fjset.command(name="debug")
    async def toggle_debug(self, ctx: commands.Context, enabled: bool):
        """Enable or disable debug mode for extra logging."""
        await self.config.debug_mode.set(enabled)
        await ctx.send(f"Debug mode {'enabled' if enabled else 'disabled'}.")

    @fjset.command(name="clearcache")
    async def clear_cache(self, ctx: commands.Context):
        """Clear the URL cache."""
        self.cache = {}
        await ctx.send("Cache cleared.")


class VideoNotFoundError(Exception):
    """Exception raised when a video cannot be found on the page."""

    pass


class VideoTooLargeError(Exception):
    """Exception raised when the video is too large to send."""

    pass
