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
        description="Remove your MediaWiki verification or (admin) remove for others by Discord or wiki name",
        aliases=["unlink", "disconnect"],
    )
    async def unverify(
        self,
        ctx: commands.Context[commands.Bot],
        target_user: Optional[discord.Member] = None,
        mediawiki_username: Optional[str] = None,
    ) -> None:
        """Remove verification for yourself (anyone) or for others (admin, by Discord or wiki username)."""
        await ctx.defer(ephemeral=True)

        user = ctx.author
        guild_id = ctx.guild.id if ctx.guild else None

        log_user_action("unverify_command", user.id, user.display_name, guild_id)

        # Argument validation
        if target_user and mediawiki_username:
            embed = WikiEmbeds.error(
                "Invalid Usage",
                "Please provide only one of: a Discord user or a MediaWiki username.",
                user=user,
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        # Self-unverify (anyone)
        if not target_user and not mediawiki_username:
            # Remove self
            success = await self.verification_service.remove_verification(user.id)
            if success:
                logger.success(
                    "User self-unverified",
                    target_id=user.id,
                    target_username=user.display_name,
                )
                embed = WikiEmbeds.success(
                    "Verification Removed",
                    f"You have been unverified and your wiki link has been removed.",
                    user=user,
                )
            else:
                embed = WikiEmbeds.warning(
                    "Not Verified",
                    f"You were not verified or already unverified.",
                    user=user,
                )
            await ctx.send(embed=embed, ephemeral=True)
            return

        # Admin-only actions
        if not isinstance(user, discord.Member) or not self._has_bot_admin_permissions(user):
            embed = WikiEmbeds.error(
                "Permission Denied",
                "You don't have permission to unverify other users. This action is restricted to administrators.",
                user=user,
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        # Unverify by Discord user
        if target_user:
            success = await self.verification_service.remove_verification(target_user.id)
            if success:
                logger.success(
                    "User unverified by admin",
                    target_id=target_user.id,
                    target_username=target_user.display_name,
                    admin_id=user.id,
                )
                embed = WikiEmbeds.success(
                    "User Unverified",
                    f"Successfully removed verification for **{target_user.display_name}**.\n\n🔗 They will need to verify again to regain wiki access.",
                    user=user,
                )
            else:
                embed = WikiEmbeds.warning(
                    "User Not Found",
                    f"**{target_user.display_name}** was not verified.",
                    user=user,
                )
            await ctx.send(embed=embed, ephemeral=True)
            return

        # Unverify by MediaWiki username
        if mediawiki_username:
            # Show the stored username if case does not match
            discord_id = await self.verification_service.get_discord_id(mediawiki_username)
            stored_mw_username = None
            if discord_id:
                stored_mw_username = await self.verification_service.get_mediawiki_username(discord_id)
            case_warning = ""
            if stored_mw_username and stored_mw_username.lower() != mediawiki_username.lower():
                case_warning = f"\n⚠️ Note: The stored MediaWiki username is **{stored_mw_username}** (case-sensitive)."
            success = await self.verification_service.remove_verification_by_wiki_username(mediawiki_username)
            if success:
                logger.success(
                    "User unverified by admin (wiki name)",
                    wiki_username=mediawiki_username,
                    admin_id=user.id,
                )
                embed = WikiEmbeds.success(
                    "User Unverified (Wiki Name)",
                    f"Successfully removed verification for MediaWiki user **{mediawiki_username}**.{case_warning}",
                    user=user,
                )
            else:
                embed = WikiEmbeds.warning(
                    "User Not Found",
                    f"No verified user found with MediaWiki username **{mediawiki_username}**.",
                    user=user,
                )
            await ctx.send(embed=embed, ephemeral=True)
            return

    @commands.hybrid_command(
        name="lookup",
        description="Look up Discord user from MediaWiki username or vice versa.",
        aliases=["whois", "resolve"],
    )
    async def lookup(
        self,
        ctx: commands.Context[commands.Bot],
        discord_user: Optional[discord.Member] = None,
        mediawiki_username: Optional[str] = None,
    ) -> None:
        """Look up Discord user from MediaWiki username or vice versa. Anyone can use."""
        await ctx.defer(ephemeral=True)
        user = ctx.author

        # Argument validation
        if (discord_user and mediawiki_username) or (not discord_user and not mediawiki_username):
            embed = WikiEmbeds.error(
                "Invalid Usage",
                "Please provide exactly one of: a Discord user or a MediaWiki username.",
                user=user,
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        if discord_user:
            mw_username = await self.verification_service.get_mediawiki_username(discord_user.id)
            if mw_username:
                case_warning = ""
                if mediawiki_username and mw_username.lower() != mediawiki_username.lower():
                    case_warning = f"\n⚠️ Note: The stored MediaWiki username is **{mw_username}** (case-sensitive)."
                embed = WikiEmbeds.info(
                    "MediaWiki Username Found",
                    f"Discord user **{discord_user.display_name}** is linked to MediaWiki username: **{mw_username}**.{case_warning}",
                    user=user,
                )
            else:
                embed = WikiEmbeds.warning(
                    "Not Linked",
                    f"Discord user **{discord_user.display_name}** is not linked to any MediaWiki account.",
                    user=user,
                )
            await ctx.send(embed=embed, ephemeral=True)
            return

        if mediawiki_username:
            discord_id = await self.verification_service.get_discord_id(mediawiki_username)
            if discord_id:
                # Try to resolve to a member in the current guild, fallback to mention and username#discriminator
                member = ctx.guild.get_member(discord_id) if ctx.guild else None
                display = None
                if member:
                    display = f"{member.mention} ({member.display_name})"
                else:
                    # Try to fetch user object from bot cache
                    fetched_user = self.bot.get_user(discord_id)
                    if fetched_user:
                        display = f"<@{discord_id}> ({fetched_user.name}#{fetched_user.discriminator})"
                    else:
                        display = f"<@{discord_id}>"
                # Also show the normalized MediaWiki username as stored
                stored_mw_username = await self.verification_service.get_mediawiki_username(discord_id)
                case_warning = ""
                if stored_mw_username and stored_mw_username.lower() != mediawiki_username.lower():
                    case_warning = f"\n⚠️ Note: The stored MediaWiki username is **{stored_mw_username}** (case-sensitive)."
                embed = WikiEmbeds.info(
                    "Discord User Found",
                    f"MediaWiki username **{mediawiki_username}** is linked to Discord user: {display}.{case_warning}",
                    user=user,
                )
            else:
                embed = WikiEmbeds.warning(
                    "Not Linked",
                    f"MediaWiki username **{mediawiki_username}** is not linked to any Discord account.",
                    user=user,
                )
            await ctx.send(embed=embed, ephemeral=True)
            return

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
