"""Aurora Cog for Red Discord Bot

This cog integrates the Letta AI service to create an autonomous Discord agent
that can respond to messages in channels and DMs.
"""

import logging
from typing import Optional

from discord.ext import tasks
from letta_client import AsyncLetta
from redbot.core import Config, commands
from redbot.core.bot import Red

log = logging.getLogger("red.tyto.aurora")


class Aurora(commands.Cog):
    """Autonomous Discord person powered by Letta."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=3897456238745, force_registration=True
        )

        # Letta client (will be initialized in setup)
        self.letta: Optional[AsyncLetta] = None
        self.tasks: dict[str, tasks.Loop] = {}

    async def cog_load(self):
        """Load the Letta client and start the heartbeats."""
        await self.initialize_letta()

    async def initialize_letta(self):
        """Configure Letta client based on global settings."""
        letta_base_url = await self.config.letta_base_url()
        letta_tokens = await self.bot.get_shared_api_tokens("letta")
        if token := letta_tokens.get("token"):
            self.letta = AsyncLetta(
                base_url=letta_base_url,
                token=token,
            )
            log.info("Letta client configured successfully.")
            return self.letta
        else:
            log.warning("Letta API token not found. Aurora will not function.")
            self.letta = None
            return None

    def cancel_tasks(self):
        """Cancel all running tasks."""
        for task_name, task in self.tasks.items():
            if task.is_running():
                task.cancel()
                log.info("Cancelled task %s", task_name)
        self.tasks.clear()

    async def cog_unload(self):
        """Stop the heartbeats."""
        self.cancel_tasks()
