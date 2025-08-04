"""Create links to atl.wiki for properly formatted wikilinks"""

from discord.ext import commands

import re

RE_WIKI_LINK_IN_MESSAGE = r"\[\[([^\n\[\]#<|{}_�:][^\n\[\]#<|{}_�]*)\]\](?=([^`]|```([^`]|`{1,2}([^`]|$))+```|``([^`]|`([^`]|$))+``|`[^`]+`)*$)"

class AutoLinker(commands.Cog):
    """Automatically reply to a message with links to atl.wiki articles if it contains a properly formatted wikilink"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        matches = re.findall(RE_WIKI_LINK_IN_MESSAGE, message.content)

        if (len(matches) == 0):
            return

        matches = [match[i][0] for match in matches]
        links = [f'[atl.wiki/{match}](https://atl.wiki/{match.replace(" ", "_")})' for match in matches]
        
        await message.reply(content=', '.join(links))

async def setup(bot: commands.Bot) -> None:
    """Set up the wikilinker cog."""
    await bot.add_cog(AutoLinker(bot))
