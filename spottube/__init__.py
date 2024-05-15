from spottube.spottube import SpotTube


async def setup(bot):
    bot.add_cog(SpotTube(bot))
