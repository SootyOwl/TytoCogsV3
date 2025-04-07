"""Too Long; Didn't Watch (TLDW) - Summarize YouTube videos."""

import re
from typing import List
import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red

from anthropic import AsyncAnthropic as AsyncLLM
from anthropic.types.text_block import TextBlock

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from collections import OrderedDict

MAX_CACHE_SIZE = 100


class TLDWatch(commands.Cog):
    """Use Claude to create short summaries of youtube videos from their transcripts."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=84436212912371,  # Random identifier
            force_registration=True,
        )

        # Default settings
        default_global = {
            "api_key": None,
            "system_prompt": ("You are a YouTube video note taker and summarizer."),
            "https_proxy": None,
        }
        self.config.register_global(**default_global)
        self.llm_client = None
        self._summary_cache = OrderedDict()

        # context menu names must be between 1-32 characters
        self.youtube_summary_context_menu = app_commands.ContextMenu(
            callback=self.summarize_msg, name="Summarize YouTube (Public)"
        )
        self.bot.tree.add_command(self.youtube_summary_context_menu)
        # private mode is only visible to the user who created the context menu
        self.youtube_summary_context_menu_private = app_commands.ContextMenu(
            callback=self.summarize_msg_private, name="Summarize YouTube (Private)"
        )
        self.bot.tree.add_command(self.youtube_summary_context_menu_private)

    async def initialize(self) -> None:
        """Initialize the LLM client with the stored API key"""
        api_key = await self.config.api_key()
        if api_key:
            self.llm_client = AsyncLLM(api_key=api_key)

    async def cog_load(self) -> None:
        """Called when the cog is loaded"""
        await self.initialize()

    @commands.group()
    async def tldwset(self, ctx: commands.Context) -> None:
        """Settings for the video summarizer"""
        pass

    @commands.is_owner()
    @tldwset.command(name="apikey")
    async def set_api_key(self, ctx: commands.Context, api_key: str) -> None:
        """Set the LLM API key (admin only)

        Note: Use this command in DM to keep your API key private
        """
        # Delete the command message if it's not in DMs
        if ctx.guild is not None:
            try:
                await ctx.message.delete()
            except (discord.errors.Forbidden, discord.errors.NotFound):
                pass

            await ctx.send("Please use this command in DM to keep your API key private.")
            return
        await self.config.api_key.set(api_key)
        await self.initialize()
        await ctx.send("API key set successfully.")

    @commands.is_owner()
    @tldwset.command(name="prompt")
    async def set_prompt(self, ctx: commands.Context, *, prompt: str) -> None:
        """Set the system prompt for Claude (admin only)"""
        await self.config.system_prompt.set(prompt)
        await ctx.send("System prompt set successfully.")

    @commands.is_owner()
    @tldwset.command(name="proxy")
    async def set_proxy(self, ctx: commands.Context, https_proxy: str = None) -> None:
        """Set the https proxy (admin only). Can be used to bypass YT IP restrictions."""
        if https_proxy is None:
            await self.config.https_proxy.clear()
            await ctx.send("https proxy cleared successfully.")
            return
        await self.config.https_proxy.set(https_proxy)
        await ctx.send("https proxy set successfully.")

    @commands.hybrid_command(name="tldw")
    async def summarize(self, ctx: commands.Context, video_url: str) -> None:
        """Summarize a YouTube video using Claude"""
        if not self.llm_client:
            await ctx.send("API key is not set. Please set the API key first.")
            return

        async with ctx.typing():
            try:
                summary = await self.handlesummarize(video_url)
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
                return

        await ctx.reply(f"{summary}")

    async def summarize_msg(self, inter: discord.Interaction, message: discord.Message) -> None:
        """Summarize a YouTube video using Claude"""
        await inter.response.defer(thinking=True)
        try:
            summary = await self._process_video_message(message)
        except Exception as e:
            await inter.edit_original_response(content=str(e))
            return
        await inter.edit_original_response(content=summary)

    async def summarize_msg_private(self, inter: discord.Interaction, message: discord.Message) -> None:
        """Summarize a YouTube video using Claude"""
        await inter.response.defer(thinking=True, ephemeral=True)
        try:
            summary = await self._process_video_message(message)
        except Exception as e:
            await inter.edit_original_response(content=str(e))
            return
        await inter.edit_original_response(content=summary)

    async def _process_video_message(self, message: discord.Message) -> str:
        """Shared processing of a message to generate a YouTube video summary."""
        if not self.llm_client:
            raise ValueError("API key is not set. Please set the API key first.")
        if not message.content:
            raise ValueError("No content to summarize.")

        try:
            # Validate the video URL by attempting to extract the video id
            get_video_id(message.content)
        except ValueError as e:
            raise ValueError(f"An error occurred: {e}")

        try:
            summary = await self.handlesummarize(message.content)
        except Exception as e:
            raise Exception(f"An error occurred: {e}")

        return summary

    async def handlesummarize(self, video_url: str) -> str:
        """Handle the process of summarizing a YouTube video"""
        # get the video id from the video url using regex
        video_id = get_video_id(video_url)

        # return cached summary if available and mark it as recently used
        if video_id in self._summary_cache:
            self._summary_cache.move_to_end(video_id)
            return self._summary_cache[video_id]

        # get the transcript of the video using the video id
        # get the https proxy from the config if it's set
        https_proxy = await self.config.https_proxy()
        transcript = await get_transcript(video_id, https_proxy)

        # summarize the transcript using Claude
        summary = await self.generate_summary(transcript)
        summary = cleanup_summary(summary)

        # store the computed summary in the cache
        self._summary_cache[video_id] = summary

        # Ensure cache does not exceed the maximum size
        if len(self._summary_cache) > MAX_CACHE_SIZE:
            self._summary_cache.popitem(last=False)

        return summary

    async def generate_summary(self, text: str) -> str:
        """Generate a summary using Claude"""
        if not text:
            raise ValueError("No text to summarize.")

        response = await self.llm_client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=2048,
            temperature=0,
            system=await self.config.system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "text",
                            "text": "Summarise the key points in this video transcript in the form of markdown-formatted concise notes.",
                        },
                    ],
                },
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Here are the key points from the video transcript:\n\n```markdown",
                        }
                    ],
                },
            ],
        )

        return response.content

def cleanup_summary(summary: List[TextBlock]) -> str:
    """The summary should have a closing ```"""
    if not summary:
        raise ValueError("Failed to generate a summary.")

    # get the actual text from the response content
    output = summary[0].text

    # the closing ``` indicates the end of the summary, only keep everything before it
    output = output.split("```")[0]

    return output


async def get_transcript(video_id: str, https_proxy: str = None) -> str:
    """Get the transcript of a YouTube video."""
    # get the transcript of the video using the video id
    try:
        params = {"video_id": video_id, "languages": ("en", "en-US", "en-GB")}
        if https_proxy:
            params["proxies"] = {"https": https_proxy}
        transcript = YouTubeTranscriptApi.get_transcript(**params)
    except Exception as e:
        raise ValueError("Error getting transcript: " + str(e))

    # format the transcript as text
    return TextFormatter().format_transcript(transcript)


def get_video_id(video_url: str) -> str:
    """Extract the YouTube video ID from the URL"""
    # extract the YT video ID from the URL using regex
    # there may be gubbins after the video ID, so we need to be careful
    video_id = re.search(r"(?<=v=)[\w-]+|(?<=youtu\.be/)[\w-]+|(?<=shorts/)[\w-]+", video_url)
    if video_id:
        return video_id.group(0)
    else:
        raise ValueError("Invalid YouTube video URL")
