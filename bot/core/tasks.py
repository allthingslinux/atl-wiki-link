"""Background tasks for the Discord bot."""

import discord
from discord.ext import commands, tasks
from .config import Config
from .database import DatabaseManager


class BotTasks:
    """Handles bot background tasks."""

    def __init__(self, bot: commands.Bot, db: DatabaseManager):
        self.bot = bot
        self.db = db

    def start_tasks(self):
        """Start all background tasks."""
        self.purge_old_links.start()
        self.grant_roles_loop.start()

    def stop_tasks(self):
        """Stop all background tasks."""
        if self.purge_old_links.is_running():
            self.purge_old_links.stop()
        if self.grant_roles_loop.is_running():
            self.grant_roles_loop.stop()

    @tasks.loop(minutes=Config.PURGE_INTERVAL)
    async def purge_old_links(self):
        """Remove old unverified tokens."""
        deleted_count = self.db.purge_old_tokens()
        if deleted_count > 0:
            print(f"🧹 Purged {deleted_count} old unverified links.")

    @tasks.loop(minutes=Config.ROLE_GRANT_INTERVAL)
    async def grant_roles_loop(self):
        """Grant roles to verified users."""
        if not Config.WIKI_AUTHOR_ROLE_ID:
            return

        verified_ids = self.db.get_verified_user_ids()

        for guild in self.bot.guilds:
            for discord_id in verified_ids:
                member = guild.get_member(discord_id)
                if member and not self._has_wiki_role(member):
                    try:
                        await member.add_roles(
                            discord.Object(id=Config.WIKI_AUTHOR_ROLE_ID)
                        )
                        print(
                            f"✅ Granted wiki role to {member.display_name} in {guild.name}"
                        )
                    except discord.Forbidden:
                        print(
                            f"❌ Missing permissions to grant role to {member.display_name} in {guild.name}"
                        )
                    except Exception as e:
                        print(f"❌ Error granting role to {member.display_name}: {e}")

    def _has_wiki_role(self, member: discord.Member) -> bool:
        """Check if member already has the wiki author role."""
        return Config.WIKI_AUTHOR_ROLE_ID in [role.id for role in member.roles]
