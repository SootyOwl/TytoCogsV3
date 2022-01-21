from gpt3chatbot.gpt3chatbot import GPT3ChatBot
from gpt3chatbot.personalities import personalities_dict  # noqa: F401


def setup(bot):
    bot.add_cog(GPT3ChatBot(bot))
