"""Too Long; Didn't Watch (TLDW) - Summarize YouTube videos."""

import logging
import re
import typing as t
from collections import OrderedDict

import aiohttp
import discord
from discord import ButtonStyle
from openai import AsyncOpenAI as AsyncLLM
from redbot.core import Config, app_commands, commands
from redbot.core.bot import Red
from redbot.core.utils.views import ConfirmView, SetApiView
from yt_transcript_fetcher import (
    NoTranscriptError,
    VideoNotFoundError,
    YouTubeTranscriptFetcher,
)

MAX_CACHE_SIZE = 100


class TLDWatch(commands.Cog):
    """Use a LLM from OpenRouter to create short summaries of youtube videos from their transcripts."""

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
            "model": "openrouter/auto",
            "other_models": [],
            "system_prompt": ("You are a YouTube video note taker and summarizer."),
            "languages": ["en-US", "en-GB", "en"],
            "migration_notified": False,  # Track if user has been notified about OpenRouter migration
        }
        self.config.register_global(**default_global)

        self.llm_client: t.Optional[AsyncLLM] = None
        self._summary_cache = OrderedDict()
        self.yt_transcript_fetcher = YouTubeTranscriptFetcher()

        # context menu names must be between 1-32 characters
        self.youtube_summary_context_menu = app_commands.ContextMenu(
            callback=self.summarize_msg_callback,
            name="Summarize YouTube (Public)",
            extras={"is_private": False},
        )
        # private mode is only visible to the user who created the context menu using ephemeral=True
        self.youtube_summary_context_menu_private = app_commands.ContextMenu(
            callback=self.summarize_msg_callback,
            name="Summarize YouTube (Private)",
            extras={"is_private": True},
        )
        self.bot.tree.add_command(self.youtube_summary_context_menu)
        self.bot.tree.add_command(self.youtube_summary_context_menu_private)

    async def initialize(self) -> None:
        """Initialize the LLM client with the stored API key."""
        openrouter_keys = await self.bot.get_shared_api_tokens("openrouter")
        if api_key := openrouter_keys.get("api_key"):
            self.llm_client = AsyncLLM(
                api_key=api_key, base_url="https://openrouter.ai/api/v1"
            )

    @commands.Cog.listener()
    async def on_red_api_tokens_update(
        self, service_name: str, api_tokens: t.Dict[str, str]
    ) -> None:
        """Update the LLM client when the API tokens are updated."""
        if service_name != "openrouter":
            return

        if "api_key" in api_tokens:
            await self.initialize()

    async def _check_migration_notification(self) -> None:
        """Check if we need to show the OpenRouter migration notification."""
        # Only check if we haven't already notified the user
        if await self.config.migration_notified():
            return

        # Check if there's an API key set but the user hasn't been notified about the migration
        api_key2 = await self.config.api_key()
        if api_key2:
            # Send migration notification to bot owner
            await self._send_migration_notification()
            # User has an API key set, mark as notified so we don't show this again
            await self.config.migration_notified.set(True)

    async def _send_migration_notification(self) -> None:
        """Send a migration notification to the bot owner."""
        try:
            app_info = await self.bot.application_info()
            if app_info.owner:
                prefix = (await self.bot.get_valid_prefixes())[0]
                embed = discord.Embed(
                    title="🔄 TLDW Cog Migration Notice",
                    description="The TLDW cog has been updated to use OpenRouter instead of Anthropic Claude.",
                    color=0x00FF00,
                )
                embed.add_field(
                    name="⚠️ Action Required",
                    value=(
                        "You need to update your API key to use OpenRouter:\n"
                        "1. Sign up or log in to OpenRouter at https://openrouter.ai/\n"
                        "2. Get an OpenRouter API key from https://openrouter.ai/settings/keys \n"
                        "3. Set it using: `{p}set api openrouter api_key,<your_openrouter_key>` or the interface provided by `{p}tldwset apikey`.\n"
                        "4. The cog now supports multiple LLM providers through OpenRouter\n"
                    ).format(p=prefix),
                    inline=False,
                ).add_field(
                    name="ℹ️ What Changed",
                    value=(
                        "• Switched from Anthropic Claude API to OpenRouter\n"
                        "• Now supports multiple AI models\n"
                        "• Better reliability and model selection\n"
                        "• Same functionality, better backend\n"
                    ),
                    inline=False,
                ).add_field(  # using existing anthropic key on OpenRouter BYOK
                    name="🔑 Using Your Existing Key",
                    value=(
                        "If you already have an Anthropic API key, you can use it on OpenRouter by following the instructions below:\n"
                        "1. Obtain and set your OpenRouter API key as described above.\n"
                        "2. Go to https://openrouter.ai/settings/integrations and add your Anthropic key in the list of providers.\n"
                        "3. Set the model to `anthropic/claude-3.5-sonnet` or any [other Claude model](https://openrouter.ai/anthropic) you prefer, using the command:\n"
                        "\t`{p}tldwset model anthropic/claude-3.5-sonnet`.\n"
                        "4. Now you can use the TLDW cog with your existing Anthropic key on OpenRouter, which will route requests to Claude models and use existing credits.\n"
                    ).format(p=prefix),
                    inline=False,
                ).set_footer(
                    text="This message will only be sent once. If you need to see it again, use the command `{p}tldwset show_migration`.".format(
                        p=prefix
                    )
                )
                try:
                    await app_info.owner.send(embed=embed)
                except discord.Forbidden:
                    # If we can't DM the owner, log it instead
                    log = logging.getLogger("red.cogs.tldw")
                    log.info(
                        "Could not send migration notification to the bot owner. Please check their DM settings."
                    )
        except Exception:
            # Silently fail if we can't send the notification
            pass

    async def cog_load(self) -> None:
        """Called when the cog is loaded"""
        # Check if we need to show the OpenRouter migration notification
        await self._check_migration_notification()
        await self.initialize()

    async def cog_unload(self) -> None:
        """Called when the cog is unloaded"""
        self.bot.tree.remove_command(
            self.youtube_summary_context_menu.name,
            type=self.youtube_summary_context_menu.type,
        )
        self.bot.tree.remove_command(
            self.youtube_summary_context_menu_private.name,
            type=self.youtube_summary_context_menu_private.type,
        )
        if self.llm_client:
            await self.llm_client.close()

    @commands.group()
    async def tldwset(self, ctx: commands.Context) -> None:
        """Settings for the video summarizer"""
        pass

    @tldwset.command(name="model")
    async def set_model(
        self, ctx: commands.Context, model: t.Optional[str] = None
    ) -> None:
        """Set the model to use for summarization (owner only)"""
        if not model:
            # send the current model
            current_model = await self.config.model()
            await ctx.send(f"Current model: {current_model}")
            return

        # validate the model name against the available models

        async with aiohttp.ClientSession() as session:
            async with session.get("https://openrouter.ai/api/v1/models") as resp:
                try:
                    resp.raise_for_status()
                except aiohttp.ClientResponseError as e:
                    await ctx.send(
                        f"Failed to fetch available models: {e}. Please check your internet connection or try again later."
                    )
                    return
                data = await resp.json()
                available_models = data.get("data", [])

        if model not in [m["id"] for m in available_models]:
            await ctx.send(
                f"Model '{model}' is not available, please check the available models at https://openrouter.ai/models."
            )
            return

        await self.config.model.set(model)
        await ctx.send(f"Model set to: {model}")

    @commands.is_owner()
    @tldwset.command(name="apikey")
    async def set_api_key(self, ctx: commands.Context):
        """Set the LLM API key (admin only)."""
        view = SetApiView(
            default_service="openrouter",
            default_keys={
                "api_key": ""  # Placeholder for the OpenRouter API key
            },
        )
        await ctx.send(
            "Click the button below to set the API key for OpenRouter. This will allow you to use the TLDW cog.",
            view=view,
        )

    @commands.is_owner()
    @tldwset.command(name="prompt")
    async def set_prompt(
        self, ctx: commands.Context, *, prompt: t.Optional[str]
    ) -> None:
        """Set the system prompt (owner only)"""
        if not prompt:
            # send the current prompt
            current_prompt = await self.config.system_prompt()
            await ctx.send(f"Current system prompt: {current_prompt}")
            return
        await self.config.system_prompt.set(prompt)
        await ctx.send("System prompt set successfully.")

    @commands.is_owner()
    @tldwset.command(name="reset_migration")
    async def reset_migration_notification(self, ctx: commands.Context) -> None:
        """Reset the migration notification flag (owner only)"""
        await self.config.migration_notified.set(False)
        await ctx.send(
            "Migration notification flag has been reset. The notification will be shown again on next cog load."
        )

    @commands.is_owner()
    @tldwset.command(name="show_migration")
    async def show_migration_notification(self, ctx: commands.Context) -> None:
        """Manually show the migration notification (owner only)"""
        await self._send_migration_notification()
        await ctx.send("Migration notification sent!")

    @tldwset.group(name="languages", invoke_without_command=True)
    async def languages(self, ctx: commands.Context) -> None:
        """Set the languages for the transcript API"""
        await ctx.send_help()

    @commands.is_owner()
    @languages.command(name="add")
    async def add_language(
        self, ctx: commands.Context, language: t.Optional[str] = None
    ) -> None:
        """Add a language to the list of languages for the transcript API"""

        async with self.config.languages() as langs:
            if language:
                # add the language to the list if it isn't already there
                if language in langs:
                    await ctx.reply(f"Language '{language}' already exists.")
                    return
                langs.append(language)
                # send a message to the user with the language added
                await ctx.reply(f"Language '{language}' added successfully.")
                return

            class AddLanguageModal(discord.ui.Modal, title="Add Language"):
                language = discord.ui.TextInput(
                    label="Language", placeholder="e.g. en-US", required=True
                )

                async def on_submit(self, interaction: discord.Interaction) -> None:
                    langs.append(self.language.value)
                    await interaction.response.edit_message(
                        content=f"Language '{self.language.value}' added successfully.",
                        view=None,
                    )

            class MyView(discord.ui.View):
                @discord.ui.button(label="Add Language", style=ButtonStyle.blurple)
                async def button_callback(self, interaction, button):
                    return await interaction.response.send_modal(AddLanguageModal())

            await ctx.reply("Click the button to add a language:", view=MyView())

    @commands.is_owner()
    @languages.command(name="remove")
    async def remove_languages(
        self, ctx: commands.Context, number: t.Optional[int] = None
    ) -> None:
        """Remove a language from the list of languages for the transcript API by its number."""
        languages = await self.config.languages()
        if not languages:
            await ctx.send("No languages set.")
            return

        if number is not None:
            # remove the language by number
            async with self.config.languages() as langs:
                removed_lang = langs.pop(number - 1)
            await ctx.send(f"Language '{removed_lang}' removed successfully.")
            return

        # create a discord view to manage the languages
        async def remove_callback(interaction: discord.Interaction) -> None:
            # get the language index from the button id
            lang_index = int(interaction.data.get("custom_id"))
            async with self.config.languages() as langs:
                removed_lang = langs.pop(lang_index)
            await interaction.response.edit_message(
                content=f"Language '{removed_lang}' removed successfully.", view=None
            )

        view = discord.ui.View(timeout=60)
        for i, lang in enumerate(languages):
            button = discord.ui.Button(
                label=lang, style=ButtonStyle.red, custom_id=str(i)
            )
            button.callback = remove_callback
            view.add_item(button)

        await ctx.send("Select a language to remove:", view=view)

    @commands.is_owner()
    @languages.command(name="list")
    async def list_languages(self, ctx: commands.Context) -> None:
        """List the languages for the transcript API"""
        languages = await self.config.languages()
        if not languages:
            await ctx.send("No languages set.")
            return
        # create a discord embed to display the languages
        embed = discord.Embed(
            title="Languages",
            description="\n".join(
                f"[{i + 1}] {lang}" for i, lang in enumerate(languages)
            ),
        )
        embed.set_footer(
            text="Use `tldwset languages remove <number>` to remove a language, or `tldwset languages add <language>` to add a language."
        )
        await ctx.send(embed=embed)

    @commands.is_owner()
    @languages.command(name="clear")
    async def clear_languages(self, ctx: commands.Context) -> None:
        """Clear the list of languages for the transcript API"""
        view = ConfirmView(ctx.author)
        view.message = await ctx.send(
            "Are you sure you want to clear the list of languages? This will remove all languages.",
            view=view,
        )
        await view.wait()
        if view.result:
            async with self.config.languages() as languages:
                languages.clear()
            await ctx.reply("Languages cleared successfully.")
        else:
            await ctx.reply("Languages not cleared.")

    # allow reordering (reprioritising) of the languages
    @commands.is_owner()
    @languages.command(name="reorder")
    async def reorder_languages(self, ctx: commands.Context) -> None:
        """Reorder the languages for the transcript API.

        The order of the languages will be set to the order provided.
        Any languages not provided will be appended to the end of the list.

        Example:
            When the current languages are ['en-US', 'en-GB', 'en']
            and the command is called with ['en-GB', 'en-US']
            the new order will be ['en-GB', 'en-US', 'en']
        """
        if not await self.config.languages():
            await ctx.reply(
                f"No languages set. Add a language first using `{ctx.clean_prefix}tldwset languages add`."
            )
            return

        # create a discord view to manage the languages
        async def make_view():
            # create a discord view to manage the languages
            view = discord.ui.View(timeout=60)
            for i, lang in enumerate(await self.config.languages()):
                button = discord.ui.Button(
                    label=lang, style=ButtonStyle.blurple, custom_id=str(i)
                )
                button.callback = reorder_callback
                view.add_item(button)

            done_button = discord.ui.Button(
                label="Done", style=ButtonStyle.green, row=4
            )
            done_button.callback = done
            view.add_item(done_button)

            async def on_timeout():
                view.stop()
                await view.message.edit(view=None, content="Timeout! Please try again.")

            view.on_timeout = on_timeout
            return view

        async def done(interaction: discord.Interaction) -> None:
            view.stop()
            await view.message.edit(view=None, content="Done reordering languages.")

        async def reorder_callback(interaction: discord.Interaction) -> None:
            # get the language index from the button id
            lang_index = int(interaction.data.get("custom_id"))
            async with self.config.languages() as langs:
                moved_lang = langs[
                    lang_index
                ]  # Save the language before modifying the list
                langs.insert(0, langs.pop(lang_index))
            # update the view with the new order
            view = await make_view()
            view.message = interaction.message
            await interaction.response.edit_message(
                content=f"Language '{moved_lang}' moved to the top.",  # Use the saved language
                view=view,
            )

        view = await make_view()
        view.message = await ctx.reply(
            "Select a language to move to the top:", view=view
        )

    @commands.hybrid_command(name="tldw")
    async def summarize(self, ctx: commands.Context, video_url: str) -> None:
        """Summarize a YouTube video using OpenRouter."""
        if not self.llm_client:
            await ctx.send("API key is not set. Please set the API key first.")
            return

        async with ctx.typing():
            try:
                summary = await self.handlesummarize(video_url)
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
                raise  # so we can get traceback in the bot

        await ctx.reply(embed=summary)

    async def summarize_msg_callback(
        self, inter: discord.Interaction, message: discord.Message
    ) -> None:
        """Summarize a YouTube video using OpenRouter from a message context menu."""
        is_private = inter.command.extras.get("is_private", False)
        await inter.response.defer(thinking=True, ephemeral=is_private)
        try:
            summary = await self._process_video_message(message)
        except Exception as e:
            await inter.edit_original_response(content=str(e))
            raise  # so we can get traceback in the bot
        await inter.edit_original_response(embed=summary)

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
        transcript = await get_transcript(
            self.yt_transcript_fetcher,
            video_id,
            languages=await self.config.languages(),
        )

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

    async def generate_summary(self, text: str) -> str | None:
        """Generate a summary using OpenRouter."""
        if not self.llm_client:
            raise ValueError("API key is not set. Please set the API key first.")
        if not self.llm_client.api_key:
            raise ValueError("API key is not set. Please set the API key first.")
        if not text:
            raise ValueError("No text to summarize.")
        system_prompt = await self.config.system_prompt()
        if not system_prompt:
            raise ValueError(
                "System prompt is not set. Please set the system prompt first."
            )
        model = await self.config.model()
        other_models = await self.config.other_models()
        if not model:
            raise ValueError("Model is not set. Please set the model first.")
        if not other_models:
            other_models = []
        # Call the get_llm_response coroutine to get the summary
        try:
            return await get_llm_response(
                self.llm_client,
                text,
                system_prompt,
                model=model,
                other_models=other_models,
            )
        except Exception as e:
            raise ValueError(f"Error generating summary: {e}") from e


