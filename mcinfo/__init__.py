from redbot.core.bot import Red
from mcinfo.mcinfo import McInfo


async def setup(bot: Red):
    await bot.add_cog(McInfo(bot))
