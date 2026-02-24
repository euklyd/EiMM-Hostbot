# Interview Cog: Missing Features Implementation Plan

## Context

The interview cog migration (Phase 8) is ~85% complete. Core Q&A workflow, voting, opt-outs, and web UI all work. This plan addresses the remaining gaps: missing Discord commands, a data migration script, web management routes, and command tests.

**Priority order:** Missing commands >> Migration script > Web features > Command tests

## Design Decisions

- Stage commands organized under `iv stage` subgroup (not top-level)
- Both interviewee AND managers can manage stage access
- `iv invite` deferred — audience role + `iv start` clearing on rollover covers the common case
- Days-based reinterview limiting (`reinterview_days` field, already in model)
- No new DB tables needed — all features use existing schema
- **Votes are cleared when a new interview starts** — voters re-vote each round

---

## Phase 1: Service Layer Additions

**File:** `cogs/interview/service.py`

New methods:

| Method | Section | Purpose |
|--------|---------|---------|
| `get_latest_interview_for_user(session, server_id, user_id)` | Interview lifecycle | For reinterview enforcement in vote |
| `get_votals_detailed(session, server_id) -> list[tuple[int, list[int]]]` | Voting | Returns (candidate_id, [voter_ids]) for --full flag |
| `clear_votes(session, server_id)` | Voting | Remove all votes for a server (called on interview start) |
| `get_member_question_count(session, server_id, user_id) -> int` | Stats | Questions asked by a member across all interviews |
| `get_member_interviews(session, server_id, user_id) -> list[Interview]` | Stats | Interviews where user was interviewee |

---

## Phase 2: Discord Commands

All in **`cogs/interview/commands.py`**. Each feature below is independently implementable once Phase 1 service methods exist.

### 2A. `iv setaudience @role` (admin only)

Simple setter — calls `update_server_config(audience_role_id=role.id)`.
Also update `iv settings` embed to display audience role and reinterview setting.

### 2B. `iv stage` group (interviewee OR manager)

New permission helper: `_can_manage_stage(ctx) -> bool` — checks interviewee OR manager OR admin.

| Command | Params | Logic |
|---------|--------|-------|
| `iv stage grant` | members (up to 5 for slash, Greedy for prefix) | Add audience role to members |
| `iv stage revoke` | same | Remove audience role |
| `iv stage list` | none | List `role.members` in embed |
| `iv stage clear` | none | Remove role from all members |

All validate `server.audience_role_id` exists first. Use same member param pattern as `vote` command.

### 2C. `iv reinterview` group (manager)

| Subcommand | Action |
|------------|--------|
| `iv reinterview` (no args / fallback) | Show current setting |
| `iv reinterview set <days>` | Set cooldown (0 = no limit) |
| `iv reinterview on` | Set `reinterviews_allowed=True` |
| `iv reinterview off` | Set `reinterviews_allowed=False` |

**Enforcement in `vote` command** (after opt-out check):
- If `reinterviews_allowed=False` -> reject candidates with any past interview
- If `reinterview_days > 0` -> reject candidates whose last interview `ended_at` is within cooldown
- Use `get_latest_interview_for_user()` for the check

### 2D. `iv stats [member]` (anyone, interviews_enabled)

Two modes:
1. **No args:** Current interview stats + server-wide stats (total interviews, avg questions). List past interviews with jump URLs.
2. **With @member:** Member's interview history (when interviewed, Q&A counts) + questions asked count.

Uses existing `get_server_stats()`, `get_top_askers()`, plus new `get_member_question_count()` and `get_member_interviews()`.

### 2E. `votals` `--full` flag

- Add `flag: str | None = None` param (like old code), check for `-f` in it
- Basic mode: existing behavior (name + count)
- Full mode: use `get_votals_detailed()` to show `**Name**: N votes (Voter1, Voter2, ...)`
- Always append footer with invoker's own votes (both modes)

### 2F. `iv start` improvements

After creating the interview, also:
1. Clear all votes for the server
2. Clear audience role from all current members (if `audience_role_id` set)
3. Add default question if `server.default_question` is set (asker = bot)

---

## Phase 3: Migration Script

**New file:** `scripts/migrate_interview_data.py`

One-time archival migration from old interview system (SQLite + Google Sheets) to new PostgreSQL schema.

### Data Sources

**Old SQLite** (`cogs/interview_schema.py`):
- `Server` -> `InterviewServer` (map `answer_channel`->`answer_channel_id`, `back_channel`->`backstage_channel_id`)
- `Vote` -> `Vote` (composite PK `(server_id, voter_id, candidate_id)` -> individual rows)
- `OptOut` -> `OptOut` (`opt_id`->`user_id`)

**Google Sheets** (4 spreadsheets, multiple worksheets each):
- Each worksheet = one interview
- Worksheet naming: `username [userid]-timestamp` (e.g. `frog.go [454293693600628747]-1695056606.554501`)
- Columns: `Time | POSIX Timestamp | Username | ID | # | Question | Answer | Posted? | Server ID | Channel ID | Message ID`
- Parse worksheet name for: interviewee name, interviewee Discord ID, interview start timestamp
- Each row -> a `Question` record

### Approach

Use `gspread` (already in project via `utils/spreadsheet.py`) to pull sheet data:
1. Connect to all 4 spreadsheets
2. Iterate worksheets in chronological order -> each becomes an `Interview` record (with `ended_at` set since all are historical)
3. Each row -> `Question` record with POSIX timestamp, asker info, answer, posted status, and source message IDs mapping directly
4. Import old SQLite data for server configs, votes, opt-outs

### Features
- `--old-db` path to SQLite file
- `--sheet-ids` list of Google Sheets document IDs
- `--dry-run` flag (rollback instead of commit)
- Logging of each entity migrated
- Handles missing/null fields gracefully

---

## Phase 4: Web Management Routes (lower priority)

**File:** `web/routes/interviews.py`

- `POST /api/interviews` — Start interview (manager only)
- `POST /api/interviews/{id}/end` — End interview (manager only)
- `PUT /api/servers/{id}/config` — Update server settings (manager only)
- `GET /api/servers/{id}/stage/members` — List stage members

These need the bot instance for Discord API calls (role assignment, channel posting). The web app already has access to the bot via `app.state.bot`.

---

## Phase 5: Command Tests (lower priority)

**File:** `tests/test_interview_commands.py`

Test areas:
- Stage grant/revoke/list/clear with mocked guild, roles, members
- Reinterview enforcement in vote command
- Stats display formatting
- Votals --full output
- Permission checks (interviewee, manager, neither)

Use existing mock fixtures from `conftest.py`.

---

## Verification

After implementation:
1. `uv run ruff check . && uv run ruff format --check .` — lint clean
2. `uv run pyright` — type-check clean
3. `uv run pytest` — all tests pass (existing 219 + new)
4. Manual test in Discord: stage commands, reinterview enforcement, votals --full, stats display
