import newspaper
from redbot.core import commands, Config
from redbot.core.bot import Red
import discord
from typing import Optional
from anthropic import AsyncAnthropic


class HistoryLesson(commands.Cog):
    """
    Provides historical context for news articles using newspaper3k and Anthropic API.
    """

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=9834759283,  # Replace with a random identifier
            force_registration=True,
        )

        default_global = {
            "api_key": None,
            "model": "claude-3-opus-latest",
            "system_prompt": "You are a world-class history professor.",
        }
        self.config.register_global(**default_global)
        self.anthropic_client = None

    async def initialize(self) -> None:
        """Initialize the Anthropic client with the stored API key"""
        api_key = await self.config.api_key()
        if api_key:
            self.anthropic_client = AsyncAnthropic(api_key=api_key)

    async def cog_load(self) -> None:
        """Called when the cog is loaded"""
        await self.initialize()

    @commands.group()
    async def historylesson(self, ctx: commands.Context) -> None:
        """Commands for the HistoryLesson cog."""
        pass

    @commands.is_owner()
    @historylesson.command(name="setapikey")
    async def set_api_key(self, ctx: commands.Context, api_key: str) -> None:
        """Set the Anthropic API key (admin only)"""
        # Delete the command message if it's not in DMs
        if ctx.guild is not None:
            try:
                await ctx.message.delete()
            except (discord.errors.Forbidden, discord.errors.NotFound):
                pass

            await ctx.send("Please use this command in DM to keep your API key private.")
            return

        await self.config.api_key.set(api_key)
        self.anthropic_client = AsyncAnthropic(api_key=api_key)
        await ctx.send("API key has been set successfully!")

    @commands.is_owner()
    @historylesson.command(name="setprompt")
    async def set_system_prompt(self, ctx: commands.Context, *, prompt: str) -> None:
        """Set the system prompt for Claude (admin only)"""
        await self.config.system_prompt.set(prompt)
        await ctx.send("System prompt has been updated successfully!")

    @historylesson.command(name="context")
    async def get_context(self, ctx: commands.Context, url: str) -> None:
        """
        Gets historical context for a news article from a given URL.
        """
        try:
            article = newspaper.Article(url)
            article.download()
            article.parse()
            news_content = article.text
        except Exception as e:
            await ctx.send(f"Failed to extract article content. Error: {e}")
            return

        if not news_content:
            await ctx.send("Could not extract the article content.")
            return

        async with ctx.typing():
            try:
                # Generate historical context and extract the summary text from the response content
                historical_context = await self.generate_historical_context(news_content)
                output = await self.extract_summary(historical_context)
            except commands.UserFeedbackCheckFailure as e:
                await ctx.send(str(e))
                return
            except Exception as e:
                await ctx.send(f"An unexpected error occurred: {str(e)}")
                return

            # Send the output
            if not output:
                await ctx.send("Failed to generate a summary.")
                return
            await ctx.send(output)

    async def generate_historical_context(self, news_content: str) -> str:
        """
        Generates historical context for the given news content using the Anthropic API.
        """
        response = await self.anthropic_client.messages.create(
            model=await self.config.model(),
            max_tokens=4096,
            temperature=0.3,
            system=await self.config.system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": f"Provide historical context for the following news article:\n\n{news_content}\n\nFocus on events, people, and situations that are relevant to the article. Provide a summary of the context in 3-5 sentences.",
                }
            ],
        )
        return response.content[0].text

    async def extract_summary(self, text: str) -> str:
        """Extract the summary from the response"""
        if not text:
            return ""

        return text.strip()