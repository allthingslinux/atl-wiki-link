"""Core verification logic using a state machine approach."""

import discord
from typing import Optional, Union, Any, List
from enum import Enum
from dataclasses import dataclass

from .config import Config
from .database import DatabaseManager
from .embeds import WikiEmbeds
from loguru import logger
from .logger import log_user_action, log_verification


class VerificationState(Enum):
    """States for the verification process."""

    INITIAL = "initial"
    CHECKING_STATUS = "checking_status"
    TESTING_DM_PERMISSIONS = "testing_dm_permissions"
    CREATING_TOKEN = "creating_token"
    SENDING_VERIFICATION = "sending_verification"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class VerificationContext:
    """Context object to hold verification state and data."""

    user: Union[discord.User, discord.Member]
    guild_id: Optional[int]
    state: VerificationState = VerificationState.INITIAL
    token: Optional[str] = None
    error_message: Optional[str] = None
    user_status: Optional[Any] = None
    response_handler: Optional[Any] = None  # For sending responses back to Discord


class VerificationService:
    """Service class for handling verification flow using state machine."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    async def process_verification(
        self,
        user: Union[discord.User, discord.Member],
        guild_id: Optional[int] = None,
        response_handler: Optional[Any] = None,
    ) -> tuple[VerificationState, Optional[discord.Embed], Optional[str]]:
        """
        Process verification for a user.

        Returns:
            tuple: (final_state, embed_to_send, error_message)
        """
        context = VerificationContext(
            user=user, guild_id=guild_id, response_handler=response_handler
        )

        state_machine = VerificationStateMachine(self.db)
        result = await state_machine.process(context)

        return context.state, result, context.error_message

    async def get_verification_status(self, user_id: int) -> Optional[Any]:
        """Get verification status for a user."""
        return self.db.get_user_status(user_id)

    async def remove_verification(self, user_id: int) -> bool:
        """Remove verification for a user."""
        return self.db.remove_verification(user_id)

    async def get_verified_users(self) -> List[Any]:
        """Get all verified users."""
        return self.db.get_verified_users()


class VerificationStateMachine:
    """State machine for handling verification flow."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def process(self, context: VerificationContext) -> Optional[discord.Embed]:
        """Process the verification state machine."""
        while context.state not in [
            VerificationState.COMPLETED,
            VerificationState.ERROR,
        ]:
            if context.state == VerificationState.INITIAL:
                await self._transition_to_checking_status(context)
            elif context.state == VerificationState.CHECKING_STATUS:
                await self._handle_status_check(context)
            elif context.state == VerificationState.TESTING_DM_PERMISSIONS:
                await self._handle_dm_permission_test(context)
            elif context.state == VerificationState.CREATING_TOKEN:
                await self._handle_token_creation(context)
            elif context.state == VerificationState.SENDING_VERIFICATION:
                await self._handle_verification_sending(context)

        # Return appropriate embed based on final state
        if context.state == VerificationState.ERROR:
            return WikiEmbeds.error(
                "Verification Error",
                context.error_message
                or "An unknown error occurred during verification.",
                user=context.user,
            )
        elif context.state == VerificationState.COMPLETED and context.token:
            # Only return success embed if we actually sent a verification link
            return WikiEmbeds.success(
                "Verification Link Sent!",
                "📬 I've sent you a DM with your verification link.\n\n"
                "**Next steps:**\n"
                "1. Check your DMs for the verification link\n"
                "2. Click the link to verify your MediaWiki account\n"
                "3. If you meet the [requirements](https://atl.wiki/Atl.wiki:Discord_Linking), you'll automatically receive the wiki editor role\n\n"
                "⏰ The link expires in 10 minutes.\n"
                "🔒 **Do not share this link with anyone, including ATL staff.**",
                user=context.user,
            )
        else:
            # Other completion cases (already verified, pending) handled inline
            return None

    async def _transition_to_checking_status(
        self, context: VerificationContext
    ) -> None:
        """Transition from initial state to checking status."""
        log_user_action(
            "verify_command",
            context.user.id,
            context.user.display_name,
            context.guild_id,
        )
        context.state = VerificationState.CHECKING_STATUS

    async def _handle_status_check(self, context: VerificationContext) -> None:
        """Handle checking if user is already verified or has pending verification."""
        try:
            context.user_status = self.db.get_user_status(context.user.id)

            if context.user_status and context.user_status[0]:  # Already verified
                log_verification(
                    "already_verified", context.user.id, context.user.display_name
                )

                if context.response_handler:
                    embed = WikiEmbeds.success(
                        "Already Verified",
                        "Your Discord account is already linked to a MediaWiki account.\n\n"
                        "🔗 To unlink your account at anytime you can use `/unverify`.\n"
                        "📝 If you are missing the role and meet the [requirements](https://atl.wiki/Atl.wiki:Discord_Linking), you can unverify and reverify to receive it.",
                        user=context.user,
                    )
                    await context.response_handler(embed)

                context.state = VerificationState.COMPLETED
                return

            context.state = VerificationState.TESTING_DM_PERMISSIONS

        except Exception as e:
            logger.error(f"Error checking user status: {e}", user_id=context.user.id)
            context.error_message = (
                "Failed to check verification status. Please try again later."
            )
            context.state = VerificationState.ERROR

    async def _handle_dm_permission_test(self, context: VerificationContext) -> None:
        """Handle testing DM permissions."""
        try:
            # Send a test message first
            test_message = await context.user.send("🔍 Testing DM permissions...")
            await test_message.delete()  # Clean up test message
            context.state = VerificationState.CREATING_TOKEN

        except discord.Forbidden:
            logger.warning(
                "DM permission denied",
                user_id=context.user.id,
                username=context.user.display_name,
            )

            if context.response_handler:
                embed = WikiEmbeds.error(
                    "DM Permission Required",
                    "I need to send you a verification link via DM, but I can't message you.\n\n"
                    "**Please enable DMs from server members:**\n"
                    "1. Right-click this server\n"
                    "2. Go to Privacy Settings\n"
                    "3. Enable 'Allow direct messages from server members'\n"
                    "4. Try the command again",
                    user=context.user,
                )
                await context.response_handler(embed)

            context.state = VerificationState.COMPLETED
        except Exception as e:
            logger.error(f"Unexpected DM test error: {e}", user_id=context.user.id)
            context.error_message = (
                "Something went wrong while testing DM permissions. Please try again."
            )
            context.state = VerificationState.ERROR

    async def _handle_token_creation(self, context: VerificationContext) -> None:
        """Handle creating verification token."""
        try:
            context.token = self.db.create_verification_token(context.user.id)

            if not context.token:
                log_verification("pending", context.user.id, context.user.display_name)

                if context.response_handler:
                    embed = WikiEmbeds.pending(
                        "Verification Pending",
                        "You already have a pending verification request.\n\n"
                        "📬 Please check your DMs for the verification link.\n"
                        "⏰ If you can't find it, please wait an hour and try again.\n"
                        "⚠️ If you still have issues, please contact a member of the wiki team.",
                        user=context.user,
                    )
                    await context.response_handler(embed)

                context.state = VerificationState.COMPLETED
                return

            context.state = VerificationState.SENDING_VERIFICATION

        except Exception as e:
            logger.error(
                f"Error creating verification token: {e}", user_id=context.user.id
            )
            context.error_message = (
                "Failed to create verification token. Please try again later."
            )
            context.state = VerificationState.ERROR

    async def _handle_verification_sending(self, context: VerificationContext) -> None:
        """Handle sending verification link to user."""
        try:
            verification_link = f"{Config.VERIFICATION_URL}?token={context.token}"
            verification_embed = WikiEmbeds.verification_start(
                context.user, verification_link
            )
            await context.user.send(embed=verification_embed)

            log_verification("started", context.user.id, context.user.display_name)
            context.state = VerificationState.COMPLETED

        except discord.Forbidden:
            logger.error(
                "DM send failed after successful test", user_id=context.user.id
            )
            context.error_message = "Verification link could not be sent. Please ensure DMs are enabled and try again."
            context.state = VerificationState.ERROR
        except Exception as e:
            logger.error(
                f"Error sending verification link: {e}", user_id=context.user.id
            )
            context.error_message = (
                "Failed to send verification link. Please try again later."
            )
            context.state = VerificationState.ERROR
