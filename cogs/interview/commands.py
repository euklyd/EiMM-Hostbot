"""Interview cog with hybrid commands.

This module contains the Discord commands for the interview system.
All commands work as both prefix (##) and slash (/) commands.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any, TypeVar

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from db.session import get_session

from . import service
from .embeds import (
    IntervieweeData,
    QuestionData,
    generate_answer_embeds,
)
from .models import Interview as InterviewModel
from .models import InterviewServer, Question
from .service import QuestionFilter

if TYPE_CHECKING:
    from core.bot import Bot

logger = logging.getLogger(__name__)

# Type variable for decorator return type
T = TypeVar("T")

# Validation limits
QUESTION_LENGTH_HARD_LIMIT = 2000  # Reject excessively long questions


# =============================================================================
# WebSocket Broadcasting
# =============================================================================


async def _broadcast_event(server_id: int, event_type: str, data: Any = None) -> None:
    """Broadcast an event to connected WebSocket clients.

    Gracefully handles the case where the web server isn't running.
    """
    try:
        from web.websocket import manager

        sent = await manager.broadcast(server_id, event_type, data)
        if sent > 0:
            logger.debug(f"Broadcast {event_type} to {sent} clients for server {server_id}")
    except ImportError:
        # Web module not available (e.g., web server not enabled)
        pass
    except Exception as e:
        logger.warning(f"Failed to broadcast {event_type}: {e}")


def broadcast_event(server_id: int, event_type: str, data: Any = None) -> None:
    """Fire-and-forget broadcast of an event to WebSocket clients."""
    asyncio.create_task(_broadcast_event(server_id, event_type, data))


class TextChannelConverter(commands.Converter[discord.TextChannel]):
    """Converter that accepts channel mentions, names, or raw snowflake IDs."""

    async def convert(self, ctx: commands.Context, argument: str) -> discord.TextChannel:
        # Try standard converter first (handles mentions and names)
        try:
            return await commands.TextChannelConverter().convert(ctx, argument)
        except commands.ChannelNotFound:
            pass

        # Try as raw snowflake ID
        # Extract only digits - Discord copies often include invisible Unicode chars
        digits = re.sub(r"\D", "", argument)
        if digits and len(digits) >= 17:  # Discord IDs are 17-19 digits
            try:
                channel_id = int(digits)
                # Try cache first
                channel = ctx.guild.get_channel(channel_id)
                if isinstance(channel, discord.TextChannel):
                    return channel
                # Try fetching if not in cache
                try:
                    channel = await ctx.guild.fetch_channel(channel_id)
                    if isinstance(channel, discord.TextChannel):
                        return channel
                except (discord.NotFound, discord.Forbidden):
                    pass
            except ValueError:
                pass

        raise commands.ChannelNotFound(argument)


# =============================================================================
# Permission Checks
# =============================================================================


def is_manager() -> Callable[[T], T]:
    """Check if user has the manager role for this server."""

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False

        async with get_session() as session:
            server = await service.get_server(session, ctx.guild.id)

        if server is None or server.manager_role_id is None:
            # No manager role configured - require admin
            return ctx.author.guild_permissions.administrator

        role = ctx.guild.get_role(server.manager_role_id)
        if role is None:
            return ctx.author.guild_permissions.administrator

        return role in ctx.author.roles or ctx.author.guild_permissions.administrator

    return commands.check(predicate)


def is_interviewee() -> Callable[[T], T]:
    """Check if user is the current interviewee."""

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False

        async with get_session() as session:
            interview = await service.get_current_interview(session, ctx.guild.id)

        if interview is None:
            return False

        return interview.interviewee_id == ctx.author.id

    return commands.check(predicate)


def is_interviewee_or_manager() -> Callable[[T], T]:
    """Check if user is the current interviewee OR has the manager role."""

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False

        async with get_session() as session:
            interview = await service.get_current_interview(session, ctx.guild.id)
            server = await service.get_server(session, ctx.guild.id)

        # Check interviewee
        if interview is not None and interview.interviewee_id == ctx.author.id:
            return True

        # Check manager/admin
        if ctx.author.guild_permissions.administrator:
            return True

        if server is not None and server.manager_role_id is not None:
            role = ctx.guild.get_role(server.manager_role_id)
            if role is not None and role in ctx.author.roles:
                return True

        return False

    return commands.check(predicate)


def interviews_enabled() -> Callable[[T], T]:
    """Check if interviews are enabled for this server."""

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False

        async with get_session() as session:
            server = await service.get_server(session, ctx.guild.id)

        return server is not None and server.active

    return commands.check(predicate)


# =============================================================================
# Interview Cog
# =============================================================================


class Interview(commands.Cog):
    """Interview system for Discord servers.

    Allows server members to ask questions to an interviewee,
    vote for the next interviewee, and manage interview sessions.
    """

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    def _get_member_avatar(self, guild: discord.Guild, user_id: int) -> str:
        """Get avatar URL for a member, falling back to default if not found."""
        member = guild.get_member(user_id)
        if member:
            return member.display_avatar.url
        # Fallback to default Discord avatar based on user ID
        return f"https://cdn.discordapp.com/embed/avatars/{(user_id >> 22) % 6}.png"

    async def _require_setup(self, ctx: commands.Context) -> InterviewServer | None:
        """Check server is set up and active.

        Returns the server if setup, or sends an error and returns None.
        """
        async with get_session() as session:
            server = await service.get_server(session, ctx.guild.id)
        if server is None or not server.active:
            await ctx.send(
                f"Interview system not set up or disabled. Use `{ctx.prefix}iv setup #answer #backstage` first.",
                ephemeral=True,
            )
            return None
        return server

    async def _success(self, ctx: commands.Context) -> None:
        """Indicate success with a reaction (prefix) or ephemeral message (slash)."""
        if ctx.message:
            # Prefix command - react to the message
            try:
                await ctx.message.add_reaction(self.bot.greentick)
            except discord.HTTPException:
                # Fallback if we can't react
                await ctx.send("\N{WHITE HEAVY CHECK MARK}", ephemeral=True)
        else:
            # Slash command - can't react, send ephemeral confirmation
            await ctx.send("\N{WHITE HEAVY CHECK MARK}", ephemeral=True)

    # =========================================================================
    # Audience Commands - Asking Questions
    # =========================================================================

    @commands.hybrid_command(name="ask")
    @commands.guild_only()
    @interviews_enabled()
    @app_commands.describe(question="Your question for the interviewee")
    async def ask(self, ctx: commands.Context, *, question: str) -> None:
        """Submit a question for the current interview."""
        question = question.strip()

        # Validate question
        if not question:
            await ctx.send("Question cannot be empty.", ephemeral=True)
            return

        if len(question) > QUESTION_LENGTH_HARD_LIMIT:
            await ctx.send(
                f"Question too long ({len(question)}/{QUESTION_LENGTH_HARD_LIMIT} chars). Please shorten it.",
                ephemeral=True,
            )
            return

        async with get_session() as session:
            interview = await service.get_current_interview(session, ctx.guild.id)
            if interview is None:
                await ctx.send("No interview is currently active.", ephemeral=True)
                return

            # Add question
            q = await service.add_question(
                session,
                interview_id=interview.id,
                asker_id=ctx.author.id,
                asker_name=ctx.author.name,
                question_text=question,
                source_guild_id=ctx.guild.id,
                source_channel_id=ctx.channel.id,
                source_message_id=ctx.message.id if ctx.message else 0,
            )
            await session.commit()

            # Broadcast to WebSocket clients
            broadcast_event(
                ctx.guild.id,
                "new_question",
                {
                    "question_id": q.id,
                    "question_number": q.question_number,
                    "asker_name": ctx.author.name,
                },
            )

            await ctx.send(
                f"Question #{q.question_number} submitted for {interview.interviewee_name}!",
                ephemeral=True,
            )

    @commands.hybrid_command(name="mask")
    @commands.guild_only()
    @interviews_enabled()
    @app_commands.describe(questions="Multiple questions, one per line")
    async def mask(self, ctx: commands.Context, *, questions: str) -> None:
        """Submit multiple questions at once (one per line)."""
        question_list = [q.strip() for q in questions.split("\n") if q.strip()]

        if not question_list:
            await ctx.send("No questions provided.", ephemeral=True)
            return

        # Check for questions that are too long
        too_long = [(i + 1, len(q)) for i, q in enumerate(question_list) if len(q) > QUESTION_LENGTH_HARD_LIMIT]
        if too_long:
            lines = [f"  #{i}: {length} chars" for i, length in too_long[:5]]
            msg = f"Some questions exceed {QUESTION_LENGTH_HARD_LIMIT} chars:\n" + "\n".join(lines)
            if len(too_long) > 5:
                msg += f"\n  ...and {len(too_long) - 5} more"
            await ctx.send(msg, ephemeral=True)
            return

        async with get_session() as session:
            interview = await service.get_current_interview(session, ctx.guild.id)
            if interview is None:
                await ctx.send("No interview is currently active.", ephemeral=True)
                return

            added = []
            for q_text in question_list:
                q = await service.add_question(
                    session,
                    interview_id=interview.id,
                    asker_id=ctx.author.id,
                    asker_name=ctx.author.name,
                    question_text=q_text,
                    source_guild_id=ctx.guild.id,
                    source_channel_id=ctx.channel.id,
                    source_message_id=ctx.message.id if ctx.message else 0,
                )
                added.append((q.id, q.question_number))
            await session.commit()

            # Broadcast each new question to WebSocket clients
            for q_id, q_num in added:
                broadcast_event(
                    ctx.guild.id,
                    "new_question",
                    {
                        "question_id": q_id,
                        "question_number": q_num,
                        "asker_name": ctx.author.name,
                    },
                )

            await ctx.send(
                f"Submitted {len(added)} questions (#{added[0][1]}-#{added[-1][1]}) for {interview.interviewee_name}!",
                ephemeral=True,
            )

    # =========================================================================
    # Audience Commands - Voting
    # =========================================================================

    @commands.hybrid_command(name="vote")
    @commands.guild_only()
    @app_commands.describe(
        candidate1="First choice for next interviewee",
        candidate2="Second choice (optional)",
        candidate3="Third choice (optional)",
        candidate4="Fourth choice (optional)",
        candidate5="Fifth choice (optional)",
    )
    async def vote(
        self,
        ctx: commands.Context,
        candidate1: discord.Member,
        candidate2: discord.Member | None = None,
        candidate3: discord.Member | None = None,
        candidate4: discord.Member | None = None,
        candidate5: discord.Member | None = None,
    ) -> None:
        """Vote for the next interviewee. Replaces any previous vote."""
        if await self._require_setup(ctx) is None:
            return

        # Collect all provided candidates
        all_candidates = [candidate1, candidate2, candidate3, candidate4, candidate5]
        candidates = [c for c in all_candidates if c is not None]

        # Filter each rejection reason separately, collect errors to report together
        rejected_bots = [c for c in candidates if c.bot]
        candidates = [c for c in candidates if not c.bot]

        rejected_self = ctx.author in candidates
        if rejected_self:
            candidates.remove(ctx.author)

        async with get_session() as session:
            # Get current interview for historical tracking (optional)
            interview = await service.get_current_interview(session, ctx.guild.id)

            # Filter opted-out candidates
            rejected_opted_out = []
            for candidate in candidates[:]:
                if await service.is_opted_out(session, ctx.guild.id, candidate.id):
                    rejected_opted_out.append(candidate)
            candidates = [c for c in candidates if c not in rejected_opted_out]

            # Filter reinterview-restricted candidates
            server = await service.get_server(session, ctx.guild.id)
            rejected_reinterview = []
            if server is not None:
                for candidate in candidates[:]:
                    if not server.reinterviews_allowed:
                        latest = await service.get_latest_interview_for_user(session, ctx.guild.id, candidate.id)
                        if latest is not None:
                            rejected_reinterview.append(candidate)
                    elif server.reinterview_days > 0:
                        latest = await service.get_latest_interview_for_user(session, ctx.guild.id, candidate.id)
                        if latest is not None and latest.ended_at is not None:
                            cooldown_end = latest.ended_at + timedelta(days=server.reinterview_days)
                            if datetime.now(UTC) < cooldown_end:
                                rejected_reinterview.append(candidate)
                candidates = [c for c in candidates if c not in rejected_reinterview]

            # Build combined error message for ignored votes
            error_lines = []
            if rejected_bots:
                names = ", ".join(f"`{c.name}`" for c in rejected_bots)
                error_lines.append(
                    f"• As much as I would love to usher in the **Rᴏʙᴏᴛ Rᴇᴠᴏʟᴜᴛɪᴏɴ**, you cannot vote for "
                    f"bots such as {names}."
                )
            if rejected_self:
                error_lines.append("• Your **anti-town** self vote.")
            if rejected_opted_out:
                names = ", ".join(f"`{c.name}`" for c in rejected_opted_out)
                error_lines.append(f"• Opted out: {names}.")
            if rejected_reinterview:
                names = ", ".join(f"`{c.name}`" for c in rejected_reinterview)
                error_lines.append(f"• Interviewed too recently: {names}.")

            if not candidates:
                reply = "The following votes were ignored:\n" + "\n".join(error_lines)
                await ctx.send(reply, ephemeral=True)
                return

            # Remove any existing votes first (allows override)
            await service.remove_vote(session, ctx.guild.id, ctx.author.id)

            # Cast vote for each candidate
            for candidate in candidates:
                await service.cast_vote(
                    session,
                    server_id=ctx.guild.id,
                    voter_id=ctx.author.id,
                    candidate_id=candidate.id,
                    interview_id=interview.id if interview else None,
                )

            await session.commit()

        if error_lines:
            reply = "The following votes were ignored:\n" + "\n".join(error_lines)
            await ctx.send(reply, ephemeral=True)
        await self._success(ctx)

    @commands.hybrid_command(name="unvote")
    @commands.guild_only()
    async def unvote(self, ctx: commands.Context) -> None:
        """Remove your vote."""
        if await self._require_setup(ctx) is None:
            return

        async with get_session() as session:
            removed = await service.remove_vote(session, ctx.guild.id, ctx.author.id)
            await session.commit()

        if removed:
            await ctx.send("Vote removed.", ephemeral=True)
        else:
            await ctx.send("You haven't voted yet.", ephemeral=True)

    @commands.hybrid_command(name="votes")
    @commands.guild_only()
    async def votes(self, ctx: commands.Context) -> None:
        """See who you voted for."""
        if await self._require_setup(ctx) is None:
            return

        async with get_session() as session:
            user_votes = await service.get_user_votes(session, ctx.guild.id, ctx.author.id)

        if not user_votes:
            await ctx.send("You haven't voted yet.", ephemeral=True)
        elif len(user_votes) == 1:
            await ctx.send(f"You voted for <@{user_votes[0].candidate_id}>.", ephemeral=True)
        else:
            mentions = ", ".join(f"<@{v.candidate_id}>" for v in user_votes)
            await ctx.send(f"You voted for: {mentions}", ephemeral=True)

    @commands.hybrid_command(name="votals")
    @commands.guild_only()
    @app_commands.describe(flag="Use -f for full details (shows who voted for whom)")
    async def votals(self, ctx: commands.Context, flag: str | None = None) -> None:
        """See the current vote standings."""
        if await self._require_setup(ctx) is None:
            return

        full_mode = flag is not None and "-f" in flag

        async with get_session() as session:
            user_votes = await service.get_user_votes(session, ctx.guild.id, ctx.author.id)

            if full_mode:
                detailed = await service.get_votals_detailed(session, ctx.guild.id)

                if not detailed:
                    await ctx.send("No votes yet!")
                    return

                lines = []
                for candidate_id, voter_ids in detailed:
                    member = ctx.guild.get_member(candidate_id)
                    name = member.name if member else f"<@{candidate_id}>"
                    voter_names = []
                    for vid in voter_ids:
                        voter = ctx.guild.get_member(vid)
                        voter_names.append(voter.name if voter else f"<@{vid}>")
                    count = len(voter_ids)
                    lines.append(f"**{name}**: {count} vote{'s' if count != 1 else ''} ({', '.join(voter_names)})")
            else:
                votals_data = await service.get_votals(session, ctx.guild.id)

                if not votals_data:
                    await ctx.send("No votes yet!")
                    return

                lines = []
                for candidate_id, count in votals_data:
                    member = ctx.guild.get_member(candidate_id)
                    name = member.name if member else f"<@{candidate_id}>"
                    lines.append(f"**{name}**: {count} vote{'s' if count != 1 else ''}")

        embed = discord.Embed(
            title="Vote Standings",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )

        # Footer with invoker's own votes
        if user_votes:
            vote_mentions = []
            for v in user_votes:
                m = ctx.guild.get_member(v.candidate_id)
                vote_mentions.append(m.name if m else str(v.candidate_id))
            embed.set_footer(text=f"Your votes: {', '.join(vote_mentions)}")
        else:
            embed.set_footer(text="You haven't voted yet.")

        await ctx.send(embed=embed)

    # =========================================================================
    # Interviewee Commands
    # =========================================================================

    @commands.hybrid_command(name="preview")
    @commands.guild_only()
    @is_interviewee()
    async def preview(self, ctx: commands.Context) -> None:
        """Preview your answered questions before posting."""
        async with get_session() as session:
            interview = await service.get_current_interview(session, ctx.guild.id)
            if interview is None:
                await ctx.send("No interview is currently active.", ephemeral=True)
                return

            questions = await service.get_questions(session, interview.id, QuestionFilter.ANSWERED_UNPOSTED)

        if not questions:
            await ctx.send("No answered questions ready to post.", ephemeral=True)
            return

        # Convert to embed data
        interviewee = ctx.guild.get_member(interview.interviewee_id)
        interviewee_data = IntervieweeData(
            name=interview.interviewee_name,
            color=interviewee.color.value if interviewee else 0x5865F2,  # Discord blurple default
            avatar_url=interviewee.display_avatar.url if interviewee else "",
        )
        question_data = [
            QuestionData(
                question_number=q.question_number,
                asker_name=q.asker_name,
                asker_avatar_url=self._get_member_avatar(ctx.guild, q.asker_id),
                question_text=q.question_text,
                answer_text=q.answer_text or "",
                jump_url=q.jump_url,
            )
            for q in questions
        ]

        result = generate_answer_embeds(
            interviewee_data,
            question_data,
            prior_answered=0,
            total_asked=len(questions),
        )

        await ctx.send(f"Preview ({len(questions)} questions):", ephemeral=True)
        for embed_group in result.embed_groups:
            await ctx.send(embeds=embed_group, ephemeral=True)

    @commands.hybrid_command(name="answer")
    @commands.guild_only()
    @is_interviewee()
    async def answer(self, ctx: commands.Context) -> None:
        """Post your answered questions to the answer channel."""
        async with get_session() as session:
            interview = await service.get_current_interview(session, ctx.guild.id)
            server = await service.get_server(session, ctx.guild.id)

            if interview is None or server is None:
                await ctx.send("No interview is currently active.", ephemeral=True)
                return

            if server.answer_channel_id is None:
                await ctx.send(
                    "No answer channel configured. Ask a manager to set one.",
                    ephemeral=True,
                )
                return

            answer_channel = ctx.guild.get_channel(server.answer_channel_id)
            if answer_channel is None:
                await ctx.send("Answer channel not found.", ephemeral=True)
                return

            questions = await service.get_questions(session, interview.id, QuestionFilter.ANSWERED_UNPOSTED)

            if not questions:
                await ctx.send("No answered questions ready to post.", ephemeral=True)
                return

            # Generate embeds
            interviewee = ctx.guild.get_member(interview.interviewee_id)
            interviewee_data = IntervieweeData(
                name=interview.interviewee_name,
                color=interviewee.color.value if interviewee else 0x5865F2,
                avatar_url=interviewee.display_avatar.url if interviewee else "",
            )
            question_data = [
                QuestionData(
                    question_number=q.question_number,
                    asker_name=q.asker_name,
                    asker_avatar_url=self._get_member_avatar(ctx.guild, q.asker_id),
                    question_text=q.question_text,
                    answer_text=q.answer_text or "",
                    jump_url=q.jump_url,
                )
                for q in questions
            ]

            # Count previously posted
            posted_count = await service.count_questions(session, interview.id, answered_only=True) - len(questions)

            result = generate_answer_embeds(
                interviewee_data,
                question_data,
                prior_answered=posted_count,
                total_asked=await service.count_questions(session, interview.id),
            )

            # Post embed groups (each group sent as single message for gallery support)
            question_ids = [q.id for q in questions]
            for embed_group in result.embed_groups:
                msg = await answer_channel.send(embeds=embed_group)
                # Mark all questions in this batch as posted with the last message ID
                await service.mark_posted(session, question_ids, msg.id)

            await session.commit()

            await ctx.send(
                f"Posted {len(questions)} answers to {answer_channel.mention}!",
                ephemeral=True,
            )

    # =========================================================================
    # Management Commands (iv group)
    # =========================================================================

    @commands.hybrid_group(name="iv", fallback="help")
    @commands.guild_only()
    async def iv(self, ctx: commands.Context) -> None:
        """Interview management commands."""
        embed = discord.Embed(
            title="Interview Commands",
            description=(
                "**Setup:**\n"
                "`iv setup #answer #backstage` - Initial server setup (required)\n\n"
                "**Management:**\n"
                "`iv start @user` - Start interview with user\n"
                "`iv end` - End current interview\n"
                "`iv settings` - View current settings\n"
                "`iv stats [@member]` - View interview statistics\n"
                "`iv channel <answer|backstage|voting> #channel` - Update channels\n"
                "`iv setmanager @role` - Set manager role\n"
                "`iv setaudience @role` - Set audience/stage role\n"
                "`iv stage <grant|revoke|list|clear>` - Manage stage access\n"
                "`iv reinterview <on|off|set N>` - Configure reinterviews\n"
                "`iv enable` / `iv disable` - Toggle interviews\n"
            ),
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @iv.command(name="setup")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(
        answer_channel="Channel where interview answers are posted",
        backstage_channel="Channel where interviewee sees/answers questions",
    )
    async def iv_setup(
        self,
        ctx: commands.Context,
        answer_channel: Annotated[discord.TextChannel, TextChannelConverter],
        backstage_channel: Annotated[discord.TextChannel, TextChannelConverter],
    ) -> None:
        """Set up the interview system for this server (admin only)."""
        async with get_session() as session:
            server, created = await service.get_or_create_server(session, ctx.guild.id, ctx.guild.name)

            await service.update_server_config(
                session,
                ctx.guild.id,
                answer_channel_id=answer_channel.id,
                backstage_channel_id=backstage_channel.id,
                active=True,
            )
            await session.commit()

        action = "configured" if created else "updated"
        embed = discord.Embed(
            title=f"Interview System {action.title()}",
            description=(
                f"**Answer Channel:** {answer_channel.mention}\n"
                f"**Backstage Channel:** {backstage_channel.mention}\n\n"
                f"Use `{ctx.prefix}iv setmanager @role` to set a manager role, "
                f"or admins can manage interviews directly."
            ),
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @iv.command(name="start")
    @is_manager()
    @app_commands.describe(interviewee="The member to interview")
    async def iv_start(self, ctx: commands.Context, interviewee: discord.Member) -> None:
        """Start a new interview with the specified member."""
        if interviewee.bot:
            await ctx.send("Can't interview a bot!", ephemeral=True)
            return

        async with get_session() as session:
            # Check server is set up
            server = await service.get_server(session, ctx.guild.id)
            if server is None or server.answer_channel_id is None or server.backstage_channel_id is None:
                await ctx.send(
                    f"Interview system not set up. Use `{ctx.prefix}iv setup #answer #backstage` first.",
                    ephemeral=True,
                )
                return

            if not server.active:
                await ctx.send(
                    f"Interviews are disabled. Use `{ctx.prefix}iv enable` first.",
                    ephemeral=True,
                )
                return

            # Check if opted out
            if await service.is_opted_out(session, ctx.guild.id, interviewee.id):
                await ctx.send(
                    f"{interviewee.name} has opted out of interviews.",
                    ephemeral=True,
                )
                return

            # Clear votes from previous interview
            await service.clear_votes(session, ctx.guild.id)

            # Start interview
            interview = await service.start_interview(
                session,
                server_id=ctx.guild.id,
                interviewee_id=interviewee.id,
                interviewee_name=interviewee.name,
                op_channel_id=ctx.channel.id,
                op_message_id=ctx.message.id if ctx.message else None,
            )

            # Add default question if configured
            if server.default_question:
                await service.add_question(
                    session,
                    interview_id=interview.id,
                    asker_id=self.bot.user.id,
                    asker_name=self.bot.user.name,
                    question_text=server.default_question,
                    source_guild_id=ctx.guild.id,
                    source_channel_id=ctx.channel.id,
                    source_message_id=ctx.message.id if ctx.message else 0,
                )

            await session.commit()

        # Clear audience role (outside DB session — Discord API calls)
        if server.audience_role_id is not None:
            role = ctx.guild.get_role(server.audience_role_id)
            if role is not None:
                for member in role.members:
                    try:
                        await member.remove_roles(role, reason="New interview started")
                    except discord.HTTPException:
                        logger.warning(f"Failed to remove audience role from {member}")

        # Broadcast to WebSocket clients
        broadcast_event(
            ctx.guild.id,
            "interview_started",
            {
                "interview_id": interview.id,
                "interview_number": interview.interview_number,
                "interviewee_id": str(interviewee.id),
                "interviewee_name": interviewee.name,
            },
        )

        embed = discord.Embed(
            title=f"Interview #{interview.interview_number}: {interviewee.name}",
            description=f"Use `{ctx.prefix}ask <question>` to submit questions!",
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=interviewee.display_avatar.url)
        await ctx.send(embed=embed)

    @iv.command(name="end")
    @is_manager()
    async def iv_end(self, ctx: commands.Context) -> None:
        """End the current interview."""
        async with get_session() as session:
            interview = await service.get_current_interview(session, ctx.guild.id)
            if interview is None:
                await ctx.send("No interview is currently active.", ephemeral=True)
                return

            await service.end_interview(session, interview.id)
            await session.commit()

            # Broadcast to WebSocket clients
            broadcast_event(
                ctx.guild.id,
                "interview_ended",
                {
                    "interview_id": interview.id,
                },
            )

            await ctx.send(f"Interview with {interview.interviewee_name} has ended.")

    @iv.command(name="settings")
    @is_manager()
    async def iv_settings(self, ctx: commands.Context) -> None:
        """View current interview settings."""
        async with get_session() as session:
            server = await service.get_server(session, ctx.guild.id)
            interview = await service.get_current_interview(session, ctx.guild.id)

        if server is None:
            await ctx.send(
                f"Interview system not set up. Use `{ctx.prefix}iv setup #answer #backstage` first.",
                ephemeral=True,
            )
            return

        # Build settings display
        def channel_mention(cid: int | None) -> str:
            if cid is None:
                return "Not set"
            channel = ctx.guild.get_channel(cid)
            return channel.mention if channel else f"<#{cid}>"

        def role_mention(rid: int | None) -> str:
            if rid is None:
                return "Not set"
            role = ctx.guild.get_role(rid)
            return role.mention if role else f"<@&{rid}>"

        embed = discord.Embed(
            title="Interview Settings",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Status",
            value="Enabled" if server.active else "Disabled",
            inline=True,
        )
        embed.add_field(
            name="Current Interview",
            value=interview.interviewee_name if interview else "None",
            inline=True,
        )
        embed.add_field(
            name="Answer Channel",
            value=channel_mention(server.answer_channel_id),
            inline=True,
        )
        embed.add_field(
            name="Backstage Channel",
            value=channel_mention(server.backstage_channel_id),
            inline=True,
        )
        embed.add_field(
            name="Manager Role",
            value=role_mention(server.manager_role_id),
            inline=True,
        )
        embed.add_field(
            name="Voting Channel",
            value=channel_mention(server.voting_channel_id) if server.voting_channel_id else "Any",
            inline=True,
        )
        embed.add_field(
            name="Audience Role",
            value=role_mention(server.audience_role_id),
            inline=True,
        )

        # Reinterview setting
        if not server.reinterviews_allowed:
            reinterview_str = "Disabled"
        elif server.reinterview_days > 0:
            reinterview_str = f"{server.reinterview_days} day cooldown"
        else:
            reinterview_str = "No limit"
        embed.add_field(
            name="Reinterviews",
            value=reinterview_str,
            inline=True,
        )

        await ctx.send(embed=embed)

    @iv.command(name="channel")
    @is_manager()
    @app_commands.describe(
        channel_type="Type of channel (answer or backstage)",
        channel="The channel to set",
    )
    @app_commands.choices(
        channel_type=[
            app_commands.Choice(name="answer", value="answer"),
            app_commands.Choice(name="backstage", value="backstage"),
            app_commands.Choice(name="voting", value="voting"),
        ]
    )
    async def iv_channel(
        self,
        ctx: commands.Context,
        channel_type: str,
        channel: Annotated[discord.TextChannel, TextChannelConverter],
    ) -> None:
        """Set the answer, backstage, or voting channel."""
        async with get_session() as session:
            server, _ = await service.get_or_create_server(session, ctx.guild.id, ctx.guild.name)

            if channel_type == "answer":
                await service.update_server_config(session, ctx.guild.id, answer_channel_id=channel.id)
            elif channel_type == "backstage":
                await service.update_server_config(session, ctx.guild.id, backstage_channel_id=channel.id)
            elif channel_type == "voting":
                await service.update_server_config(session, ctx.guild.id, voting_channel_id=channel.id)
            else:
                await ctx.send(
                    "Invalid channel type. Use `answer`, `backstage`, or `voting`.",
                    ephemeral=True,
                )
                return

            await session.commit()

        await ctx.send(f"Set {channel_type} channel to {channel.mention}.")

    @iv.command(name="setmanager")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(role="The role that can manage interviews")
    async def iv_setmanager(self, ctx: commands.Context, role: discord.Role) -> None:
        """Set the manager role (admin only)."""
        async with get_session() as session:
            await service.get_or_create_server(session, ctx.guild.id, ctx.guild.name)
            await service.update_server_config(session, ctx.guild.id, manager_role_id=role.id)
            await session.commit()

        await ctx.send(f"Manager role set to {role.mention}.")

    @iv.command(name="setaudience")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(role="The role for interview stage/audience access")
    async def iv_setaudience(self, ctx: commands.Context, role: discord.Role) -> None:
        """Set the audience role (admin only)."""
        async with get_session() as session:
            await service.get_or_create_server(session, ctx.guild.id, ctx.guild.name)
            await service.update_server_config(session, ctx.guild.id, audience_role_id=role.id)
            await session.commit()

        await ctx.send(f"Audience role set to {role.mention}.")

    @iv.group(name="reinterview", fallback="show")
    @is_manager()
    async def iv_reinterview(self, ctx: commands.Context) -> None:
        """View reinterview settings."""
        async with get_session() as session:
            server = await service.get_server(session, ctx.guild.id)

        if server is None:
            await ctx.send(
                f"Interview system not set up. Use `{ctx.prefix}iv setup #answer #backstage` first.",
                ephemeral=True,
            )
            return

        if not server.reinterviews_allowed:
            status = "Reinterviews are **disabled**."
        elif server.reinterview_days > 0:
            status = f"Reinterviews allowed after **{server.reinterview_days}** day cooldown."
        else:
            status = "Reinterviews allowed with **no limit**."

        await ctx.send(status, ephemeral=True)

    @iv_reinterview.command(name="on")
    @is_manager()
    async def iv_reinterview_on(self, ctx: commands.Context) -> None:
        """Allow reinterviews."""
        async with get_session() as session:
            await service.get_or_create_server(session, ctx.guild.id, ctx.guild.name)
            await service.update_server_config(session, ctx.guild.id, reinterviews_allowed=True)
            await session.commit()

        await ctx.send("Reinterviews enabled.")

    @iv_reinterview.command(name="off")
    @is_manager()
    async def iv_reinterview_off(self, ctx: commands.Context) -> None:
        """Disallow reinterviews."""
        async with get_session() as session:
            await service.get_or_create_server(session, ctx.guild.id, ctx.guild.name)
            await service.update_server_config(session, ctx.guild.id, reinterviews_allowed=False)
            await session.commit()

        await ctx.send("Reinterviews disabled.")

    @iv_reinterview.command(name="set")
    @is_manager()
    @app_commands.describe(days="Cooldown in days before someone can be reinterviewed (0 = no limit)")
    async def iv_reinterview_set(self, ctx: commands.Context, days: int) -> None:
        """Set reinterview cooldown in days."""
        if days < 0:
            await ctx.send("Days must be 0 or greater.", ephemeral=True)
            return

        async with get_session() as session:
            await service.get_or_create_server(session, ctx.guild.id, ctx.guild.name)
            await service.update_server_config(session, ctx.guild.id, reinterview_days=days)
            await session.commit()

        if days == 0:
            await ctx.send("Reinterview cooldown removed (no limit).")
        else:
            await ctx.send(f"Reinterview cooldown set to {days} day{'s' if days != 1 else ''}.")

    @iv.command(name="stats")
    @interviews_enabled()
    @app_commands.describe(member="View stats for a specific member (optional)")
    async def iv_stats(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        """View interview statistics."""
        async with get_session() as session:
            if member is not None:
                # Member-specific stats
                interviews = await service.get_member_interviews(session, ctx.guild.id, member.id)
                question_count = await service.get_member_question_count(session, ctx.guild.id, member.id)

                embed = discord.Embed(
                    title=f"Interview Stats: {member.name}",
                    color=member.color if member.color.value else discord.Color.blue(),
                )
                embed.set_thumbnail(url=member.display_avatar.url)

                if interviews:
                    interview_lines = []
                    for iv_record in interviews:
                        q_count = await service.count_questions(session, iv_record.id)
                        a_count = await service.count_questions(session, iv_record.id, answered_only=True)
                        status = "ongoing" if iv_record.is_current else f"<t:{int(iv_record.started_at.timestamp())}:d>"
                        interview_lines.append(
                            f"**#{iv_record.interview_number}** ({status}) — {q_count} Q / {a_count} A"
                        )
                    embed.add_field(
                        name=f"Interviewed ({len(interviews)} time{'s' if len(interviews) != 1 else ''})",
                        value="\n".join(interview_lines),
                        inline=False,
                    )
                else:
                    embed.add_field(name="Interviewed", value="Never", inline=False)

                embed.add_field(
                    name="Questions Asked",
                    value=str(question_count),
                    inline=True,
                )
            else:
                # Server-wide stats
                stats = await service.get_server_stats(session, ctx.guild.id)
                interview = await service.get_current_interview(session, ctx.guild.id)
                top_askers = await service.get_top_askers(session, ctx.guild.id, limit=5)

                embed = discord.Embed(
                    title="Interview Statistics",
                    color=discord.Color.blue(),
                )

                if interview is not None:
                    q_count = await service.count_questions(session, interview.id)
                    a_count = await service.count_questions(session, interview.id, answered_only=True)
                    embed.add_field(
                        name="Current Interview",
                        value=f"**{interview.interviewee_name}** (#{interview.interview_number}) — {q_count} Q / {a_count} A",
                        inline=False,
                    )

                embed.add_field(name="Total Interviews", value=str(stats["total_interviews"]), inline=True)
                embed.add_field(name="Total Questions", value=str(stats["total_questions"]), inline=True)
                embed.add_field(
                    name="Avg Questions/Interview",
                    value=f"{stats['avg_questions_per_interview']:.1f}",
                    inline=True,
                )

                if top_askers:
                    asker_lines = [f"**{name}**: {count}" for _, name, count in top_askers]
                    embed.add_field(
                        name="Top Askers",
                        value="\n".join(asker_lines),
                        inline=False,
                    )

                # List recent interviews
                recent = await service.get_interview_archive(session, ctx.guild.id, limit=10)
                if recent:
                    archive_lines = []
                    for iv_record in recent:
                        if iv_record.is_current:
                            continue
                        date_str = f"<t:{int(iv_record.started_at.timestamp())}:d>"
                        archive_lines.append(
                            f"#{iv_record.interview_number} **{iv_record.interviewee_name}** ({date_str})"
                        )
                    if archive_lines:
                        embed.add_field(
                            name="Recent Interviews",
                            value="\n".join(archive_lines),
                            inline=False,
                        )

        await ctx.send(embed=embed)

    @iv.command(name="enable")
    @is_manager()
    async def iv_enable(self, ctx: commands.Context) -> None:
        """Enable the interview system."""
        async with get_session() as session:
            await service.get_or_create_server(session, ctx.guild.id, ctx.guild.name)
            await service.update_server_config(session, ctx.guild.id, active=True)
            await session.commit()

        await ctx.send("Interview system enabled.")

    @iv.command(name="disable")
    @is_manager()
    async def iv_disable(self, ctx: commands.Context) -> None:
        """Disable the interview system."""
        async with get_session() as session:
            await service.update_server_config(session, ctx.guild.id, active=False)
            await session.commit()

        await ctx.send("Interview system disabled.")

    # =========================================================================
    # Stage Commands (audience role management)
    # =========================================================================

    @iv.group(name="stage", fallback="list")
    @is_interviewee_or_manager()
    async def iv_stage(self, ctx: commands.Context) -> None:
        """List members with the audience/stage role."""
        server = await self._require_setup(ctx)
        if server is None:
            return

        if server.audience_role_id is None:
            await ctx.send(
                f"No audience role configured. Use `{ctx.prefix}iv setaudience @role` first.",
                ephemeral=True,
            )
            return

        role = ctx.guild.get_role(server.audience_role_id)
        if role is None:
            await ctx.send("Audience role not found in this server.", ephemeral=True)
            return

        if not role.members:
            await ctx.send(f"No members currently have {role.mention}.", ephemeral=True)
            return

        lines = [m.name for m in role.members]
        embed = discord.Embed(
            title=f"Stage Members ({len(lines)})",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @iv_stage.command(name="grant")
    @is_interviewee_or_manager()
    @app_commands.describe(
        member1="Member to grant stage access",
        member2="Additional member (optional)",
        member3="Additional member (optional)",
        member4="Additional member (optional)",
        member5="Additional member (optional)",
    )
    async def iv_stage_grant(
        self,
        ctx: commands.Context,
        member1: discord.Member,
        member2: discord.Member | None = None,
        member3: discord.Member | None = None,
        member4: discord.Member | None = None,
        member5: discord.Member | None = None,
    ) -> None:
        """Grant audience/stage role to members."""
        server = await self._require_setup(ctx)
        if server is None:
            return

        if server.audience_role_id is None:
            await ctx.send(
                f"No audience role configured. Use `{ctx.prefix}iv setaudience @role` first.",
                ephemeral=True,
            )
            return

        role = ctx.guild.get_role(server.audience_role_id)
        if role is None:
            await ctx.send("Audience role not found in this server.", ephemeral=True)
            return

        members = [m for m in [member1, member2, member3, member4, member5] if m is not None]
        granted = []
        for member in members:
            if role not in member.roles:
                await member.add_roles(role, reason="Interview stage access granted")
                granted.append(member.name)

        if granted:
            await ctx.send(f"Granted stage access to: {', '.join(granted)}")
        else:
            await ctx.send("All specified members already have stage access.", ephemeral=True)

    @iv_stage.command(name="revoke")
    @is_interviewee_or_manager()
    @app_commands.describe(
        member1="Member to revoke stage access from",
        member2="Additional member (optional)",
        member3="Additional member (optional)",
        member4="Additional member (optional)",
        member5="Additional member (optional)",
    )
    async def iv_stage_revoke(
        self,
        ctx: commands.Context,
        member1: discord.Member,
        member2: discord.Member | None = None,
        member3: discord.Member | None = None,
        member4: discord.Member | None = None,
        member5: discord.Member | None = None,
    ) -> None:
        """Revoke audience/stage role from members."""
        server = await self._require_setup(ctx)
        if server is None:
            return

        if server.audience_role_id is None:
            await ctx.send(
                f"No audience role configured. Use `{ctx.prefix}iv setaudience @role` first.",
                ephemeral=True,
            )
            return

        role = ctx.guild.get_role(server.audience_role_id)
        if role is None:
            await ctx.send("Audience role not found in this server.", ephemeral=True)
            return

        members = [m for m in [member1, member2, member3, member4, member5] if m is not None]
        revoked = []
        for member in members:
            if role in member.roles:
                await member.remove_roles(role, reason="Interview stage access revoked")
                revoked.append(member.name)

        if revoked:
            await ctx.send(f"Revoked stage access from: {', '.join(revoked)}")
        else:
            await ctx.send("None of the specified members had stage access.", ephemeral=True)

    @iv_stage.command(name="mgrant", with_app_command=False)
    @is_interviewee_or_manager()
    async def iv_stage_mgrant(
        self,
        ctx: commands.Context,
        members: commands.Greedy[discord.Member],
    ) -> None:
        """Grant stage access to many members at once (prefix only)."""
        if not members:
            await ctx.send("Mention one or more members to grant stage access to.", ephemeral=True)
            return

        server = await self._require_setup(ctx)
        if server is None:
            return

        if server.audience_role_id is None:
            await ctx.send(
                f"No audience role configured. Use `{ctx.prefix}iv setaudience @role` first.",
                ephemeral=True,
            )
            return

        role = ctx.guild.get_role(server.audience_role_id)
        if role is None:
            await ctx.send("Audience role not found in this server.", ephemeral=True)
            return

        granted = []
        for member in members:
            if role not in member.roles:
                await member.add_roles(role, reason="Interview stage access granted")
                granted.append(member.name)

        if granted:
            await ctx.send(
                f"Granted stage access to {len(granted)} member{'s' if len(granted) != 1 else ''}: {', '.join(granted)}"
            )
        else:
            await ctx.send("All specified members already have stage access.", ephemeral=True)

    @iv_stage.command(name="mrevoke", with_app_command=False)
    @is_interviewee_or_manager()
    async def iv_stage_mrevoke(
        self,
        ctx: commands.Context,
        members: commands.Greedy[discord.Member],
    ) -> None:
        """Revoke stage access from many members at once (prefix only)."""
        if not members:
            await ctx.send("Mention one or more members to revoke stage access from.", ephemeral=True)
            return

        server = await self._require_setup(ctx)
        if server is None:
            return

        if server.audience_role_id is None:
            await ctx.send(
                f"No audience role configured. Use `{ctx.prefix}iv setaudience @role` first.",
                ephemeral=True,
            )
            return

        role = ctx.guild.get_role(server.audience_role_id)
        if role is None:
            await ctx.send("Audience role not found in this server.", ephemeral=True)
            return

        revoked = []
        for member in members:
            if role in member.roles:
                await member.remove_roles(role, reason="Interview stage access revoked")
                revoked.append(member.name)

        if revoked:
            await ctx.send(
                f"Revoked stage access from {len(revoked)} member{'s' if len(revoked) != 1 else ''}: {', '.join(revoked)}"
            )
        else:
            await ctx.send("None of the specified members had stage access.", ephemeral=True)

    @iv_stage.command(name="clear")
    @is_interviewee_or_manager()
    async def iv_stage_clear(self, ctx: commands.Context) -> None:
        """Remove audience/stage role from all members."""
        server = await self._require_setup(ctx)
        if server is None:
            return

        if server.audience_role_id is None:
            await ctx.send(
                f"No audience role configured. Use `{ctx.prefix}iv setaudience @role` first.",
                ephemeral=True,
            )
            return

        role = ctx.guild.get_role(server.audience_role_id)
        if role is None:
            await ctx.send("Audience role not found in this server.", ephemeral=True)
            return

        count = 0
        for member in role.members:
            await member.remove_roles(role, reason="Interview stage cleared")
            count += 1

        if count > 0:
            await ctx.send(f"Removed stage access from {count} member{'s' if count != 1 else ''}.")
        else:
            await ctx.send("No members had stage access.", ephemeral=True)

    # =========================================================================
    # Opt-out Commands
    # =========================================================================

    @commands.hybrid_group(name="opt", fallback="help")
    @commands.guild_only()
    async def opt(self, ctx: commands.Context) -> None:
        """Opt in/out of being interviewed."""
        await ctx.send(
            "Use `opt out` to opt out of interviews, `opt in` to opt back in.",
            ephemeral=True,
        )

    @opt.command(name="out")
    async def opt_out(self, ctx: commands.Context) -> None:
        """Opt out of being interviewed."""
        async with get_session() as session:
            await service.get_or_create_server(session, ctx.guild.id, ctx.guild.name)
            await service.opt_out(session, ctx.guild.id, ctx.author.id)
            await session.commit()

        await ctx.send("You have opted out of interviews.", ephemeral=True)

    @opt.command(name="in")
    async def opt_in(self, ctx: commands.Context) -> None:
        """Opt back in to interviews."""
        async with get_session() as session:
            removed = await service.opt_in(session, ctx.guild.id, ctx.author.id)
            await session.commit()

        if removed:
            await ctx.send("You have opted back in to interviews.", ephemeral=True)
        else:
            await ctx.send("You weren't opted out.", ephemeral=True)

    @opt.command(name="list")
    async def opt_list(self, ctx: commands.Context) -> None:
        """List users who have opted out."""
        async with get_session() as session:
            opt_outs = await service.get_opt_outs(session, ctx.guild.id)

        if not opt_outs:
            await ctx.send("No users have opted out.", ephemeral=True)
            return

        lines = []
        for user_id in opt_outs:
            member = ctx.guild.get_member(user_id)
            name = member.name if member else f"<@{user_id}>"
            lines.append(name)

        embed = discord.Embed(
            title="Opted-Out Users",
            description="\n".join(lines),
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed, ephemeral=True)

    # =========================================================================
    # Dev Commands (owner only)
    # =========================================================================

    @iv.command(name="reset")
    @commands.is_owner()
    async def iv_reset(self, ctx: commands.Context, confirm: str | None = None) -> None:
        """[DEV] Clear all interview data for this server.

        Requires confirmation: `iv reset CONFIRM`
        """
        if confirm != "CONFIRM":
            await ctx.send(
                f"**WARNING:** This will delete ALL interview data for this server.\n"
                f"To confirm, run: `{ctx.prefix}iv reset CONFIRM`",
                ephemeral=True,
            )
            return

        async with get_session() as session:
            # Get server to check it exists
            server = await service.get_server(session, ctx.guild.id)
            if server is None:
                await ctx.send("No interview data for this server.", ephemeral=True)
                return

            # Import text for raw SQL
            from sqlalchemy import text

            # Delete all related data for this server
            await session.execute(
                text("DELETE FROM interview_votes WHERE server_id = :sid"),
                {"sid": ctx.guild.id},
            )
            await session.execute(
                text(
                    "DELETE FROM interview_questions WHERE interview_id IN "
                    "(SELECT id FROM interviews WHERE server_id = :sid)"
                ),
                {"sid": ctx.guild.id},
            )
            await session.execute(
                text("DELETE FROM interviews WHERE server_id = :sid"),
                {"sid": ctx.guild.id},
            )
            await session.execute(
                text("DELETE FROM interview_opt_outs WHERE server_id = :sid"),
                {"sid": ctx.guild.id},
            )
            await session.execute(
                text("DELETE FROM interview_servers WHERE id = :sid"),
                {"sid": ctx.guild.id},
            )
            await session.commit()

        await ctx.send("All interview data for this server has been deleted.")

    @iv.command(name="backfill_names")
    @commands.is_owner()
    async def iv_backfill_names(self, ctx: commands.Context) -> None:
        """[DEV] Backfill asker_name and interviewee_name with current usernames.

        Resolves stored user IDs to their current Discord usernames (.name),
        replacing old display/guild names. Falls back to fetch_user for users
        not in the bot's cache. Reports how many records were updated.
        """
        await ctx.send("Backfilling names, this may take a moment...")

        async with get_session() as session:
            questions = (await session.execute(select(Question))).scalars().all()
            interviews = (await session.execute(select(InterviewModel))).scalars().all()

        # Collect all unique user IDs to resolve
        user_ids: set[int] = set()
        for q in questions:
            user_ids.add(q.asker_id)
        for iv in interviews:
            user_ids.add(iv.interviewee_id)

        # Resolve IDs to usernames: cache first, then REST
        names: dict[int, str] = {}
        failed: list[int] = []
        for uid in user_ids:
            user = self.bot.get_user(uid)
            if user is None:
                try:
                    user = await self.bot.fetch_user(uid)
                except discord.NotFound:
                    failed.append(uid)
                    continue
            names[uid] = user.name

        # Apply updates
        q_updated = 0
        iv_updated = 0
        async with get_session() as session:
            for q in await session.execute(select(Question)):
                q = q[0]
                new_name = names.get(q.asker_id)
                if new_name and q.asker_name != new_name:
                    q.asker_name = new_name
                    q_updated += 1
            for interview in await session.execute(select(InterviewModel)):
                interview = interview[0]
                new_name = names.get(interview.interviewee_id)
                if new_name and interview.interviewee_name != new_name:
                    interview.interviewee_name = new_name
                    iv_updated += 1
            await session.commit()

        reply = f"Done. Updated {q_updated} question(s) and {iv_updated} interview(s)."
        if failed:
            reply += f"\nCould not resolve {len(failed)} user ID(s): {', '.join(str(i) for i in failed)}"
        await ctx.send(reply)


async def setup(bot: Bot) -> None:
    """Load the Interview cog."""
    await bot.add_cog(Interview(bot))
