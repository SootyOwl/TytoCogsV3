from aurora.aurora import Aurora
from redbot.core.bot import Red

__red_end_user_data_statement__ = """This cog interacts with the Letta agent which may store user data as memory blocks.
Please refer to the Letta documentation for more details on data handling and privacy."""


async def setup(bot: Red):
    await bot.add_cog(Aurora(bot))
