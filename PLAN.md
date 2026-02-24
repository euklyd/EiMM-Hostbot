# EiMM-Hostbot Modernization Plan

## Overview

Modernize the EiMM-Hostbot Discord bot with these changes:

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Complete | Migrate from Poetry to uv |
| 2 | ✅ Complete | Linting (ruff) + Type-checking (pyright) |
| 3 | ✅ Complete | CI/CD pipelines (GitHub Actions) |
| 4 | ✅ Complete | Docker Compose (PostgreSQL for Phase 8) |
| 5 | ✅ Complete | Consolidate cogs + plugins → all cogs |
| 6 | ✅ Complete | Upgrade discord.py v1.7.3 → v2.x |
| 7 | ✅ Complete | Add unit tests with pytest (219 tests) |
| 8 | ✅ Complete | Overhaul interview cog: PostgreSQL + web admin UI |
| 8b | 🔧 In Progress | [Interview missing features](docs/design-plans/2026-02-20-interview-missing-features.md): commands, migration, tests |

---

## Phase 8: Interview Cog Overhaul

### Key Decisions

#### 1. Fresh Rewrite (not refactor)

**Rationale:**
- Existing code (1812 lines) has blocking gspread calls woven throughout
- Dual data model (SQLite metadata + Google Sheets Q&A) → single PostgreSQL
- Code structure shaped around sheets API (row indices, cell references)
- Need async throughout for web interface

**Existing code as spec:**
- Use old `interview.py` as reference for expected behavior and edge cases
- Keep identical user experience on command side

#### 2. Hybrid Commands (prefix + slash)

Support both `##ask` and `/ask` for backwards compatibility:

```python
from discord.ext import commands

class Interview(commands.Cog):
    @commands.hybrid_command(name="ask")
    @commands.describe(question="Your question for the interviewee")
    async def ask(self, ctx: commands.Context, *, question: str):
        """Submit a question for the current interview."""
        # Same handler for both ##ask and /ask
        ...

    @commands.hybrid_group(name="iv", fallback="help")
    async def iv(self, ctx: commands.Context):
        """Interview management commands."""
        ...

    @iv.command(name="settings")
    async def iv_settings(self, ctx: commands.Context):
        # Works as both ##iv settings and /iv settings
        ...
```

**Slash command benefits:**
- Autocomplete for `/vote candidate:` (shows member list)
- Parameter validation enforced by Discord
- Discoverability for new users
- Member/Channel pickers in UI

#### 3. Components to Extract from Old Code

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| `InterviewEmbed` class | Lines 225-246 | Copy as-is (Discord formatting) |
| `add_question()` | Lines 269-349 | Copy (word-wrapping edge cases) |
| `Candidate` / votals | Lines 60-85 | Adapt to new models |
| `_generate_embeds()` | Lines 350+ | Adapt for new Question model |

#### 4. Same-Process Architecture

**Bot + Web server in single async process:**

```
┌─────────────────────────────────────────────────────┐
│                 Single Process                       │
│  ┌─────────────────┐      ┌─────────────────────┐   │
│  │   Discord Bot   │◄────►│   FastAPI + WebSocket│  │
│  │   (discord.py)  │      │   (admin UI)         │  │
│  └────────┬────────┘      └──────────┬──────────┘   │
│           │     Shared async loop    │              │
│           └────────────┬─────────────┘              │
└────────────────────────┼────────────────────────────┘
                         ▼
                   [PostgreSQL]
```

**Why same-process:**
- Direct function calls between bot and web (no IPC)
- WebSocket push is trivial: bot event → directly notify browsers
- Simpler deployment (one container)

**Why PostgreSQL:**
- Web interface needs concurrent access (multiple admins + bot)
- Row-level locking for simultaneous edits
- Network-native for container separation

---

### 8.1 Current State (Old Code)

- SQLite for metadata (server settings, votes, interview history)
- Google Sheets for Q&A content (questions, answers, posted status)
- **Blocking synchronous gspread calls** throughout
- Prefix commands only (`##ask`, `##vote`, etc.)

### 8.2 New PostgreSQL Schema

Replaces both SQLite + Google Sheets:

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Text, BigInteger
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Server(Base):
    __tablename__ = 'interview_servers'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Discord guild ID
    name: Mapped[str]
    sheet_name: Mapped[str | None]  # Legacy reference, remove later
    answer_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    backstage_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    manager_role_id: Mapped[int | None] = mapped_column(BigInteger)
    audience_role_id: Mapped[int | None] = mapped_column(BigInteger)
    default_question: Mapped[str] = mapped_column(default="What's your favorite card?")
    reinterview_limit: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=False)

    interviews: Mapped[list["Interview"]] = relationship(back_populates="server")

