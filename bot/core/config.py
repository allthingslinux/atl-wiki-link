"""Configuration management for the Discord bot."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Bot configuration settings."""

    # Discord settings
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    DISCORD_PREFIX = os.getenv("DISCORD_PREFIX", "$w")

    # Database settings
    DATABASE_URL = os.getenv("DATABASE_URL")

    # MediaWiki settings
    VERIFICATION_URL = os.getenv("VERIFICATION_URL")

    # Role settings
    WIKI_AUTHOR_ROLE_ID = int(os.getenv("WIKI_AUTHOR_ROLE_ID", "0"))
    # Bot admin role IDs (not Discord admin permissions) - users with these roles can use admin commands
    ALLOWED_ROLE_IDS = list(map(int, os.getenv("ALLOWED_ROLE_IDS", "").split(",")))

    # Task intervals (in minutes)
    PURGE_INTERVAL = 30
    ROLE_GRANT_INTERVAL = 5

    # Token expiry (in hours)
    TOKEN_EXPIRY_HOURS = 3

    @classmethod
    def validate(cls) -> None:
        """Validate that required environment variables are set."""
        required_vars = [
            ("DISCORD_TOKEN", cls.DISCORD_TOKEN),
            ("DATABASE_URL", cls.DATABASE_URL),
            ("VERIFICATION_URL", cls.VERIFICATION_URL),
        ]

        missing_vars = [name for name, value in required_vars if not value]

        if missing_vars:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

        assert cls.DISCORD_TOKEN is not None
