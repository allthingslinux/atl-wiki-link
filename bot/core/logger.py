"""Logging utilities using loguru for the Discord bot."""

import sys
from typing import Any, Optional
from loguru import logger


def setup_logging() -> None:
    """Configure loguru logging for the bot."""
    # Remove default handler
    logger.remove()

    # Add console handler with nice formatting
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>WikiBot</cyan> | <level>{message}</level>",
        level="INFO",
        colorize=True,
    )

    # Add file handler for errors (optional, uncomment if you want file logging)
    # logger.add(
    #     "logs/bot_errors.log",
    #     format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    #     level="ERROR",
    #     rotation="1 week",
    #     retention="1 month"
    # )


def log_user_action(
    action: str, user_id: int, username: str, guild_id: Optional[int] = None
) -> None:
    """Log user action with context."""
    context = f"user_id={user_id}, username={username}"
    if guild_id:
        context += f", guild_id={guild_id}"
    logger.info(f"ℹ️ User action: {action} [{context}]")


def log_verification(
    event: str, user_id: int, username: str, wiki_username: Optional[str] = None
) -> None:
    """Log verification events with emoji and context."""
    context = f"user_id={user_id}, username={username}"
    if wiki_username:
        context += f", wiki_username={wiki_username}"

    if event == "started":
        logger.info(f"🔗 Verification started [{context}]")
    elif event == "completed":
        logger.success(f"🎉 Verification completed [{context}]")
    elif event == "failed":
        logger.error(f"💥 Verification failed [{context}]")
    elif event == "already_verified":
        logger.info(f"✅ User already verified [{context}]")
    elif event == "pending":
        logger.warning(f"📬 User has pending verification [{context}]")


def log_role_grant(
    user_id: int, username: str, guild_name: str, success: bool = True
) -> None:
    """Log role granting events."""
    context = f"user_id={user_id}, username={username}, guild={guild_name}"
    if success:
        logger.success(f"✅ Role granted [{context}]")
    else:
        logger.error(f"❌ Failed to grant role [{context}]")


def log_database_action(action: str, success: bool = True, **kwargs: Any) -> None:
    """Log database actions."""
    context_parts = [f"{k}={v}" for k, v in kwargs.items()]
    context = f"[{', '.join(context_parts)}]" if context_parts else ""

    if success:
        logger.info(f"🗄️ Database: {action} {context}")
    else:
        logger.error(f"💥 Database error: {action} {context}")


# Set up logging when module is imported
setup_logging()
