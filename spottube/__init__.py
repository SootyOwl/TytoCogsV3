from spottube.spottube import SpotTube


async def setup(bot):
    await bot.add_cog(SpotTube(bot))
