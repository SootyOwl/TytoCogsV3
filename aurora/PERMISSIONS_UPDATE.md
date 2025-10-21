# Aurora Event System - Permission Update

## Changes Made

Updated command permissions to correctly reflect that the queue and event system are **global to the bot**, not per-guild.

## Permission Structure

### Owner-Only Commands (Global Bot Operations)
These commands affect the entire bot instance across all guilds:

**`[p]aurora queue` group** - `@commands.is_owner()`
- `queue status` - View global queue statistics
- `queue clear` - Clear all pending messages from the global queue

**`[p]aurora events` group** - `@commands.is_owner()`
- `events pause` - Pause event processing globally (all guilds)
- `events resume` - Resume event processing globally
- `events status [guild_id]` - View global status + optional guild-specific config
- `events errors` - View global error statistics
- `events resetcircuit` - Reset the global circuit breaker

### Admin-Only Commands (Per-Guild Configuration)
These commands configure guild-specific settings:

**`[p]aurora config` group** - `@commands.admin_or_permissions(manage_guild=True)` (inherited)
- `config replydepth <1-10>` - Set reply thread depth for this guild
- `config typing <bool>` - Enable/disable typing indicator for this guild
- `config ratelimit <0.5-10>` - Set rate limit for this guild
- `config queuesize <10-200>` - Set max queue size (global, but configured per-guild)
- `config timeout <10-300>` - Set agent timeout for this guild
- `config mcpguidance <bool>` - Enable/disable MCP guidance in prompts for this guild

**`[p]aurora context` command** - `@commands.admin_or_permissions(manage_guild=True)` (inherited)
- `context <message_id>` - Preview context for a message (per-guild settings applied)

## Rationale

### Why Queue Commands are Owner-Only
The message queue is a **single global instance** shared across all guilds:
```python
self.queue = MessageQueue(max_size=50, rate_limit_seconds=2)
```

Operations like `queue clear` would affect messages from all guilds, making this a bot-wide operation that should only be performed by the bot owner.

### Why Event Commands are Owner-Only
Event processing control is **global state**:
```python
self._events_paused = False  # Global flag
```

When you pause events, the bot stops responding in **all guilds**, not just the current one. This is a critical operation that requires owner-level access.

### Why Config Commands Remain Admin-Only
Configuration commands modify **per-guild settings**:
```python
await self.config.guild(ctx.guild).reply_thread_depth.set(depth)
```

These settings only affect the specific guild where the command is run, so guild admins should have control over their own configuration.

## Updated Command Behavior

### `aurora events status`
Now shows global status by default, with optional guild-specific lookup:

```
[p]aurora events status              # Shows global + current guild (if any)
[p]aurora events status 123456789    # Shows global + specific guild ID
```

**Output includes:**
- Global event processing state (paused/active)
- Global queue statistics
- Global error handling status (circuit breaker, error rates)
- Guild-specific agent config and settings (if guild specified or invoked in a guild)

### `aurora events pause/resume`
Messages now clearly indicate global scope:

```
⏸️ Global event processing paused. The bot will not respond to mentions or DMs
in any server until you run `aurora events resume`.
```

## Migration Notes

**No configuration changes required.** This is purely a permission update.

Existing guild administrators will lose access to:
- `aurora queue *` commands → Now owner-only
- `aurora events *` commands → Now owner-only

Guild administrators retain access to:
- `aurora config *` commands → Still admin-only
- `aurora context` command → Still admin-only

## Testing Recommendations

1. **As bot owner**, verify you can:
   - View queue status: `[p]aurora queue status`
   - Pause/resume events: `[p]aurora events pause` / `resume`
   - View global status: `[p]aurora events status`
   - Clear queue: `[p]aurora queue clear`

2. **As guild admin** (non-owner), verify you can:
   - Configure guild settings: `[p]aurora config replydepth 3`
   - Preview context: `[p]aurora context <message_id>`
   - **Cannot** access queue/events commands (should get permission error)

3. **Test global behavior**:
   - Pause events in Guild A
   - Verify mentions in Guild B are also ignored
   - Resume events
   - Verify both guilds now respond

## Documentation Updates Needed

The following files need to be updated to reflect new permissions:

- [ ] `README.md` - Update command permissions table
- [ ] `COMMANDS.md` - Add permission level indicators
- [ ] `IMPLEMENTATION_SUMMARY.md` - Update command structure section

Example documentation format:
```markdown
| Command | Permission | Scope | Description |
|---------|-----------|-------|-------------|
| `aurora queue status` | Owner | Global | View global queue statistics |
| `aurora events pause` | Owner | Global | Pause event processing globally |
| `aurora config replydepth` | Admin | Guild | Set reply depth for this guild |
```
