"""Too Long; Didn't Watch (TLDW) - Summarize YouTube videos."""

import re
from typing import List, Optional
import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red

from anthropic import AsyncAnthropic as AsyncLLM
from anthropic.types.text_block import TextBlock
from anthropic.types.content_block import ContentBlock

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
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
            "languages": ["en-US", "en-GB", "en"],
        }
        self.config.register_global(**default_global)

        self.llm_client: Optional[AsyncLLM] = None
        self._summary_cache = OrderedDict()
        self.ytt_api = YouTubeTranscriptApi()

        # context menu names must be between 1-32 characters
        self.youtube_summary_context_menu = app_commands.ContextMenu(
            callback=self.summarize_msg_callback, name="Summarize YouTube (Public)", extras={"is_private": False}
        )
        # private mode is only visible to the user who created the context menu using ephemeral=True
        self.youtube_summary_context_menu_private = app_commands.ContextMenu(
            callback=self.summarize_msg_callback, name="Summarize YouTube (Private)", extras={"is_private": True}
        )
        self.bot.tree.add_command(self.youtube_summary_context_menu)
        self.bot.tree.add_command(self.youtube_summary_context_menu_private)

    async def initialize(self) -> None:
        """Initialize the LLM client with the stored API key,
        and the youtube transcript API with the stored proxy."""
        api_key = await self.config.api_key()
        if api_key:
            self.llm_client = AsyncLLM(api_key=api_key)

        # currently no support for the WebShareProxyConfig
        https_proxy = await self.config.https_proxy()
        proxy_config = GenericProxyConfig(https_url=https_proxy) if https_proxy else None
        self.ytt_api = YouTubeTranscriptApi(
            proxy_config=proxy_config,
        )

    async def cog_load(self) -> None:
        """Called when the cog is loaded"""
        await self.initialize()

    @commands.group()
    async def tldwset(self, ctx: commands.Context) -> None:
        """Settings for the video summarizer"""
        pass

    @commands.is_owner()
    @commands.dm_only()
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
    async def set_proxy(self, ctx: commands.Context, https_proxy: Optional[str] = None) -> None:
        """Set the https proxy (admin only). Can be used to bypass YT IP restrictions."""
        if https_proxy is None:
            await self.config.https_proxy.clear()
            await ctx.send("https proxy cleared successfully.")
            return
        await self.config.https_proxy.set(https_proxy)

        await ctx.send("https proxy set successfully.")

    @tldwset.group(name="languages", invoke_without_command=True)
    async def languages(self, ctx: commands.Context) -> None:
        """Set the languages for the transcript API"""
        await ctx.send_help()

    @commands.admin()
    @languages.command(name="add")
    async def add_language(self, ctx: commands.Context, language: str) -> None:
        """Add a language to the list of languages for the transcript API"""
        async with self.config.languages() as languages:
            if language not in languages:
                languages.append(language)
                await ctx.send(f"Language '{language}' added successfully.")
            else:
                await ctx.send(f"Language '{language}' is already in the list.")

    @commands.admin()
    @languages.command(name="remove")
    async def remove_language(self, ctx: commands.Context, language: str) -> None:
        """Remove a language from the list of languages for the transcript API"""
        async with self.config.languages() as languages:
            if language in languages:
                languages.remove(language)
                await ctx.send(f"Language '{language}' removed successfully.")
            else:
                await ctx.send(f"Language '{language}' is not in the list.")

    @commands.admin()
    @languages.command(name="list")
    async def list_languages(self, ctx: commands.Context) -> None:
        """List the languages for the transcript API"""
        languages = await self.config.languages()
        if languages:
            await ctx.send(f"Languages: {', '.join(languages)}")
        else:
            await ctx.send("No languages set.")

    @commands.admin()
    @languages.command(name="clear")
    async def clear_languages(self, ctx: commands.Context) -> None:
        """Clear the list of languages for the transcript API"""
        await self.config.languages.clear()
        await ctx.send("Languages cleared successfully.")

    # allow reordering (reprioritising) of the languages
    @commands.admin()
    @languages.command(name="reorder")
    async def reorder_languages(self, ctx: commands.Context, *languages: str) -> None:
        """Reorder the languages for the transcript API.
        
        The order of the languages will be set to the order provided.
        Any languages not provided will be appended to the end of the list.

        Example: 
            When the current languages are ['en-US', 'en-GB', 'en']
            and the command is called with ['en-GB', 'en-US']
            the new order will be ['en-GB', 'en-US', 'en']
        """
        async with self.config.languages() as lang_list:
            # check if all languages are in the list
            for lang in languages:
                if lang not in lang_list:
                    await ctx.send(f"Language '{lang}' is not in the list. Please add it first.")
                    return
            # reorder the list
            reordered_list = [lang for lang in languages if lang in lang_list]
            remaining_languages = [lang for lang in lang_list if lang not in reordered_list]
            lang_list[:] = reordered_list + remaining_languages
            await ctx.send(f"Languages reordered successfully to: {', '.join(lang_list)}")

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
                raise  # so we can get traceback in the bot

        await ctx.reply(f"{summary}")

    async def summarize_msg_callback(self, inter: discord.Interaction, message: discord.Message) -> None:
        """Summarize a YouTube video using Claude"""
        is_private = inter.extras.get("is_private", False)
        await inter.response.defer(thinking=True, ephemeral=is_private)
        try:
            summary = await self._process_video_message(message)
        except Exception as e:
            await inter.edit_original_response(content=str(e))
            raise  # so we can get traceback in the bot
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
        transcript = await get_transcript(self.ytt_api, video_id, languages=await self.config.languages())

        # summarize the transcript using Claude
        summary = await self.generate_summary(transcript)
        if not summary:
            raise ValueError("Failed to generate a summary.")
        # cleanup the summary
        summary = cleanup_summary(summary)

        # store the computed summary in the cache
        self._summary_cache[video_id] = summary

        # Ensure cache does not exceed the maximum size
        if len(self._summary_cache) > MAX_CACHE_SIZE:
            self._summary_cache.popitem(last=False)

        return summary

    async def generate_summary(self, text: str) -> List[ContentBlock]:
        """Generate a summary using Claude"""
        if not self.llm_client:
            raise ValueError("API key is not set. Please set the API key first.")
        if not self.llm_client.api_key:
            raise ValueError("API key is not set. Please set the API key first.")
        if not text:
            raise ValueError("No text to summarize.")
        system_prompt = await self.config.system_prompt()

        return await get_llm_response(self.llm_client, text, system_prompt)


