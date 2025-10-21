# TytoCogsV3 Development Guide

## Project Overview

TytoCogsV3 is a collection of **Red-DiscordBot V3 cogs** (plugins) that extend Discord bot functionality. Each cog is an independent module following Red-DiscordBot's architecture patterns.

**Architecture:** Monorepo with isolated cog directories (`aurora/`, `gpt3chatbot/`, `mcinfo/`, etc.). Each cog follows the Red-DiscordBot plugin pattern with standardized structure.

**Branching Strategy:** GitHub Flow - feature and fix branches (e.g., `aurora/event-system-refactor`) are merged to `main` via pull requests. Create descriptive branch names prefixed with the cog name or feature area.

## Red-DiscordBot Cog Architecture

### Essential Cog Structure

Every cog MUST have these components:

```
cogname/
├── __init__.py       # Export setup(bot) function
├── cogname.py        # Main cog class inheriting commands.Cog
└── info.json         # Metadata (follows red_cog.schema.json)
```

**Critical Pattern:** All cogs inherit from `commands.Cog` and are registered via `setup()` function:

```python
# cogname/__init__.py
async def setup(bot: Red):
    await bot.add_cog(CogName(bot))

# cogname/cogname.py
class CogName(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=UNIQUE_ID, force_registration=True)
```

### Configuration Pattern

Cogs use Red's `Config` API for persistent storage:

- `Config.get_conf(self, identifier=UNIQUE_ID, force_registration=True)` - unique identifier required
- Register scopes: `register_global()`, `register_guild()`, `register_user()`, `register_member()`, `register_channel()`
- Access: `await self.config.setting_name()` / `await self.config.guild(guild).setting_name()`

**Example from aurora/aurora.py:**
```python
self.config = Config.get_conf(self, identifier=3897456238745, force_registration=True)
default_global = {"letta_base_url": "https://api.letta.ai/v1"}
self.config.register_global(**default_global)
```

### API Key Management

Access shared API tokens via bot instance:

```python
tokens = await self.bot.get_shared_api_tokens("service_name")
api_key = tokens.get("key") or tokens.get("api_key")
```

Users set tokens with: `[p]set api service_name key,<value>`

### Lifecycle Hooks

- `cog_load()` - Async initialization (replaces `__init__` for async setup)
- `cog_unload()` - Cleanup tasks, cancel loops
- `@commands.Cog.listener("event_name")` - Discord event handlers

**Example from aurora/aurora.py:**
```python
async def cog_load(self):
    await self.initialize_letta()
    # Start background tasks for enabled guilds

async def cog_unload(self):
    self._cancel_tasks()  # Clean up background tasks
```

## Background Tasks Pattern

Use `discord.ext.tasks` for periodic operations:

```python
from discord.ext import tasks

# Create task registry in __init__
self.tasks: dict[str, tasks.Loop] = {}

# Dynamic task creation
def _get_or_create_task(self, guild_id: int, interval_secs: int = 3600) -> tasks.Loop:
    task_name = f"task_{guild_id}"
    if task_name not in self.tasks:
        task = tasks.loop(seconds=interval_secs)(self.my_task)
        self.tasks[task_name] = task
        task.start(guild_id=guild_id)
    return self.tasks[task_name]
```

See `aurora/aurora.py` for per-guild task management with synthesis loop.

## Testing

**Framework:** pytest with async support

- Run tests: `pytest` (configured in `pytest.ini`)
- Test files: `test_*.py` in cog directories
- Use `@pytest.mark.asyncio` for async tests
- Fixtures in conftest or inline with `@pytest.fixture`

**Debug configuration:** `.vscode/launch.json` includes:
- "Run Redbot" - launches bot with `--dev` flag
- "Python: Debug Tests" - pytest debugging

**Example test patterns from mcinfo/test_helpers.py:**
```python
@pytest.mark.asyncio
async def test_fetch_servers():
    results = await fetch_servers(["mc.tyto.cc:25565"])
    assert isinstance(results["mc.tyto.cc:25565"], JavaStatusResponse)
```

## Project-Specific Patterns

