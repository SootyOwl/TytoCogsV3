import logging
import re

import discord
import openai
from redbot.core import Config
from redbot.core import commands

log = logging.getLogger("red.tytocogsv3.gpt3chatbot")
log.setLevel("DEBUG")

CUSTOM_EMOJI = re.compile(
    "<(?P<animated>a?):(?P<name>[a-zA-Z0-9_]{2,32}):(?P<id>[0-9]{18,22})>"
)  # from brainshop cog


class GPT3ChatBot(commands.Cog):
    """AI chatbot Using GPT3

    An artificial intelligence chatbot using OpenAI's GPT3 (https://openai.org)."""

    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=259390542
        )  # randomly generated identifier
        default_global = {
            "reply": True,
            "memory": 20,
            "personalities": personalities_dict,
        }
        self.config.register_global(**default_global)
        default_guild = {  # default per-guild settings
            "reply": True,
            "channels": [],
            "allowlist": [],
            "blacklist": [],
            "personality": "Aurora",
        }
        self.config.register_guild(**default_guild)
        default_member = {"personality": "Aurora", "chat_log": []}
        self.config.register_member(**default_member)

    @staticmethod
    async def _filter_custom_emoji(message: str) -> str:
        return CUSTOM_EMOJI.sub('', message).strip()

    # async def local_perms(self, message: discord.Message) -> bool:
    #     """Check the user is/isn't locally whitelisted/blacklisted.
    #     https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
    #     """
    #     if await self.bot.is_owner(message.author):
    #         return True
    #     elif message.guild is None:
    #         return True
    #     if not getattr(message.author, "roles", None):
    #         return False
    #     try:
    #         return await self.bot.allowed_by_whitelist_blacklist(
    #             message.author,
    #             who_id=message.author.id,
    #             guild_id=message.guild.id,
    #             role_ids=[r.id for r in message.author.roles],
    #         )
    #     except AttributeError:
    #         guild_settings = self.bot.db.guild(message.guild)
    #         local_blacklist = await guild_settings.blacklist()
    #         local_whitelist = await guild_settings.whitelist()
    #         author: discord.Member = message.author
    #         _ids = [r.id for r in author.roles if not r.is_default()]
    #         _ids.append(message.author.id)
    #         if local_whitelist:
    #             return any(i in local_whitelist for i in _ids)
    #
    #         return not any(i in local_blacklist for i in _ids)

    # async def global_perms(self, message: discord.Message) -> bool:
    #     """Check the user is/isn't globally whitelisted/blacklisted.
    #     https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
    #     """
    #     if version_info >= VersionInfo.from_str("3.3.6"):
    #         if not await self.bot.ignored_channel_or_guild(message):
    #             return False
    #     if await self.bot.is_owner(message.author):
    #         return True
    #     try:
    #         return await self.bot.allowed_by_whitelist_blacklist(message.author)
    #     except AttributeError:
    #         whitelist = await self.bot.db.whitelist()
    #         if whitelist:
    #             return message.author.id in whitelist
    #
    #         return message.author.id not in await self.bot.db.blacklist()

    async def _update_chat_log(self, question, answer):
        self.chat_log = f"""{self.chat_log}
        
        {restart_sequence}{question}
        {start_sequence}{answer}
        """

    async def _should_respond(self, message):
        # ignore bots
        if message.author.bot:
            return False

        global_auto = await self.config.auto()
        starts_with_mention = message.content.startswith((f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"))

        # command is in DMs
        if not message.guild:
            if not starts_with_mention or not global_auto:
                return False

        # command is in a server
        else:
            # cog is disabled or bot cannot send messages in channel
            if await self.bot.cog_disabled_in_guild(self, message.guild) or not message.channel.permissions_for(
                    message.guild.me).send_messages:
                return False

            guild_settings = await self.config.guild(message.guild).all()

            # Not in auto-channel
            if message.channel.id not in guild_settings["channels"] and (
                    not starts_with_mention or  # Does not start with mention
                    not (guild_settings["auto"] or global_auto)  # Both guild & global auto are toggled off
            ):
                return False

        # passed the checks
        return True

    async def _get_response(self, key: str, uid: str, msg: str) -> str:
        prompt_text = f"""{self.chat_log}
        
        {restart_sequence}{msg}              
        {start_sequence}"""

        response = openai.Completion.create(
            engine="ada",
            prompt=prompt_text,
            temperature=0.8,
            max_tokens=150,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0.3,
            stop=["\n"],
        )
        reply = response['choices'][0]['text']
        await self.update_chat_log(question=msg, answer=str(reply))
        return str(reply)

    @commands.Cog.listener("on_message_without_command")
    async def _message_listener(self, message: discord.Message):
        """This does stuff!"""
        if not self._should_respond(message=message):
            return

    async def _build_prompt_from_chat_log(self, new_msg: discord.Message) -> str:
        """Serialize the chat_log into a prompt for the AI request.
        :param new_msg: The new message
        :return: prompt_text
        """
        personalities_dict = await self.config.personalities()
        personality_name: str = await self.config.member(new_msg.author).personality()
        prompt_text, initial_chat_log = personalities_dict[personality_name].values()
        log.debug(f"{personalities_dict=}\n\n{personality_name=}\n\n{prompt_text}")
        async with self.config.member(new_msg.author).chat_log() as chat_log:
            # include initial_chat_log and chat_log in prompt_text
            for entry in chain(initial_chat_log, chat_log):
                prompt_text += (
                    f"{new_msg.author.display_name}: {entry['input']}\n"
                    f"{personality_name}: {entry['reply']}\n###\n"
                )
        prompt_text += (
            f"{new_msg.author.display_name}: {await self._filter_message(new_msg)}\n"
            f"{personality_name}:"
        )
        log.debug(f"{prompt_text=}")
        return str(prompt_text)

    async def _update_chat_log(
            self, author: Union[discord.User, discord.Member], question: str, answer: str
    ):
        """Update chat log with new response, so the bot can remember conversations."""
        new_response = {"timestamp": time.time(), "input": question, "reply": answer}
        log.info(
            f"Adding new response to the chat log: {author.id=}, {new_response['timestamp']=}"
        )

        # create queue from chat chat_log
        chat_log = await self.config.member(author).chat_log()
        deq_chat_log = deque(chat_log)
        log.debug(f"current length {len(deq_chat_log)=}")
        if not len(deq_chat_log) <= (mem := await self.config.memory()):
            log.debug(f"length at {mem=}, popping oldest log:")
            log.debug(deq_chat_log.popleft())
        deq_chat_log.append(new_response)
        # back to list for saving
        await self.config.member(author).chat_log.set(list(deq_chat_log))

    @commands.command(name="clear_log")
    async def clear_personal_history(self, ctx):
        """Clear chat log."""
        await self.config.member(ctx.author).clear()
        return await ctx.tick()