def cleanup_summary(summary: str):
    """The summary should have a closing ```"""
    if not summary or not summary.strip():
        raise ValueError("Failed to generate a summary, no content found.")
    # remove any leading or trailing whitespace
    return markdown_to_embed(
        summary.split("```")[
            0
        ]  # the closing ``` indicates the end of the summary, only keep everything before it
        .strip()  # remove leading/trailing whitespace
        .strip("\n")
    )


# convert the markdown summary to a discord embed
def markdown_to_embed(markdown: str) -> discord.Embed:
    """Convert a markdown string to a Discord embed."""
    if not markdown:
        raise ValueError("Markdown content is empty or None.")
    if markdown.startswith("# "):
        title, content = markdown.split("\n", 1)
        content = content.strip()  # remove leading/trailing whitespace
        if not content:
            raise ValueError("Markdown content is empty after title.")
        # create an embed with the title and content
        embed = discord.Embed(description=content, color=discord.Color.blue())
        embed.title = title.strip(
            "# "
        ).strip()  # remove the leading "# " from the title
    else:
        embed = discord.Embed(description=markdown, color=discord.Color.blue())
        embed.title = "Video Summary"
    return embed


async def get_transcript(
    transcript_fetcher: YouTubeTranscriptFetcher,
    video_id: str,
    languages: list[str] = ["en-US", "en-GB", "en"],
) -> str:
    """Get the transcript of a YouTube video."""
    # get the transcript of the video using the video id
    try:
        available_languages = transcript_fetcher.list_languages(video_id=video_id)
        # find the first language in the list of languages that is available for the video
        language = next(
            (lang for lang in languages if lang in available_languages), None
        )
        if not language:
            raise ValueError(
                f"No available transcript for video {video_id} in languages {languages}.\nAvailable languages: {[lang.code for lang in available_languages]}"
            )
        # fetch the transcript in the specified language
        transcript = transcript_fetcher.get_transcript(
            video_id=video_id, language=language
        )
    except NoTranscriptError as e:
        raise ValueError(
            f"No transcript available for video {video_id} in language {language}."
        ) from e
    except VideoNotFoundError as e:
        raise ValueError(
            f"Couldn't find transcript for video {video_id}. Please check the video ID exists and is accessible."
        ) from e
    except Exception as e:
        raise ValueError("Error getting transcript: " + str(e))

    # return the transcript as text
    return transcript.text if transcript else ""


