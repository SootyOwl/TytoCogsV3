from tldw.tldw import TLDWatch
from redbot.core.bot import Red

__red_end_user_data_statement__ = "This cog does not store end user data."


async def setup(bot: Red):
    await bot.add_cog(TLDWatch(bot))
