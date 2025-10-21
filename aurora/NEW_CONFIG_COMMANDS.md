# Aurora Configuration Commands - New Additions

## Summary

Added comprehensive configuration viewing and management commands to Aurora:

1. **View Configuration** - Show current guild and global settings
2. **Agent Management** - Enable/disable/configure agents per guild
3. **Global Settings** - Configure bot-wide options (owner-only)

## New Commands

### Configuration Viewing

#### `[p]aurora config show [guild_id]`
**Permission**: Admin (or Owner for other guilds)

Show current configuration for a guild.

**Parameters**:
- `guild_id` (optional): Specific guild ID to view (owner-only feature)

**Output**:
- Agent status (enabled/disabled, agent ID)
- Event system settings (reply depth, typing indicator, DM responses, MCP guidance)
- Performance settings (rate limit, queue size, timeout)
- Global settings (Letta base URL - owner only)

**Examples**:
```
[p]aurora config show                    # Show current guild's config
[p]aurora config show 123456789012345    # Show specific guild's config (owner only)
```

---

### Agent Management

#### `[p]aurora enable <agent_id>`
**Permission**: Admin

Enable Aurora agent for the current guild and set the Letta agent ID.

**Parameters**:
- `agent_id` (required): The Letta agent ID to use

**Behavior**:
- Sets the agent ID for the guild
- Enables the agent
- Starts the synthesis task (if Letta is initialized)
- Bot will now respond to mentions and DMs in this guild

**Example**:
```
[p]aurora enable agent-3f7a8b2c-1234-5678-90ab-cdef12345678
```

---

#### `[p]aurora disable`
**Permission**: Admin

Disable Aurora agent for the current guild.

**Behavior**:
- Disables the agent (keeps agent ID saved)
- Stops the synthesis task
- Bot will no longer respond to mentions/DMs in this guild

**Example**:
```
[p]aurora disable
```

---

#### `[p]aurora setagent <agent_id>`
**Permission**: Admin

Change the Letta agent ID for the current guild without disabling/re-enabling.

**Parameters**:
- `agent_id` (required): The new Letta agent ID to use

**Behavior**:
- Updates the agent ID
- Restarts synthesis task if agent is enabled
- Does not change enabled/disabled status

**Example**:
```
[p]aurora setagent agent-abc123def456-new-agent-id
```

---

### Global Settings (Owner-Only)

#### `[p]aurora global baseurl [url]`
**Permission**: Owner

Get or set the Letta base URL for the bot.

**Parameters**:
- `url` (optional): New Letta base URL

**Behavior**:
- If no URL provided: Shows current base URL
- If URL provided: Updates the base URL (requires cog reload)

**Valid URLs**:
- Letta Cloud: `https://api.letta.ai/v1`
- Self-hosted: `http://localhost:8283` or custom domain

**Examples**:
```
[p]aurora global baseurl                              # Show current URL
[p]aurora global baseurl https://api.letta.ai/v1      # Set to Letta Cloud
[p]aurora global baseurl http://localhost:8283        # Set to local instance
```

**Note**: After changing the base URL, you must reload the cog:
```
[p]reload aurora
```

---

#### `[p]aurora global show`
**Permission**: Owner

Show all global Aurora settings.

**Output**:
- Letta base URL
- Circuit breaker configuration (failure threshold, recovery timeout, half-open attempts, current state)
- Retry configuration (max attempts, base delay, exponential base, max delay, jitter)

**Example**:
```
[p]aurora global show
```

---

## Permission Matrix

| Command | Permission Level | Scope | Affects |
|---------|-----------------|-------|---------|
| `config show` | Admin | Guild | View only |
| `config show <guild_id>` | Owner | Any Guild | View only |
| `enable` | Admin | Guild | This guild |
| `disable` | Admin | Guild | This guild |
| `setagent` | Admin | Guild | This guild |
| `global baseurl` | Owner | Bot-wide | All guilds |
| `global show` | Owner | Bot-wide | View only |

## Configuration Hierarchy

