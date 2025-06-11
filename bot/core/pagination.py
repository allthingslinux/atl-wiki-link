"""Pagination utility for Discord embeds with navigation controls."""

import discord
from typing import List, Optional, Callable, Any, Union, Tuple
from discord.ext import commands
from math import ceil


class PaginationView(discord.ui.View):
    """View class for handling pagination interactions."""

    def __init__(
        self,
        pages: List[discord.Embed],
        timeout: float = 300.0,
        user_id: Optional[int] = None,
    ):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.user_id = user_id
        self.message: Optional[discord.Message] = None

        # Update button states
        self.update_buttons()

    def update_buttons(self) -> None:
        """Update button states based on current page."""
        # Disable/enable buttons based on current page
        self.first_page.disabled = self.current_page == 0
        self.previous_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page == len(self.pages) - 1
        self.last_page.disabled = self.current_page == len(self.pages) - 1

        # Update page counter
        if hasattr(self, "page_counter"):
            self.page_counter.label = f"{self.current_page + 1}/{len(self.pages)}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the user can interact with this pagination."""
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot interact with this pagination.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.gray, custom_id="first")
    async def first_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Go to first page."""
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[0], view=self)

    @discord.ui.button(
        label="◀️", style=discord.ButtonStyle.primary, custom_id="previous"
    )
    async def previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Go to previous page."""
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current_page], view=self
        )

    @discord.ui.button(
        label="1/1", style=discord.ButtonStyle.gray, custom_id="counter", disabled=True
    )
    async def page_counter(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Page counter (non-interactive)."""
        pass

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary, custom_id="next")
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Go to next page."""
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current_page], view=self
        )

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.gray, custom_id="last")
    async def last_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Go to last page."""
        self.current_page = len(self.pages) - 1
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.current_page], view=self
        )

    @discord.ui.button(label="🗑️", style=discord.ButtonStyle.danger, custom_id="delete")
    async def delete_message(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Delete the pagination message."""
        if self.message:
            await self.message.delete()
        else:
            await interaction.response.defer()

    async def on_timeout(self) -> None:
        """Called when the view times out."""
        # Disable all buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        # Try to edit the message to show it's timed out
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass  # Message was deleted


class Paginator:
    """Utility class for creating paginated embeds."""

    @staticmethod
    def create_pages(
        items: List[Any],
        items_per_page: int = 10,
        title_formatter: Optional[Callable[[int, int, int], str]] = None,
        description_formatter: Optional[Callable[[List[Any], int, int], str]] = None,
        embed_color: int = 0x0099FF,
        footer_formatter: Optional[Callable[[int, int], str]] = None,
    ) -> List[discord.Embed]:
        """
        Create a list of embed pages from items.

        Args:
            items: List of items to paginate
            items_per_page: Number of items per page
            title_formatter: Function to format page titles (current_page, total_pages, total_items)
            description_formatter: Function to format page descriptions (page_items, current_page, total_pages)
            embed_color: Color for the embeds
            footer_formatter: Function to format page footers (current_page, total_pages)
        """
        if not items:
            # Return a single empty page
            embed = discord.Embed(
                title="No Items Found",
                description="There are no items to display.",
                color=embed_color,
                timestamp=discord.utils.utcnow(),
            )
            return [embed]

        total_pages = ceil(len(items) / items_per_page)
        pages: List[discord.Embed] = []

        for page_num in range(total_pages):
            start_idx = page_num * items_per_page
            end_idx = start_idx + items_per_page
            page_items = items[start_idx:end_idx]

            # Default formatters
            if title_formatter is None:
                title = f"Items (Page {page_num + 1}/{total_pages})"
            else:
                title = title_formatter(page_num + 1, total_pages, len(items))

            if description_formatter is None:
                description = "\n".join(str(item) for item in page_items)
            else:
                description = description_formatter(
                    page_items, page_num + 1, total_pages
                )

            embed = discord.Embed(
                title=title,
                description=description,
                color=embed_color,
                timestamp=discord.utils.utcnow(),
            )

            if footer_formatter is None:
                embed.set_footer(
                    text=f"Page {page_num + 1} of {total_pages} • {len(items)} total items"
                )
            else:
                embed.set_footer(text=footer_formatter(page_num + 1, total_pages))

            pages.append(embed)

        return pages

    @staticmethod
    async def send_paginated(
        ctx: Union[commands.Context[commands.Bot], discord.Interaction],
        pages: List[discord.Embed],
        ephemeral: bool = False,
        timeout: float = 300.0,
    ) -> None:
        """
        Send paginated embeds with navigation controls.

        Args:
            ctx: Context or interaction to respond to
            pages: List of embed pages
            ephemeral: Whether to send as ephemeral (for interactions)
            timeout: How long the pagination should stay active
        """
        if not pages:
            return

        # If only one page, send without pagination
        if len(pages) == 1:
            if isinstance(ctx, discord.Interaction):
                if ctx.response.is_done():
                    await ctx.followup.send(embed=pages[0], ephemeral=ephemeral)
                else:
                    await ctx.response.send_message(embed=pages[0], ephemeral=ephemeral)
            else:
                await ctx.send(embed=pages[0])
            return

        # Create pagination view
        user_id = None
        if isinstance(ctx, discord.Interaction):
            user_id = ctx.user.id
        else:  # commands.Context
            user_id = ctx.author.id

        view = PaginationView(pages=pages, timeout=timeout, user_id=user_id)
        view.update_buttons()

        # Send the first page with navigation
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                message = await ctx.followup.send(
                    embed=pages[0], view=view, ephemeral=ephemeral, wait=True
                )
            else:
                await ctx.response.send_message(
                    embed=pages[0], view=view, ephemeral=ephemeral
                )
                message = await ctx.original_response()
        else:
            message = await ctx.send(embed=pages[0], view=view)

        view.message = message


class VerificationPaginator:
    """Specialized paginator for verification user lists."""

    @staticmethod
    def create_verification_pages(
        verified_users: List[Tuple[int, str]],
        users_per_page: int = 15,
        requesting_user: Optional[Union[discord.User, discord.Member]] = None,
    ) -> List[discord.Embed]:
        """Create paginated embeds for verified users list."""

        def title_formatter(
            current_page: int, total_pages: int, total_items: int
        ) -> str:
            return f"📊 Verified Users (Page {current_page}/{total_pages})"

        def description_formatter(
            page_items: List[Tuple[int, str]], current_page: int, total_pages: int
        ) -> str:
            if not page_items:
                return "No verified users found."

            user_list: List[str] = []
            start_num = (current_page - 1) * users_per_page + 1

            for i, (discord_id, wiki_username) in enumerate(page_items):
                num = start_num + i
                user_list.append(f"`{num:2d}.` <@{discord_id}> → **{wiki_username}**")

            return "\n".join(user_list)

        def footer_formatter(current_page: int, total_pages: int) -> str:
            footer_text = f"Page {current_page} of {total_pages} • {len(verified_users)} verified users"
            if requesting_user:
                footer_text += f" • Requested by {requesting_user.display_name}"
            return footer_text

        pages = Paginator.create_pages(
            items=verified_users,
            items_per_page=users_per_page,
            title_formatter=title_formatter,
            description_formatter=description_formatter,
            embed_color=0x00FF00,  # Success green
            footer_formatter=footer_formatter,
        )

        # Add additional fields to each page
        for page in pages:
            page.add_field(
                name="📈 Stats",
                value=f"**{len(verified_users)}** total verified users",
                inline=True,
            )
            page.add_field(
                name="🔗 Actions",
                value="Use `/unverify @user` to remove verification",
                inline=True,
            )

        return pages
