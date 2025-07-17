"""Create links to atl.wiki for properly formatted wikilinks"""

from discord.ext import commands

import re

class AutoLinker(commands.Cog):
    """Automatically reply to a message with links to atl.wiki articles if it contains a properly formatted wikilink"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        matches = re.findall(r"\[\[[^\n]+\]\]", message.content)
        
        links = []
        
        if (message.author.bot):
            return
        
        if (len(matches) == 0):
            return
        
        for match in matches:
            # i wish you could do re.sub(x, y, z).sub(x, y, z) but alas, the language forced my hand
            match = re.sub(r"\[\[", "", match)
            match = re.sub(r"\]\]", "", match)
            match_clean = re.sub(" ", "_", match)
            
            links.append(f"[[[`{match}`]]](https://atl.wiki/{match_clean})")
        
        await message.reply(content=f"Link{'' if len(links) == 1 else 's'}: {', '.join(links)}")
        
            

async def setup(bot: commands.Bot) -> None:
    """Set up the wikilinker cog."""
    await bot.add_cog(AutoLinker(bot))