def cleanup_summary(summary: List[ContentBlock]) -> str:
    """The summary should have a closing ```"""
    if not summary:
        raise ValueError("Failed to generate a summary, no content found.")
    # ensure it's a text block and not a tool use block
    if not isinstance(summary[0], TextBlock):
        raise ValueError("Failed to generate a summary, expected a text block but got %s", type(summary[0]))

    # get the actual text from the response content
    output = summary[0].text

    # the closing ``` indicates the end of the summary, only keep everything before it
    output = output.split("```")[0]
    # remove any leading or trailing whitespace
    output = output.strip()
    # remove any leading or trailing newlines
    output = output.strip("\n")

    return output


async def get_transcript(ytt_api: YouTubeTranscriptApi, video_id: str, languages: list[str] = ["en-US", "en-GB", "en"]) -> str:
    """Get the transcript of a YouTube video."""
    # get the transcript of the video using the video id
    try:
        transcript = ytt_api.fetch(video_id=video_id, languages=languages)
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


async def get_llm_response(llm_client: AsyncLLM, text: str, system_prompt: str) -> List[ContentBlock]:
    response = await llm_client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=2048,
        temperature=0,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "text",
                        "text": "Summarise the key points in this video transcript in the form of markdown-formatted concise notes, in the language of the transcript.",
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
