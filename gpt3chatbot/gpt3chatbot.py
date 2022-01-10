from redbot.core import commands


class GPT3ChatBot(commands.Cog):
    """A chatbot that uses GPT3 to generate messages."""

    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @commands.command()
    async def reply(self, ctx):
        """This does stuff!"""
        # code here
        await ctx.send("I can do stuff!")