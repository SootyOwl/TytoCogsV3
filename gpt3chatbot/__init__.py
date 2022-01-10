from .gpt3chatbot import GPT3ChatBot

def setup(bot):
    bot.add_cog(GPT3ChatBot(bot))
