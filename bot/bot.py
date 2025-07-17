"""Main bot class and setup."""

import discord
from discord.ext import commands
from .core.config import Config
from .core.database import DatabaseManager
from .core.tasks import BotTasks
from .commands.verification import setup as setup_verification_commands
from .commands.linker import setup as setup_autolinker

class WikiBot(commands.Bot):
    """Main Discord bot class."""

    def __init__(self):
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        # Initialize bot
        super().__init__(
            command_prefix=Config.DISCORD_PREFIX,
            intents=intents,
            description="atl.wiki bot",
        )

        # Initialize components
        self.db = DatabaseManager()
        self.tasks = BotTasks(self, self.db)

    async def setup_hook(self):
        """Called when the bot is starting up."""
        print("🚀 Setting up bot...")

        # Validate configuration
        Config.validate()

        # Test and initialize database
        if not self.db.test_connection():
            raise RuntimeError("Failed to connect to database")

        self.db.init_database()

        # Load commands
        await setup_verification_commands(self)
        
        await setup_autolinker(self)
        
        # Sync command tree
        await self.tree.sync()
        print("✅ Command tree synced")

    async def on_ready(self):
        """Called when the bot is ready."""
        print(f"🤖 Logged in as {self.user}!")

        # Start background tasks
        self.tasks.start_tasks()

        print("✅ Bot is ready!")

    async def close(self):
        """Clean shutdown."""
        print("🛑 Shutting down bot...")

        # Stop background tasks
        self.tasks.stop_tasks()

        # Close database connections and parent
        await super().close()

        print("✅ Bot shutdown complete")


def create_bot() -> WikiBot:
    """Create and return a configured bot instance."""
    return WikiBot()
