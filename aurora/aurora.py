"""Aurora Cog for Red Discord Bot

This cog integrates the Letta AI service to create an autonomous Discord agent
that can respond to messages in channels and DMs.
"""

from datetime import date
import logging
from typing import Optional

from discord.ext import tasks
from letta_client import AsyncLetta, MessageCreate
from redbot.core import Config, commands
from redbot.core.bot import Red

from .utils import attach_blocks, detach_blocks

log = logging.getLogger("red.tyto.aurora")


class Aurora(commands.Cog):
    """Autonomous Discord person powered by Letta."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=3897456238745, force_registration=True
        )
        default_global = {
            "letta_base_url": "https://api.letta.ai/v1",
        }
        self.config.register_global(**default_global)

        default_guild = {
            "agent_id": None,
            "enabled": False,
        }
        self.config.register_guild(**default_guild)

        # Letta client (will be initialized in setup)
        self.letta: Optional[AsyncLetta] = None
        self.tasks: dict[str, tasks.Loop] = {}

    async def cog_load(self):
        """Load the Letta client and start the synthesiss."""
        await self.initialize_letta()
        # start synthesis tasks for all guilds with enabled agents
        all_guilds: dict[int, dict] = await self.config.all_guilds()
        for guild_id, guild_config in all_guilds.items():
            if guild_config.get("enabled") and guild_config.get("agent_id"):
                self._get_or_create_task(guild_id)

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

    async def cog_unload(self):
        """Stop the synthesiss."""
        self._cancel_tasks()

    # region: Tasks
    def _get_or_create_task(
        self, guild_id: int, interval_secs: int = 3600
    ) -> tasks.Loop:
        """Get or create a task for the given guild."""
        task_name = f"synthesis_{guild_id}"
        if task_name not in self.tasks:
            task = tasks.loop(seconds=interval_secs)(self.synthesis)
            self.tasks[task_name] = task
            task.start(guild_id=guild_id)
            log.info("Started synthesis task for guild %d", guild_id)
        return self.tasks[task_name]

    def _remove_task(self, guild_id: int):
        """Remove and cancel the task for the given guild."""
        task_name = f"synthesis_{guild_id}"
        if task_name in self.tasks:
            task = self.tasks[task_name]
            if task.is_running():
                task.cancel()
                log.info("Cancelled synthesis task for guild %d", guild_id)
            del self.tasks[task_name]

    def _cancel_tasks(self):
        """Cancel all running tasks."""
        for task_name, task in self.tasks.items():
            if task.is_running():
                task.cancel()
                log.info("Cancelled task %s", task_name)
        self.tasks.clear()
        log.info("All tasks cancelled.")

    async def synthesis(self, guild_id: int):
        """A synthesis task to allow aurora to perform periodic actions."""
        log.debug("synthesis for guild %d", guild_id)
        today = date.today()
        heatbeat_prompt = f"""Time for self-reflection and synthesis.

You have access to temporal journal blocks for recording your thoughts and experiences:
- aurora_daily_{today.strftime("%Y_%m_%d")}: Today's journal ({today.strftime("%B %d, %Y")})
- aurora_month_{today.strftime("%Y_%m")}: This month's journal ({today.strftime("%B %Y")})
- aurora_year_{today.strftime("%Y")}: This year's journal ({today.year})

Use them to:
1. Record significant interactions and insights from recent experiences
2. Track patterns in conversations and user behaviors
3. Note your evolving understanding of the digital social environment
4. Reflect on your growth and changes in perspective
5. Document memorable moments or interesting discoveries

The journal entries should be cumulative - add to existing content rather than replacing it.
Consider both immediate experiences (daily) and longer-term patterns (monthly/yearly).

After recording in your journals, synthesize your recent experiences into your core memory blocks
(zeitgeist, aurora-persona, aurora-humans) as you normally would.

Begin your synthesis and journaling now.
"""
        if not self.letta:
            log.warning("Letta client not configured. Cannot run synthesis.")
            return

        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                log.warning("Guild %d not found. Stopping synthesis task.", guild_id)
                self._remove_task(guild_id)
                return

            guild_config = await self.config.guild(guild).all()
            agent_id = guild_config.get("agent_id")
            if not agent_id:
                log.warning(
                    "Agent ID not configured for guild %d. Stopping synthesis task.",
                    guild_id,
                )
                self._remove_task(guild_id)
                return

            # attach necessary blocks
            block_names = [
                f"aurora_daily_{today.strftime('%Y_%m_%d')}",
                f"aurora_month_{today.strftime('%Y_%m')}",
                f"aurora_year_{today.strftime('%Y')}",
            ]
            success, attached = await attach_blocks(self.letta, agent_id, block_names)
            if not success:
                log.warning(
                    "Failed to attach blocks for guild %d during synthesis.", guild_id
                )

            # Send the synthesis prompt to the agent
            message_stream = self.letta.agents.messages.create_stream(
                agent_id=agent_id,
                messages=[MessageCreate(role="user", content=heatbeat_prompt)],
                stream_tokens=False,
                max_steps=100,
            )

            # Process the streamed response
            async for chunk in message_stream:
                match chunk.message_type:
                    case "reasoning_message":
                        log.debug(
                            "synthesis reasoning chunk received for guild %d:", guild_id
                        )
                        for line in chunk.reasoning.splitlines():
                            log.debug(f"\t{line}")
                    case "tool_call_message":
                        log.debug(
                            "synthesis tool call chunk received for guild %d:", guild_id
                        )
                        log.debug("\tTool: %s", chunk.tool_call.name)
                        log.debug("\tInput: %s", chunk.tool_call.arguments)
                    case "tool_return_message":
                        if chunk.status == "success":
                            log.debug("Success", f"Tool result: {chunk.name}")
                        else:
                            log.warning("Tool error: %s", chunk.name, chunk.stderr)
                    case None:
                        if str(chunk) == "done":
                            log.debug("synthesis done for guild %d", guild_id)
                            break
                    case _:
                        log.debug(
                            "synthesis unknown chunk type %s for guild %d",
                            chunk.message_type,
                            guild_id,
                        )
        except Exception as e:
            log.exception(
                "Exception during synthesis for guild %d: %s", guild_id, str(e)
            )
        finally:
            # detach blocks
            if self.letta and agent_id and attached:
                success, _ = await detach_blocks(self.letta, agent_id, block_names)
                if not success:
                    log.warning(
                        "Failed to detach blocks for guild %d after synthesis.",
                        guild_id,
                    )

    # endregion

    # region: Commands and Listeners
