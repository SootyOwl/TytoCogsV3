"""Aurora Cog for Red Discord Bot

This cog integrates the Letta AI service to create an autonomous Discord agent
that can respond to messages in channels and DMs.
"""

import logging
from typing import Optional

from letta_client import AsyncLetta
from redbot.core import Config, commands
from redbot.core.bot import Red

from aurora.config import GlobalConfig, GuildConfig, ChannelConfig

log = logging.getLogger("red.tyto.aurora")


class Aurora(commands.Cog):
    """Autonomous Discord person powered by Letta."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=3897456238745, force_registration=True
        )

        default_global: dict = GlobalConfig().to_dict()
        self.config.register_global(**default_global)

        default_guild: dict = GuildConfig().to_dict()
        self.config.register_guild(**default_guild)

        default_channel: dict = ChannelConfig().to_dict()
        self.config.register_channel(**default_channel)

        # Letta client (will be initialized in setup)
        self.letta: Optional[AsyncLetta] = None

    async def cog_load(self):
        """Load the Letta client and start the background tasks."""
        global_config = await self.config.all_guilds()
        letta_base_url = global_config.get("letta_base_url", "https://api.letta.ai")

        self.letta = AsyncLetta(base_url=letta_base_url)

        # Start background tasks if needed
        self.background_tasks.start()

    async def cog_unload(self):
        """Stop the background tasks."""
        self.background_tasks.stop()
