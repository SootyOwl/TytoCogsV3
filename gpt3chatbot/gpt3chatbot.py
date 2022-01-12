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

        # Get OpenAI API Key
        openai_api = await self.bot.get_shared_api_tokens("openai")
        if not (key := openai_api.get("key")):
            return

        # Remove bot mention
        filtered = re.sub(f"<@!?{self.bot.user.id}>", "", message.content)
        # clean custom emoji
        filtered = await self._filter_custom_emoji(filtered)
        if not filtered:
            return

        # Get response from OpenAI
        async with message.channel.typing():
            response = await self._get_response(key=key, uid=message.author.id, msg=filtered)

        if hasattr(message, "reply"):
            return await message.reply(response, mention_author=False)

        return await message.channel.send(response)
