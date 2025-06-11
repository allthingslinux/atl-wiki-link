"""Entry point for the Discord bot."""

import asyncio
from .bot import create_bot
from .core.config import Config


async def main():
    """Main entry point for the bot."""
    bot = None
    
    try:
        if not Config.DISCORD_TOKEN:
            print("❌ DISCORD_TOKEN is not set in the configuration. Exiting.")
            return

        bot = create_bot()
        await bot.start(Config.DISCORD_TOKEN)

    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot crashed: {e}")
        raise

    finally:
        if bot is not None:
            await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
