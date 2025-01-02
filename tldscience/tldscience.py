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
        default_global = {"api_key": None, "system_prompt": ("You are an expert scientist and science communicator.")}

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
            if not any(attachment.filename.endswith(ext) for ext in [".pdf"]):
                return await ctx.send("Please provide a valid PDF document")
            pdf_url = attachment.url
        # handle url input
        else:
            if not url:
                return await ctx.send("Please provide a valid link.")
            
            # check content type of the url
            # if not a pdf, return an error
            # # get headers 
            headers = httpx.head(url).headers
            if headers.get("Content-Type") != "application/pdf":
                return await ctx.send("Please provide a valid PDF document URL.")
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

                if output := await self.extract_summary(summary):
                    await ctx.send(output)
                else:
                    await ctx.send("Sorry, I couldn't generate a summary. Please try again.")

            except commands.UserFeedbackCheckFailure as e:
                await ctx.send(str(e))
            except Exception as e:
                await ctx.send(f"An unexpected error occurred: {str(e)}")

    async def generate_summary(self, pdf_data) -> List[TextBlock]:
        # get the response
        response = self.anthropic_client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=4096,
            temperature=0,  # same each time
            system=await self.config.system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_data},
                            "cache_control": {"type": "ephemeral"},
                        },
                        {
                            "type": "text",
                            "text": "You are an expert science communicator tasked with summarizing scientific articles for social media. Your goal is to create engaging, informative, and concise summaries that capture the essence of the research while also providing a critical perspective. Please follow these steps to create your summary:\n\n1. Carefully read and analyze the article.\n2. Wrap your analysis inside <article_analysis> tags, addressing the following:\n   - Key findings of the research (include relevant quotes from the article)\n   - Potential critiques or limitations of the study (include relevant quotes from the article)\n   - Significance of the research in its field\n   - Any particularly interesting or surprising aspects\n   - Brainstorm 5-7 potential hashtags and explain their relevance to the article\n\n3. Based on your analysis, create three draft summaries that meet these criteria:\n   - 3-5 sentences long\n   - Includes both key findings and potential critiques\n   - Uses relevant emojis to enhance engagement\n   - Fits into a single social media post\n   - Includes relevant hashtags for better reach\n   - Provides a DOI-style link to the full article\n\n4. Evaluate each draft summary and select the best one, explaining your choice.\n\nYour final output should follow this structure:\n\n<summary>\n[Emoji] Sentence 1\n[Emoji] Sentence 2\n[Emoji] Sentence 3\n(Optional: Sentence 4)\n(Optional: Sentence 5)\n\n#Hashtag1 #Hashtag2 #Hashtag3\n\n🔗 Article: [URL to full article PDF / DOI]\n</summary>\n\nRemember to keep the language accessible to a general audience while maintaining scientific accuracy. It's OK for the article_analysis section to be quite long.",
                        },
                    ],
                },
                {"role": "assistant", "content": [{"type": "text", "text": "<article_analysis>"}]},
            ],
        )

        return response.content

    async def extract_summary(self, text: List[TextBlock]) -> str:
        """Extract the summary from the response"""
        if not text:
            return ""

        # get the text from the first block (and only block in this case)
        text = text[0].text

        # find the <summary></summary> tags and get all the text between them (excluding the tags)
        start = text.find("<summary>")
        end = text.find("</summary>")
        if start == -1 or end == -1:
            return ""

        return text[start + len("<summary>") : end].strip()
