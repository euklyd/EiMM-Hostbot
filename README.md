# EiMM-Hostbot

A Discord bot for running mafia games and community interviews.

## Quick Start

### Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** - Python package manager

Install uv if you don't have it:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1. Clone and Install

```bash
git clone https://github.com/euklyd/EiMM-Hostbot.git
cd EiMM-Hostbot
uv sync
```

This creates a virtual environment and installs all dependencies.

### 2. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" tab and click "Add Bot"
4. Copy the **Token** (you'll need this in step 3)
5. Under "Privileged Gateway Intents", enable:
   - **Server Members Intent** ✓
   - **Message Content Intent** ✓
6. Go to "OAuth2" → "URL Generator":
   - Select scopes: `bot`, `applications.commands`
   - Select permissions: `Send Messages`, `Manage Messages`, `Add Reactions`, `Read Message History`, `Use External Emojis`
   - Copy the generated URL and open it to invite the bot to your test server

### 3. Configure the Bot

Copy the example config:
```bash
cp conf/settings-example.py conf/settings.py
```

Edit `conf/settings.py` with your values:

```python
# Required changes:
owner_id = 123456789012345678      # Your Discord user ID
client_token = "your-bot-token"   # From step 2

# Optional: Choose which cogs to load
extensions = [
    "eimm",
    "hostbot",
    # "macro",      # Requires Imgur API keys (see below)
    "scryfall",   # Card search: [[Lightning Bolt]]
    "utility",
    # "interview",  # Complex, requires Google Sheets setup
]

# Optional: Custom emoji IDs for reactions (or leave defaults)
# The bot uses these to react to commands with ✅ or ❌

# Optional: Imgur API keys (only needed for macro cog)
# Leave as placeholder strings if not using macros
imgur_keys = {
    "id": "not-configured",
    "secret": "not-configured",
    "access": "not-configured",
    "refresh": "not-configured",
}
```

**How to get your Discord user ID:**
1. Enable Developer Mode in Discord (Settings → Advanced → Developer Mode)
2. Right-click your username → "Copy User ID"

### 4. Run the Bot

```bash
uv run python bidoof.py
```

You should see:
```
[timestamp] loaded cogs.eimm
[timestamp] loaded cogs.hostbot
...
```

Test it works by typing `##help` in a channel the bot can see.

### 5. Run Tests (Optional)

```bash
uv run pytest
```

All 172 tests should pass.

---

## Cog Overview

| Cog | Description | Commands |
|-----|-------------|----------|
| `eimm` | EiMM game management, ability search | `<<ability>>`, `##role` |
| `hostbot` | Mafia game hosting tools | `##players`, `##in`, `##out` |
| `macro` | Text macros/shortcuts | `##macro` |
| `scryfall` | MTG/Yu-Gi-Oh card search | `[[card]]`, `{{card}}` |
| `utility` | Misc utilities | `##clear`, `##ping` |
| `interview` | Community interviews (complex) | `##ask`, `##vote`, `##iv` |

---

## Interview Cog Setup (Optional)

The interview cog requires Google Sheets API access. Skip this if you don't need interviews.

### 1. Create Google API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/dashboard)
2. Create a new project (or select existing)
3. Enable the **Google Sheets API**
4. Go to "Credentials" → "Create Credentials" → "Service Account"
5. Download the JSON key file
6. Rename it to `google_creds.json` and put it in the `conf/` folder

### 2. Update Config

In `conf/settings.py`:

```python
extensions = [
    # ... other cogs ...
    "interview",  # Uncomment this
]

conf = Conf(
    # ... other settings ...
    google_email="your-service-account@your-project.iam.gserviceaccount.com",
)
```

### 3. Create Interview Spreadsheet

1. Copy [this template](https://docs.google.com/spreadsheets/d/1cC3YtXrXlykd6vfI5Q6y1sw8EGH9walpidZB4BJKTbw/edit?usp=sharing)
2. Share it with your service account email (from step 1)
3. Run `##iv setup #answer-channel #backstage-channel "Sheet Name"` in Discord

---

## Running with Docker Compose

For production or if you prefer containers:

### 1. Configure the Bot

Same as the Quick Start - create `conf/settings.py` from the example and add your token.

### 2. Create Database Password

Create a `.env` file with your database password:
```bash
echo "DB_PASSWORD=$(openssl rand -base64 32)" > .env
```

Or manually:
```bash
echo "DB_PASSWORD=choose-a-secure-password" > .env
```

### 3. Start Everything

```bash
docker compose up -d
```

This starts:
- **bot** - The Discord bot
- **postgres** - PostgreSQL database (for new interview system)

### 4. View Logs

```bash
docker compose logs -f bot
```

### 5. Stop

```bash
docker compose down
```

To also remove the database volume (destroys all data):
```bash
docker compose down -v
```

---

## Development

### Project Structure

```
├── bidoof.py              # Entry point
├── core/bot.py            # Bot class
├── cogs/                  # All cogs (features)
│   ├── eimm.py
│   ├── hostbot.py
│   ├── interview/         # New interview cog (WIP)
│   │   ├── models.py      # SQLAlchemy models
│   │   └── embeds.py      # Embed generation
│   └── ...
├── conf/                  # Configuration
│   ├── settings.py        # Your config (gitignored)
│   └── settings-example.py
├── tests/                 # Unit tests
└── db/                    # Database layer
```

### Running Linting

```bash
uv run ruff check .
uv run ruff format .
```

### Type Checking

```bash
uv run pyright
```

(Note: Many warnings from legacy code, not blocking)

---

## Troubleshooting

### "Invalid token"
- Make sure you copied the full token from Discord Developer Portal
- Regenerate the token if needed

### Bot doesn't respond to commands
- Check the bot has "Message Content Intent" enabled
- Make sure you're using the right prefix (`##` by default)
- Check the bot has permission to read/send in that channel

### "Database not initialized"
- The cog's database file might be missing
- Check `databases/` directory exists

### Import errors
- Run `uv sync` to ensure all dependencies are installed
- Check you're using Python 3.12+: `python --version`
