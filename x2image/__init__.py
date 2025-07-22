from x2image.x2image import X2Image

__all__ = ["X2Image"]


async def setup(bot):
    await bot.add_cog(X2Image(bot))