class Interview(Base):
    __tablename__ = 'interviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('interview_servers.id'))
    interviewee_id: Mapped[int] = mapped_column(BigInteger)  # Discord user ID
    interviewee_name: Mapped[str]
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    is_current: Mapped[bool] = mapped_column(default=True)
    op_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    op_message_id: Mapped[int | None] = mapped_column(BigInteger)

    server: Mapped["Server"] = relationship(back_populates="interviews")
    questions: Mapped[list["Question"]] = relationship(back_populates="interview")

class Question(Base):
    __tablename__ = 'interview_questions'
    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey('interviews.id'))
    question_number: Mapped[int]
    asker_id: Mapped[int] = mapped_column(BigInteger)
    asker_name: Mapped[str]
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text)
    is_posted: Mapped[bool] = mapped_column(default=False)
    asked_at: Mapped[datetime]
    answered_at: Mapped[datetime | None]
    # For jump_url reconstruction
    source_channel_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    # Posted message reference
    posted_message_id: Mapped[int | None] = mapped_column(BigInteger)

    interview: Mapped["Interview"] = relationship(back_populates="questions")

class Vote(Base):
    __tablename__ = 'interview_votes'
    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('interview_servers.id'))
    voter_id: Mapped[int] = mapped_column(BigInteger)
    candidate_id: Mapped[int] = mapped_column(BigInteger)
    voted_at: Mapped[datetime]

class OptOut(Base):
    __tablename__ = 'interview_opt_outs'
    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('interview_servers.id'))
    user_id: Mapped[int] = mapped_column(BigInteger)
```

### 8.3 Web Admin UI

**FastAPI with WebSocket for real-time updates:**

```python
from fastapi import FastAPI, WebSocket
import uvicorn

ws_clients: dict[int, list[WebSocket]] = {}  # interview_id -> connected clients

app = FastAPI()

@app.get("/interviews/{interview_id}")
async def get_interview(interview_id: int): ...

@app.patch("/questions/{question_id}")
async def update_question(question_id: int, data: QuestionUpdate):
    # Update DB, push to WebSocket clients
    ...

@app.post("/questions/{question_id}/post")
async def post_question(question_id: int):
    # Directly call bot to post to Discord
    ...

