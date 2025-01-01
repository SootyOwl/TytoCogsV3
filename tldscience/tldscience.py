import base64
from anthropic.types.text_block import TextBlock
from anthropic.types.tool_use_block import ToolUseBlock
import httpx
from redbot.core import commands, Config
from redbot.core.bot import Red
import anthropic
import discord
from typing import List, Optional


class TLDScience(commands.Cog):
    """Use Claude to create short summaries of scientific PDFs."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=844362129371,  # Random identifier
            force_registration=True,
        )
        
        # Default settings
        default_global = {
            "api_key": None,
            "system_prompt": (
                "You are an expert scientist and science communicator."
            )
        }
        
        self.config.register_global(**default_global)
        self.anthropic_client = None
        
    async def initialize(self) -> None:
        """Initialize the Anthropic client with the stored API key"""
        api_key = await self.config.api_key()
        if api_key:
            self.anthropic_client = anthropic.Client(api_key=api_key)

    async def cog_load(self) -> None:
        """Called when the cog is loaded"""
        await self.initialize()

    @commands.group()
    async def tldscience(self, ctx: commands.Context) -> None:
        """Commands for the Claude article summarizer"""
        pass

    @commands.is_owner()
    @tldscience.command(name="setapikey")
    async def set_api_key(self, ctx: commands.Context, api_key: str) -> None:
        """Set the Anthropic API key (admin only)
        
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
        self.anthropic_client = anthropic.Client(api_key=api_key)
        await ctx.send("API key has been set successfully!")

    @commands.is_owner()
    @tldscience.command(name="setprompt")
    async def set_system_prompt(self, ctx: commands.Context, *, prompt: str) -> None:
        """Set the system prompt for Claude (admin only)"""
        await self.config.system_prompt.set(prompt)
        await ctx.send("System prompt has been updated successfully!")

    @tldscience.command(name="summarize")
    async def summarize(self, ctx: commands.Context, *, url: Optional[str] = None) -> None:
        """Summarize provided text or attached file using Claude"""
        if not await self.bot.is_owner(ctx.author):
            # Check if the command is used in the proper channel
            # Add any additional permission checks here
            pass

        # Handle file attachments
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if not any(attachment.filename.endswith(ext) for ext in ['.pdf']):
                return await ctx.send("Please provide a valid PDF document")
            pdf_url = attachment.url
        # handle url input
        else:
            if not any(url.startswith(pfx) for pfx in ['http://', 'https://']):
                return await ctx.send("Please provide a valid link.")
            if not any(url.endswith(ext) for ext in ['.pdf']):
                return await ctx.send("Please provide a valid PDF document")
            pdf_url = url


        # try to get the pdf data from the url
        try:
            pdf_data = base64.standard_b64encode(httpx.get(pdf_url).content).decode("utf-8")
        except Exception as e:
            return await ctx.send("Something went wrong getting the PDF.")
        
        # Check if we have text to process
        if not pdf_data:
            await ctx.send("Something went wrong retrieving the PDF data.")
            return

        async with ctx.typing():
            try:
                # Generate summary
                summary = await self.generate_summary(pdf_data)
                
                if summary:
                    await ctx.send(summary[0].text)
                else:
                    await ctx.send("Sorry, I couldn't generate a summary. Please try again.")
                    
            except commands.UserFeedbackCheckFailure as e:
                await ctx.send(str(e))
            except Exception as e:
                await ctx.send(f"An unexpected error occurred: {str(e)}")


    async def generate_summary(self, pdf_data) -> List[TextBlock]:
        # get the response
        response = self.anthropic_client.messages.create(
            model = "claude-3-5-sonnet-latest",
            max_tokens=2048,
            system=await self.config.system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_data
                            },
                            "cache_control": {"type": "ephemeral"}
                        },
                        {
                            "type": "text",
                            "text": "Create a concise summary of this scientific article, using 3-5 sentences. Include relevant emojis and explain key findings."
                        }
                    ]
                },
                {
                    "role": "assistant",
                    "content": "Here's a summary of the scientific article with key findings:"
                }
            ]
        )

        return response.content