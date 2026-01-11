# Backlog

Feature requests and improvements for the EiMM-Hostbot interview system.

## Web Interface

### Interview Search
- Search interviews within a server
- Filter by: asker, interviewee, question content, answer content

### WebSocket on Server Page
- Add real-time WebSocket connection to the server detail page
- Show live updates when interviews start/end

### Refresh Button for Guild List
- Guild memberships are cached for 5 minutes
- Add a refresh button on the server list page to manually refresh the cache
- Create `/api/auth/refresh-guilds` endpoint that clears cache and refetches

### Hide Posted Questions
- Allow interviewee to hide/show questions that have already been posted to Discord
- Beyond just collapsing - actually filter them out of the list
- Toggle or filter control in the UI

### Tests for Web Routes
- Add pytest tests for FastAPI routes:
  - Auth flow (login, callback, logout, me)
  - Server/interview CRUD operations
  - Permission checks (membership, manager role)
  - WebSocket authentication
- Use `httpx.AsyncClient` with `app` for testing
- Mock Discord OAuth responses

## Discord Embeds

### Embed Edge Case Tests
- Add tests for edge cases in embed generation:
  - Field character limits (name: 256, value: 1024)
  - Number of fields per embed (max 25)
  - Total embed character limit (6000)
  - Image gallery limits (4 preview, 10 max)
  - Long questions/answers that need chunking
  - Mixed scenarios (images + long text + multiple askers)
- Identify more edge cases during implementation

## Interview Cog

### Fix Cog Reload Bug
SQLAlchemy raises "table already defined" error when reloading the cog:
```
ExtensionFailed: Extension 'cogs.interview' raised an error:
InvalidRequestError: Table 'interview_servers' is already defined for this MetaData instance.
```

Fix options:
1. Add `extend_existing=True` to model `__table_args__`
2. Restructure model imports to avoid re-registration
3. Use a separate MetaData instance per cog load

### `iv start` Auto-Select Top Voted
Make the user argument optional for `iv start`. If omitted, automatically select the candidate with the most votes (error if tie).

### Scheduled Interview Actions
Add configurable automatic actions:
- **Auto-disable** at a certain time (e.g., Sunday midnight)
- **Auto-rollover** at a certain time (end current, start next with top voted)

Implementation:
- Add `auto_disable_time` and `auto_rollover_time` to InterviewServer model
- Use discord.py `tasks.loop` or APScheduler for scheduling
- Store times as UTC, convert for display

## Architecture

### Error Result Pattern
Implement a consistent error handling pattern using typed result returns instead of exceptions for expected error cases.

```python
from dataclasses import dataclass
from typing import TypeVar, Union, Generic

OkT = TypeVar("OkT")
ErrT = TypeVar("ErrT")

@dataclass
class Error(Generic[ErrT]):
    error: ErrT
    message: str | None = None

Result = Union[OkT, Error[ErrT]]
```

Benefits:
- Explicit error handling at call sites
- Type checker catches unhandled error cases
- No hidden control flow from exceptions

### Split Settings into Config + Secrets
Split `conf/settings.py` into two files:
- `conf/config.py` - Non-sensitive settings (could be committed)
- `conf/secrets.py` - Sensitive credentials (gitignored)

### Consolidate All Cogs on PostgreSQL
Migrate remaining SQLite cogs to PostgreSQL:
- `hostbot.py` - Game hosting data
- `votes.py` - Voting data
- `emoji_count.py` - Emoji statistics

Benefits: Single database to manage/backup, consistent async patterns, simpler deployment.