### Message Listeners

Two approaches for responding to messages:

1. **Event-based (gpt3chatbot):** `@commands.Cog.listener("on_message_without_command")`
2. **Context Menu (tldw):** Register `app_commands.ContextMenu` in `__init__`

### Async Client Initialization

External services are initialized in `cog_load()` or dedicated init methods:

```python
async def initialize_letta(self):
    letta_tokens = await self.bot.get_shared_api_tokens("letta")
    if token := letta_tokens.get("token"):
        self.letta = AsyncLetta(base_url=..., token=token)
```

### Utility Module Pattern

Helper functions in `utils.py` or `helpers.py`:
- `aurora/utils.py` - Letta block management (attach/detach)
- `mcinfo/helpers.py` - Server status fetching and formatting
- `gpt3chatbot/utils.py` - Memoization decorator

### Retry/Error Handling

See `ispyfj/ispyfj.py` for exponential backoff decorator:
```python
@exponential_backoff_retry(max_retries=3, base_delay=1.0, exponential_base=2.0)
async def login_with_retry(self):
    # Implementation with automatic retry on ClientError
```

## Dependency Management

**Tool:** uv (configured in `pyproject.toml`)

- Dependencies: Listed in `[project.dependencies]`
- Dev dependencies: Listed in `[dependency-groups.dev]`
- Per-cog requirements: `info.json` includes `requirements` field
- **Note:** `[tool.uv] package = false` - not a publishable package

## Code Style

**Formatter:** Black (line length: 120)
- Config in `pyproject.toml`: `[tool.black]`
- Pre-commit hooks configured: `pre-commit>=4.2.0` in dev dependencies

**Linting:** flake8 (`flake8>=7.3.0`)

## Aurora-Specific (Letta Integration)

**Status:** Aurora is under active development. Features and architecture may change frequently.

Aurora integrates Letta AI agents with Discord. The agent operates autonomously within Discord servers, using a self-hosted Letta instance (or Letta Cloud) as the backend. The Letta agent has access to MCP (Model Context Protocol) tools for Discord interactions, so **the cog's role is minimal:**

1. **Configuration management** - Base URL, API keys, per-guild agent IDs
2. **Message listening** - Forward Discord messages to Letta agent
3. **Event scheduling** - Trigger periodic synthesis/self-reflection tasks

**Key architectural concepts:**

- **MCP Tools:** Agent uses `mcp-discord` for Discord operations (sending messages, reading channels, etc.) - server-side execution in Letta
- **Memory blocks:** Temporal journal blocks attached dynamically during synthesis (daily/monthly/yearly journals)
- **Synthesis task:** Periodic self-reflection loop (default: hourly) for journaling and memory consolidation
- **Block lifecycle:** Attach journal blocks before synthesis, detach after (see `utils.py`)
- **Streaming responses:** Handle `message_type` in stream chunks (reasoning_message, tool_call_message, tool_return_message)
- **Configuration commands:** Standard Red commands for managing Aurora settings (agent IDs, intervals, etc.)

**Reference:** See `.github/instructions/LETTA.instructions.md` for Letta API patterns (applies to `aurora/**`)

## Key Files

- `pyproject.toml` - Dependencies, Black config, commitizen
- `pytest.ini` - Test configuration (`asyncio_mode = auto`)
- `info.json` (root) - Repository metadata
- `.vscode/launch.json` - Debug configurations for Red-DiscordBot
- `CHANGELOG.md` - Conventional commits changelog (managed by commitizen)

## Common Commands

```bash
# Run bot in development mode
redbot <instance_name> --dev

# Run tests
pytest

# Format code
black .

# Install dependencies
uv sync
```

## Anti-Patterns to Avoid

- ❌ Don't use blocking I/O - Red-DiscordBot requires async operations
- ❌ Don't forget `force_registration=True` in Config.get_conf()
- ❌ Don't reuse Config identifiers between cogs - must be globally unique
- ❌ Don't forget to cancel tasks in `cog_unload()`
- ❌ Don't bypass Red's shared API token system - use `bot.get_shared_api_tokens()`
