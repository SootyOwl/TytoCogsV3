from .historylesson import HistoryLesson


async def setup(bot):
    await bot.add_cog(HistoryLesson(bot))