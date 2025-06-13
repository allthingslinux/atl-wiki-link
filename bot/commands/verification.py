"""Verification-related commands with improved UX and error handling using a state machine approach."""

import discord
from discord.ext import commands
from typing import Optional

from ..core.config import Config
from ..core.verification import VerificationService, VerificationState
from ..core.embeds import WikiEmbeds
from ..core.pagination import VerificationPaginator, Paginator
from loguru import logger
from ..core.logger import log_user_action


class VerificationCommands(commands.Cog):
    """Commands for MediaWiki verification with improved UX."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verification_service = VerificationService()

    @commands.hybrid_command(
        name="verify",
        description="Link your Discord account to your MediaWiki account",
        aliases=["link", "connect"],
    )
    async def verify(self, ctx: commands.Context[commands.Bot]) -> None:
        """Start MediaWiki verification process using state machine."""
        await ctx.defer(ephemeral=True)

        async def response_handler(embed: discord.Embed) -> None:
            """Handle sending responses back to Discord."""
            await ctx.send(embed=embed, ephemeral=True)

        try:
            # Process verification through the service
            (
                final_state,
                result_embed,
                _,
            ) = await self.verification_service.process_verification(
                user=ctx.author,
                guild_id=ctx.guild.id if ctx.guild else None,
                response_handler=response_handler,
            )

            # Only send embed if we have one and haven't already sent a response
            if result_embed and final_state == VerificationState.COMPLETED:
                await ctx.send(embed=result_embed, ephemeral=True)
            elif final_state == VerificationState.ERROR and result_embed:
                await ctx.send(embed=result_embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Verification command error: {e}", user_id=ctx.author.id)
            embed = WikiEmbeds.error(
                "Verification Error",
                "Something went wrong during verification setup. Please try again later.\n\n"
                "If this problem persists, please contact a moderator.",
                user=ctx.author,
            )
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="verified",
        description="Show all verified users (Admin only)",
        aliases=["list_verified", "status"],
    )
    async def check_verified(self, ctx: commands.Context[commands.Bot]) -> None:
        """List all verified users with pagination."""
        await ctx.defer(ephemeral=True)

        user = ctx.author
        guild_id = ctx.guild.id if ctx.guild else None

        log_user_action("check_verified_command", user.id, user.display_name, guild_id)

        # Check bot admin permissions
        if not isinstance(user, discord.Member) or not self._has_bot_admin_permissions(
            user
        ):
            logger.warning("Unauthorized verified command attempt", user_id=user.id)
            embed = WikiEmbeds.error(
                "Permission Denied",
                "You don't have permission to view verified users.\n\n"
                "This command is restricted to wiki administrators.",
                user=user,
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        try:
            # Get verified users through the service
            verified_users = await self.verification_service.get_verified_users()

            # Create paginated embeds
            pages = VerificationPaginator.create_verification_pages(
                verified_users=verified_users, users_per_page=15, requesting_user=user
            )

            # Send with pagination
            await Paginator.send_paginated(
                ctx=ctx, pages=pages, ephemeral=True, timeout=300.0
            )

            logger.info(
                "Verified users list requested",
                user_id=user.id,
                count=len(verified_users),
            )

        except Exception as e:
            logger.error(f"Error fetching verified users: {e}", user_id=user.id)
            embed = WikiEmbeds.error(
                "Database Error",
                "Could not retrieve verified users list. Please try again later.",
                user=user,
            )
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="unverify",
        description="Remove your MediaWiki verification (Admin only)",
        aliases=["unlink", "disconnect"],
    )
    async def unverify(
        self,
        ctx: commands.Context[commands.Bot],
        target_user: Optional[discord.Member] = None,
    ) -> None:
        """Remove verification for a user (admin command)."""
        await ctx.defer(ephemeral=True)

        user = ctx.author
        guild_id = ctx.guild.id if ctx.guild else None

        log_user_action("unverify_command", user.id, user.display_name, guild_id)

        # Check bot admin permissions
        if not isinstance(user, discord.Member) or not self._has_bot_admin_permissions(
            user
        ):
            logger.warning("Unauthorized unverify command attempt", user_id=user.id)
            embed = WikiEmbeds.error(
                "Permission Denied",
                "You don't have permission to unverify users.\n\n"
                "This command is restricted to administrators.",
                user=user,
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        # Default to self if no target specified
        if not target_user:
            target_user = user

        try:
            # Remove verification through the service
            success = await self.verification_service.remove_verification(
                target_user.id
            )

            if success:
                logger.success(
                    "User unverified",
                    target_id=target_user.id,
                    target_username=target_user.display_name,
                    admin_id=user.id,
                )
                embed = WikiEmbeds.success(
                    "User Unverified",
                    f"Successfully removed verification for **{target_user.display_name}**.\n\n"
                    "🔗 They will need to verify again to regain wiki access.",
                    user=user,
                )
            else:
                embed = WikiEmbeds.warning(
                    "User Not Found",
                    f"**{target_user.display_name}** was not verified.",
                    user=user,
                )

            await ctx.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(
                f"Error removing verification: {e}",
                user_id=user.id,
                target_id=target_user.id,
            )
            embed = WikiEmbeds.error(
                "Unverify Error",
                "Could not remove verification. Please try again later.",
                user=user,
            )
            await ctx.send(embed=embed, ephemeral=True)

    def _has_bot_admin_permissions(self, user: discord.Member) -> bool:
        """Check if user has bot admin permissions."""
        roles = getattr(user, "roles", None)
        if not roles:
            return False

        return any(
            getattr(role, "id", None) in Config.ALLOWED_ROLE_IDS for role in roles
        )


async def setup(bot: commands.Bot) -> None:
    """Set up the verification commands cog."""
    await bot.add_cog(VerificationCommands(bot))
