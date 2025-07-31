"""Create links to atl.wiki for properly formatted wikilinks"""

from discord.ext import commands

import re

class AutoLinker(commands.Cog):
    """Automatically reply to a message with links to atl.wiki articles if it contains a properly formatted wikilink"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        matches = re.findall(r"\[\[[^\n]+\]\]", message.content)

        links = []
        
        if (len(matches) == 0):
            return
        
        for match in matches:
            match = re.sub(r"\[\[", "", match)
            match = re.sub(r"\]\]", "", match)
            match_clean = re.sub(" ", "_", match)
            
            links.append(f"[atl.wiki/{match}](https://atl.wiki/{match_clean})")
        
        await message.reply(content=f"{', '.join(links)}")
        
            

async def setup(bot: commands.Bot) -> None:
    """Set up the wikilinker cog."""
    await bot.add_cog(AutoLinker(bot))