### Global Settings (Bot-Wide)
Set by bot owner, apply to all guilds:
- `letta_base_url` - Where to connect to Letta API
- Circuit breaker settings (hardcoded in `__init__`)
- Retry settings (hardcoded in `__init__`)

### Guild Settings (Per-Server)
Set by guild admins, apply to their guild only:
- `agent_id` - Which Letta agent to use
- `enabled` - Whether the agent is active
- `reply_thread_depth` - How many parent messages to fetch (1-10)
- `enable_typing_indicator` - Show typing while processing (bool)
- `enable_dm_responses` - Respond to DMs (bool)
- `mcp_guidance_enabled` - Include MCP tool hints in prompts (bool)
- `rate_limit_seconds` - Min seconds between messages (0.5-10)
- `max_queue_size` - Maximum queued messages (10-200)
- `agent_timeout` - Max execution time (10-300s)

## Typical Workflows

### Initial Setup (Bot Owner)
1. Set Letta API credentials:
   ```
   [p]set api letta token,<your_letta_token>
   ```

2. Configure base URL (if not using Letta Cloud default):
   ```
   [p]aurora global baseurl http://localhost:8283
   [p]reload aurora
   ```

3. Verify global settings:
   ```
   [p]aurora global show
   ```

### Guild Setup (Guild Admin)
1. Create a Letta agent for your guild (via Letta web interface or CLI)

2. Enable Aurora with your agent ID:
   ```
   [p]aurora enable agent-abc123def456...
   ```

3. Configure guild settings:
   ```
   [p]aurora config replydepth 3
   [p]aurora config typing true
   [p]aurora config ratelimit 2
   ```

4. Verify configuration:
   ```
   [p]aurora config show
   ```

### Changing Agents
If you want to switch to a different Letta agent:
```
[p]aurora setagent agent-new123def456...
```

This keeps all your guild settings but changes which agent is used.

### Temporary Disable
To pause Aurora without losing configuration:
```
[p]aurora disable                    # Pause for this guild
[p]aurora events pause               # Pause globally (owner only)
```

Re-enable when ready:
```
[p]aurora enable <same_agent_id>     # Resume for this guild
[p]aurora events resume              # Resume globally (owner only)
```

## Integration with Existing Commands

These new commands complement the existing command structure:

**Existing Commands**:
- `[p]aurora queue *` - Queue management (owner-only)
- `[p]aurora events *` - Event processing control (owner-only)
- `[p]aurora config replydepth/typing/etc` - Individual setting setters (admin)
- `[p]aurora context <msg_id>` - Context preview (admin)

**New Commands**:
- `[p]aurora config show` - **View all settings at once** (admin)
- `[p]aurora enable/disable/setagent` - **Agent lifecycle management** (admin)
- `[p]aurora global *` - **Bot-wide settings** (owner-only)

## Migration Notes

**No breaking changes.** These are purely additive commands.

Guilds that already have `agent_id` and `enabled` configured will continue working exactly as before. The new commands provide a cleaner interface for managing these settings.

## Future Enhancements

Potential additions (not implemented):
- `[p]aurora config import <file>` - Import configuration from JSON
- `[p]aurora config export` - Export configuration to JSON
- `[p]aurora agent test` - Send a test message to verify agent is working
- `[p]aurora global circuitbreaker <settings>` - Configure circuit breaker thresholds
- `[p]aurora global retry <settings>` - Configure retry behavior

## Testing Checklist

- [ ] `config show` displays correct settings for current guild
- [ ] `config show <guild_id>` works for owner in other guilds
- [ ] `config show <guild_id>` denies access for non-owners
- [ ] `enable` sets agent_id and enabled=true
- [ ] `enable` starts synthesis task when Letta is ready
- [ ] `disable` sets enabled=false and stops task
- [ ] `setagent` updates agent ID and restarts task
- [ ] `global baseurl` with no args shows current URL
- [ ] `global baseurl <url>` validates and sets new URL
- [ ] `global show` displays all global settings
- [ ] Global commands reject non-owner users
- [ ] All commands log actions appropriately
