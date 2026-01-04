#!/usr/bin/env python3
"""Seed the database with test data for manual testing.

Usage:
    # With default local connection (localhost:5432)
    uv run python scripts/seed_test_data.py

    # With custom database URL
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db uv run python scripts/seed_test_data.py

    # Clear existing data first
    uv run python scripts/seed_test_data.py --clear
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from cogs.interview import service
from cogs.interview.models import Interview, InterviewServer
from db import init_db
from db.session import get_session

# Test Discord IDs (these are fake but realistic-looking)
TEST_SERVER_ID = 123456789012345678
TEST_SERVER_NAME = "Test Interview Server"

# Test users
USERS = {
    "host": {"id": 100000000000000001, "name": "InterviewHost"},
    "interviewee": {"id": 100000000000000002, "name": "CurrentInterviewee"},
    "asker1": {"id": 100000000000000003, "name": "QuestionAsker1"},
    "asker2": {"id": 100000000000000004, "name": "QuestionAsker2"},
    "asker3": {"id": 100000000000000005, "name": "QuestionAsker3"},
    "voter1": {"id": 100000000000000006, "name": "Voter1"},
    "voter2": {"id": 100000000000000007, "name": "Voter2"},
    "opted_out": {"id": 100000000000000008, "name": "OptedOutUser"},
    "candidate1": {"id": 100000000000000009, "name": "VoteCandidate1"},
    "candidate2": {"id": 100000000000000010, "name": "VoteCandidate2"},
}

# Test channels
CHANNELS = {
    "questions": 200000000000000001,
    "answers": 200000000000000002,
    "backstage": 200000000000000003,
    "voting": 200000000000000004,
}

# Test roles
ROLES = {
    "manager": 300000000000000001,
    "audience": 300000000000000002,
}


async def clear_interview_data() -> None:
    """Clear all interview-related data from the database."""
    print("Clearing existing interview data...")
    async with get_session() as session:
        # Delete in order to respect foreign keys
        await session.execute(text("DELETE FROM interview_votes"))
        await session.execute(text("DELETE FROM interview_questions"))
        await session.execute(text("DELETE FROM interviews"))
        await session.execute(text("DELETE FROM interview_opt_outs"))
        await session.execute(text("DELETE FROM interview_servers"))
        await session.commit()
    print("  Cleared all interview tables")


async def seed_server() -> InterviewServer:
    """Create the test server with configuration."""
    print("Creating test server...")
    async with get_session() as session:
        server, created = await service.get_or_create_server(session, TEST_SERVER_ID, TEST_SERVER_NAME)
        if created:
            print(f"  Created server: {TEST_SERVER_NAME}")
        else:
            print(f"  Server already exists: {TEST_SERVER_NAME}")

        # Configure channels and roles
        await service.update_server_config(
            session,
            TEST_SERVER_ID,
            answer_channel_id=CHANNELS["answers"],
            backstage_channel_id=CHANNELS["backstage"],
            voting_channel_id=CHANNELS["voting"],
            manager_role_id=ROLES["manager"],
            audience_role_id=ROLES["audience"],
            active=True,
        )
        await session.commit()
        print("  Configured channels and roles")

        # Refresh to get updated values
        server = await service.get_server(session, TEST_SERVER_ID)
        return server


async def seed_opt_outs() -> None:
    """Create opt-out entries."""
    print("Creating opt-outs...")
    async with get_session() as session:
        await service.opt_out(session, TEST_SERVER_ID, USERS["opted_out"]["id"])
        await session.commit()
    print(f"  {USERS['opted_out']['name']} opted out")


async def seed_past_interview() -> Interview:
    """Create a completed past interview for history."""
    print("Creating past interview...")
    async with get_session() as session:
        # Start an interview that happened "last week"
        interview = await service.start_interview(
            session,
            server_id=TEST_SERVER_ID,
            interviewee_id=USERS["asker1"]["id"],  # Previous interviewee
            interviewee_name="PreviousInterviewee",
            op_channel_id=CHANNELS["questions"],
            op_message_id=400000000000000001,
        )

        # Add some questions
        q1 = await service.add_question(
            session,
            interview_id=interview.id,
            asker_id=USERS["asker2"]["id"],
            asker_name=USERS["asker2"]["name"],
            question_text="What's your favorite color?",
            source_guild_id=TEST_SERVER_ID,
            source_channel_id=CHANNELS["questions"],
            source_message_id=400000000000000002,
        )

        # Answer and post
        await service.answer_question(session, q1.id, "Blue, no wait, green!")
        await service.mark_posted(session, [q1.id], 400000000000000010)

        # End the interview
        await service.end_interview(session, interview.id)
        await session.commit()

    print(f"  Created past interview with {USERS['asker1']['name']} (ended)")
    return interview


async def seed_current_interview() -> Interview:
    """Create the current active interview with various question states."""
    print("Creating current interview...")
    async with get_session() as session:
        interview = await service.start_interview(
            session,
            server_id=TEST_SERVER_ID,
            interviewee_id=USERS["interviewee"]["id"],
            interviewee_name=USERS["interviewee"]["name"],
            op_channel_id=CHANNELS["questions"],
            op_message_id=500000000000000001,
        )
        await session.commit()
    print(f"  Started interview with {USERS['interviewee']['name']}")

    # Add questions in different states
    async with get_session() as session:
        # Questions that are answered and posted
        q1 = await service.add_question(
            session,
            interview_id=interview.id,
            asker_id=USERS["asker1"]["id"],
            asker_name=USERS["asker1"]["name"],
            question_text="What got you into Magic: The Gathering?",
            source_guild_id=TEST_SERVER_ID,
            source_channel_id=CHANNELS["questions"],
            source_message_id=500000000000000002,
        )
        await service.answer_question(
            session, q1.id, "I found my older brother's cards in the attic when I was 12. Been hooked ever since!"
        )
        await service.mark_posted(session, [q1.id], 500000000000000010)
        await session.commit()
    print("  Added Q1: answered + posted")

    async with get_session() as session:
        # Questions that are answered but not posted yet
        q2 = await service.add_question(
            session,
            interview_id=interview.id,
            asker_id=USERS["asker2"]["id"],
            asker_name=USERS["asker2"]["name"],
            question_text="What's your favorite format and why?",
            source_guild_id=TEST_SERVER_ID,
            source_channel_id=CHANNELS["questions"],
            source_message_id=500000000000000003,
        )
        await service.answer_question(
            session,
            q2.id,
            "Commander, because I love the social aspect and the crazy combos "
            "you can pull off with a 100-card singleton deck.",
        )
        await session.commit()
    print("  Added Q2: answered, not posted")

    async with get_session() as session:
        q3 = await service.add_question(
            session,
            interview_id=interview.id,
            asker_id=USERS["asker1"]["id"],
            asker_name=USERS["asker1"]["name"],
            question_text="Do you have any pets?",
            source_guild_id=TEST_SERVER_ID,
            source_channel_id=CHANNELS["questions"],
            source_message_id=500000000000000004,
        )
        await service.answer_question(session, q3.id, "Yes! A cat named Jace and a dog named Chandra.")
        await session.commit()
    print("  Added Q3: answered, not posted")

    async with get_session() as session:
        # Unanswered questions
        await service.add_question(
            session,
            interview_id=interview.id,
            asker_id=USERS["asker3"]["id"],
            asker_name=USERS["asker3"]["name"],
            question_text="What's your most memorable game of Magic?",
            source_guild_id=TEST_SERVER_ID,
            source_channel_id=CHANNELS["questions"],
            source_message_id=500000000000000005,
        )
        await session.commit()
    print("  Added Q4: unanswered")

    async with get_session() as session:
        await service.add_question(
            session,
            interview_id=interview.id,
            asker_id=USERS["asker2"]["id"],
            asker_name=USERS["asker2"]["name"],
            question_text="If you could have dinner with any Magic character, who would it be?",
            source_guild_id=TEST_SERVER_ID,
            source_channel_id=CHANNELS["questions"],
            source_message_id=500000000000000006,
        )
        await session.commit()
    print("  Added Q5: unanswered")

    async with get_session() as session:
        # A longer question to test wrapping
        await service.add_question(
            session,
            interview_id=interview.id,
            asker_id=USERS["asker1"]["id"],
            asker_name=USERS["asker1"]["name"],
            question_text=(
                "This is a really long question to test how the embed system handles "
                "text wrapping and chunking. It should be long enough to potentially "
                "cause issues if there are any bugs in the word-wrapping logic. "
                "What are your thoughts on the current state of Standard, and do you "
                "think the recent bannings were justified given the metagame data?"
            ),
            source_guild_id=TEST_SERVER_ID,
            source_channel_id=CHANNELS["questions"],
            source_message_id=500000000000000007,
        )
        await session.commit()
    print("  Added Q6: unanswered (long question)")

    return interview


async def seed_votes(interview: Interview) -> None:
    """Add votes for the next interviewee."""
    print("Adding votes...")
    async with get_session() as session:
        # Voter1 votes for Candidate1
        await service.cast_vote(
            session,
            interview_id=interview.id,
            voter_id=USERS["voter1"]["id"],
            candidate_id=USERS["candidate1"]["id"],
        )
        await session.commit()
    print(f"  {USERS['voter1']['name']} voted for {USERS['candidate1']['name']}")

    async with get_session() as session:
        # Voter2 votes for Candidate1
        await service.cast_vote(
            session,
            interview_id=interview.id,
            voter_id=USERS["voter2"]["id"],
            candidate_id=USERS["candidate1"]["id"],
        )
        await session.commit()
    print(f"  {USERS['voter2']['name']} voted for {USERS['candidate1']['name']}")

    async with get_session() as session:
        # Asker1 votes for Candidate2
        await service.cast_vote(
            session,
            interview_id=interview.id,
            voter_id=USERS["asker1"]["id"],
            candidate_id=USERS["candidate2"]["id"],
        )
        await session.commit()
    print(f"  {USERS['asker1']['name']} voted for {USERS['candidate2']['name']}")


async def print_summary() -> None:
    """Print a summary of the seeded data."""
    print("\n" + "=" * 60)
    print("SEED DATA SUMMARY")
    print("=" * 60)

    async with get_session() as session:
        server = await service.get_server(session, TEST_SERVER_ID)
        interview = await service.get_current_interview(session, TEST_SERVER_ID)

        if server:
            print(f"\nServer: {server.name} (ID: {server.id})")
            print(f"  Active: {server.active}")
            print(f"  Answer Channel: {server.answer_channel_id}")
            print(f"  Manager Role: {server.manager_role_id}")

        if interview:
            print(f"\nCurrent Interview: {interview.interviewee_name}")
            print(f"  Interview ID: {interview.id}")

            questions = await service.get_questions(session, interview.id, service.QuestionFilter.ALL)
            answered = [q for q in questions if q.answer_text]
            posted = [q for q in questions if q.is_posted]
            print(f"  Questions: {len(questions)} total, {len(answered)} answered, {len(posted)} posted")

            votals = await service.get_votals(session, interview.id)
            print(f"  Votes: {sum(count for _, count in votals)} total")
            for candidate_id, count in votals:
                # Find candidate name
                name = next((u["name"] for u in USERS.values() if u["id"] == candidate_id), f"Unknown ({candidate_id})")
                print(f"    {name}: {count} votes")

        opt_outs = await service.get_opt_outs(session, TEST_SERVER_ID)
        if opt_outs:
            print(f"\nOpt-outs: {len(opt_outs)} users")

    print("\n" + "=" * 60)
    print("TEST USER IDS (for Discord commands)")
    print("=" * 60)
    for role, user in USERS.items():
        print(f"  {role}: {user['id']} ({user['name']})")

    print("\nTo test commands, you'll need to use your real Discord user ID.")
    print("The seeded data uses fake IDs for the test scenario.")
    print("=" * 60)


async def main(clear: bool = False) -> None:
    """Main entry point for seeding."""
    # Get database URL from environment or use default for local dev
    database_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://eimm:eimm@localhost:5432/eimm")

    print("Connecting to database...")
    print(f"  URL: {database_url.replace(database_url.split(':')[2].split('@')[0], '***')}")

    # Initialize database
    init_db(database_url)

    if clear:
        await clear_interview_data()

    # Seed data
    await seed_server()
    await seed_opt_outs()
    await seed_past_interview()
    interview = await seed_current_interview()
    await seed_votes(interview)

    # Print summary
    await print_summary()

    print("\nSeeding complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed test data for interview cog")
    parser.add_argument("--clear", "-c", action="store_true", help="Clear existing interview data before seeding")
    args = parser.parse_args()

    asyncio.run(main(clear=args.clear))
