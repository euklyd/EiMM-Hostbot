"""Utilities for resolving member references from strings."""

import re

import discord


async def resolve_members(guild: discord.Guild, members_str: str) -> list[discord.Member]:
    """
    Parse a string into a list of members using mentions or IDs.

    Supports:
    - Mentions: <@123456789> or <@!123456789>
    - Raw user IDs: 123456789012345678

    Args:
        guild: The guild to resolve members from
        members_str: String containing mentions and/or IDs

    Returns:
        List of resolved discord.Member objects (unresolved IDs are skipped)
    """
    # Match mentions <@123> or <@!123> and raw IDs (17-19 digits)
    pattern = r"<@!?(\d+)>|(\d{17,19})"

    resolved = []
    seen_ids: set[int] = set()

    for match in re.finditer(pattern, members_str):
        user_id = int(match.group(1) or match.group(2))
        # Avoid duplicates
        if user_id in seen_ids:
            continue
        seen_ids.add(user_id)

        member = guild.get_member(user_id)
        if member:
            resolved.append(member)

    return resolved