@app.websocket("/interviews/{interview_id}/ws")
async def interview_websocket(websocket: WebSocket, interview_id: int):
    await websocket.accept()
    ws_clients.setdefault(interview_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    finally:
        ws_clients[interview_id].remove(websocket)

# Called from bot when new question arrives
async def notify_new_question(question: Question):
    for ws in ws_clients.get(question.interview_id, []):
        await ws.send_json({"type": "new_question", "data": question.to_dict()})
```

**Features:**
- Discord OAuth2 login (managers only)
- Spreadsheet-like Q&A interface
- Edit/moderate answers inline
- Real-time updates via WebSocket
- "Post to Discord" button

### 8.4 Directory Structure

```
├── bidoof.py                    # Entry point (bot + web)
├── core/
│   └── bot.py
├── cogs/
│   └── interview/
│       ├── __init__.py          # Cog class with hybrid commands
│       ├── models.py            # SQLAlchemy models
│       ├── embeds.py            # InterviewEmbed, add_question (extracted)
│       ├── commands.py          # Command implementations
│       └── service.py           # Business logic (shared by bot + web)
├── db/
│   ├── session.py               # Async session factory (asyncpg)
│   └── migrations/              # Alembic migrations
├── web/
│   ├── app.py                   # FastAPI application
│   ├── auth.py                  # Discord OAuth2
│   ├── routes/
│   │   └── interviews.py
│   ├── static/
│   └── templates/
│       └── interviews/
│           ├── list.html
│           └── detail.html
└── docker-compose.yml
```

### 8.5 Interface Decisions

Which features are available via Discord vs Web:

| Feature | Discord | Web | Notes |
|---------|:-------:|:---:|-------|
| **Ask question** | ✅ | ❌ | Discord only (architect for future web) |
| **Masked ask** | ✅ | ❌ | Discord only |
| **Vote** | ✅ | ❌ | Discord only, no hidden voting. May restrict to specific channel. |
| **Unvote** | ✅ | ❌ | |
| **View votals** | ✅ | ❌ | |
| **Answer questions** | ✅ | ✅ | Web is primary (spreadsheet-like) |
| **Preview answers** | ✅ | ✅ | |
| **Post answers** | ✅ | ✅ | |
| **Start interview** | ✅ | ✅ | Both - forces good permissions architecture |
| **End interview** | ✅ | ✅ | Both |
| **Configure channels** | ✅ | ✅ | |
| **Configure roles** | ✅ | ✅ | |
| **Enable/disable** | ✅ | ✅ | |
| **Opt-out/opt-in** | ✅ | ❌ | Discord only |
| **View Q's in progress** | ❌ | ✅ | Managers only - like gsheet experience |
| **Delete/moderate Q's** | ❌ | ✅ | Managers only - for harassment tracking |
| **Interview archive** | ❌ | ✅ | Answered questions only, server members only |
| **Stats/analytics** | ❌ | ✅ | Questions per interview, top askers, avg answer time, duration |

**Access Control:**
- All web access requires Discord OAuth2 authentication
- Users can only view archives for servers they're members of
- Archive shows ANSWERED questions only (unanswered visible to managers/interviewee)
- Managers can view all questions including unanswered (perk of hosting)

### 8.6 Implementation Steps

1. **Set up async database layer** ✅
   - Add `asyncpg` and `sqlalchemy[asyncio]` dependencies
   - Create async session factory (`db/session.py`)
   - Set up Alembic for migrations
   - Docker entrypoint with auto-backup before migrations

2. **Create new models** (`cogs/interview/models.py`) ✅
   - SQLAlchemy 2.0 with `Mapped[]` types
   - BigInteger for Discord IDs
   - `is_current` as computed property (not stored column)
   - Votes linked to Interview for historical tracking
   - UniqueConstraint on (interview_id, voter_id, candidate_id)
   - 20 model tests

3. **Extract reusable components** (`cogs/interview/embeds.py`) ✅
   - Clean rewrite with named constants (no magic numbers)
   - `AddQuestionResult` enum instead of cryptic -1/-2 error codes
   - Pure functions instead of useless `InterviewEmbed` subclass
   - `QuestionData`/`IntervieweeData` dataclasses for testability
   - `generate_answer_embeds()` main entry point
   - 34 embed tests

4. **Build service layer** (`cogs/interview/service.py`) ✅
   - Interview lifecycle (start, end, archive)
   - Question CRUD (add, answer, delete, filter, mark_posted)
   - Voting (cast, remove, get_votals)
   - Server config and opt-outs
   - Stats queries (counts, averages, top askers)
   - Auth helper stubs (for web interface)
   - 48 service tests

5. **Implement hybrid commands** (`cogs/interview/commands.py`) ✅
   - All existing commands as `@hybrid_command`
   - Permission check decorators (is_manager, is_interviewee, interviews_enabled)
   - Audience commands: ask, mask, vote, unvote, votes, votals
   - Interviewee commands: preview, answer
   - Management commands: iv start/end/settings/channel/setmanager/enable/disable
   - Opt-out commands: opt out/in/list
   - Package __init__.py with setup() function
   - **Recent additions:**
     - `iv setup` command (required before other commands)
     - `iv reset CONFIRM` dev command
     - `TextChannelConverter` for snowflake IDs with Unicode cleanup
     - `_require_setup()` helper for consistent validation
     - 9 converter tests

6. **Build FastAPI web interface** ✅
   - Discord OAuth2 authentication
   - REST endpoints for CRUD
   - WebSocket for real-time updates
   - Vue 3 frontend with Pinia stores
   - Mobile-responsive design

7. **Write migration script** (deferred)
   - Import existing SQLite data
   - Import Google Sheets Q&A history (4 spreadsheets, gspread)
   - See [interview missing features plan](docs/design-plans/2026-02-20-interview-missing-features.md)

8. **Update Docker Compose** ✅
   - Combined bot+web container
   - PostgreSQL connection
   - `docker-compose.override.example.yml` for dev bind mounts

### 8.7 Recent Schema Changes

**Migration `5a8b2c9d1e4f`: Vote per-server**
- Added `server_id` to Vote (required)
- Made `interview_id` nullable (optional, for historical tracking)
- Changed unique constraint: `(server_id, voter_id, candidate_id)`
- Allows voting without active interview

**Migration `7c3e4f5a6b8d`: Interview numbering**
- Added `interview_number` field (ordinal per server: 1, 2, 3...)
- Displayed as "Interview #N" instead of DB primary key
- Resets per server, survives `iv reset`

### 8.8 Service Layer Specification

Business logic shared between Discord commands and web routes.

#### Schema Updates Required

Add to `Server` model:
```python
voting_channel_id: Mapped[int | None] = mapped_column(BigInteger)  # Restrict voting to channel
```

Add to `Question` model:
```python
deleted_at: Mapped[datetime | None]  # Soft delete for moderation
deleted_by_id: Mapped[int | None] = mapped_column(BigInteger)  # Who deleted
```

#### Service Operations

**Interview Lifecycle:**
```python
start_interview(server_id, interviewee_id, interviewee_name, op_channel_id, op_message_id) → Interview
end_interview(interview_id) → Interview
get_current_interview(server_id) → Interview | None
get_interview(interview_id) → Interview | None
get_interview_archive(server_id, limit, offset) → list[Interview]
```

**Questions:**
```python
add_question(interview_id, asker_id, asker_name, text, source_channel_id, source_message_id) → Question
get_questions(interview_id, filter: all|unanswered|answered_unposted|posted) → list[Question]
answer_question(question_id, answer_text) → Question
delete_question(question_id, deleted_by_id) → None  # Soft delete for moderation
mark_posted(question_ids, posted_message_id) → None
```

**Voting:**
```python
cast_vote(server_id, voter_id, candidate_id) → Vote
remove_vote(server_id, voter_id) → bool
get_votals(server_id) → list[tuple[candidate_id, vote_count]]
get_user_vote(server_id, voter_id) → Vote | None
```

**Server Config:**
```python
get_or_create_server(server_id, name) → Server
update_server_config(server_id, **fields) → Server
```

**Opt-outs:**
```python
opt_out(server_id, user_id) → OptOut
opt_in(server_id, user_id) → bool
is_opted_out(server_id, user_id) → bool
get_opt_outs(server_id) → list[int]
```

**Stats (for web dashboard):**
```python
count_questions(interview_id, answered_only: bool = False) → int
get_avg_answer_time(interview_id) → float | None  # seconds
get_top_askers(server_id, limit) → list[tuple[user_id, question_count]]
get_server_stats(server_id) → dict  # total interviews, total questions, averages
```

**Authorization Helpers (for web routes):**
```python
can_view_interview(user_id, interview_id) → bool      # Must be server member
can_view_unanswered(user_id, interview_id) → bool     # Must be manager or interviewee
can_manage_interview(user_id, server_id) → bool       # Must have manager role
can_configure_server(user_id, server_id) → bool       # Must be server admin
```

Note: Auth helpers need Discord API calls to check roles/membership. Will cache or use OAuth token info.

#### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Session management | Caller provides session | Commands/routes control transaction boundaries |
| Return types | Models directly | No DTOs needed for internal use |
| Error handling | Raise exceptions | Let callers decide presentation |
| Discord coupling | None | Service is pure database logic |
| Stats | Simple methods, no dataclasses | Web route assembles response shape |

#### Implementation Order

1. Schema updates + Alembic migration
2. Core CRUD (interview, question, vote)
3. Config operations (server settings, opt-outs)
4. Stats queries (aggregations)
5. Auth helpers (stubbed initially, full implementation with web auth)

### 8.8 Command Reference

| Old Command | New (Hybrid) | Slash Features |
|-------------|--------------|----------------|
| `##ask <q>` | `/ask question:` | - |
| `##mask <q1>\n<q2>` | `/mask questions:` | Modal for multi-line? |
| `##vote @user` | `/vote candidate:` | Member autocomplete |
| `##unvote` | `/unvote` | - |
| `##votals` | `/votals` | - |
| `##answer` | `/answer` | - |
| `##preview` | `/preview` | - |
| `##iv start @user` | `/iv start interviewee:` | Member picker |
| `##iv settings` | `/iv settings` | - |
| `##iv channel` | `/iv channel type: channel:` | Channel picker |
| `##iv enable/disable` | `/iv enable`, `/iv disable` | - |

---

## Completed Phases (Summary)

### Phase 1: Poetry → uv ✅
- Rewrote `pyproject.toml` for uv/hatchling
- Deleted `poetry.lock`, `pip-requirements.txt`

### Phase 2: Linting + Type-checking ✅
- Added ruff for linting/formatting
- Added pyright for type-checking
- Configured lenient settings for legacy code

### Phase 3: CI/CD Pipelines ✅
- GitHub Actions workflow for lint, typecheck, test
- Runs on push to master and PRs

### Phase 4: Docker Compose ✅
- `Dockerfile` for bot container
- `docker-compose.yml` with PostgreSQL service

### Phase 5: Consolidate Cogs ✅
- Moved all plugins to `cogs/`
- Deleted `plugins/` directory
- Removed unused `profiles.py` cog

### Phase 6: discord.py v2 ✅
- Async startup pattern
- `async def setup()` for all cogs
- Fixed deprecated APIs

### Phase 7: Unit Tests ✅
- **219 tests passing** (118 base + 23 interview models + 34 interview embeds + 42 service + 2 cog cleanup)
- Priority 1: Utility functions (19 tests)
- Priority 2: Core business logic (80 tests)
- Priority 3: SQLAlchemy models (19 tests)
- SQLite in-memory for fast tests
- Database fixtures in `conftest.py`
