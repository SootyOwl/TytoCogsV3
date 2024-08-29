from redvids.redvids import RedVids


async def setup(bot):
    await bot.add_cog(RedVids(bot))