def get_video_id(video_url: str) -> str:
    """Extract the YouTube video ID from the URL"""
    # extract the YT video ID from the URL using regex
    # there may be gubbins after the video ID, so we need to be careful
    video_id = re.search(
        r"(?<=v=)[\w-]+|(?<=youtu\.be/)[\w-]+|(?<=shorts/)[\w-]+", video_url
    )
    if video_id:
        return video_id.group(0)
    else:
        raise ValueError("Invalid YouTube video URL")


async def get_llm_response(
    llm_client: AsyncLLM,
    text: str,
    system_prompt: str,
    model: str = "openrouter/auto",
    other_models: list[str] = [],
) -> str | None:
    response = await llm_client.chat.completions.create(
        model=model,
        # The `extra_body` parameter with the `models` key is specific to OpenRouter.
        # It enables OpenRouter's model fallback feature, allowing the use of alternative models.
        extra_body={
            "models": other_models,
        },
        # discord character limit is 4096, and tokens are roughly 2-4 chars each, so 1000 tokens should be safe
        max_tokens=1000,
        temperature=0.0,
        n=1,
        stop=["```"],
        messages=[
            {
                "role": "developer",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": text
                + "\n\n"
                + "Summarise the key points in this video transcript in the form of markdown-formatted concise notes, in the language of the transcript.",
            },
            {
                "role": "assistant",
                "content": "Here are the key points from the video transcript:\n\n```markdown",
            },
        ],
    )
    return response.choices[0].message.content
