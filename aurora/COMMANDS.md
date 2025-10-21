# Aurora Event System Commands

This document provides a reference for all Aurora event system management commands.

## Command Structure

All commands require admin or `Manage Server` permission and must be used in a guild (not DMs).

```
[p]aurora
├── queue
│   ├── status     - Show queue statistics
│   └── clear      - Clear pending messages
├── events
│   ├── status     - Show event system status
│   ├── pause      - Pause event processing
│   └── resume     - Resume event processing
├── config
│   ├── replydepth <depth>          - Set reply chain depth (1-10)
│   ├── typing <enabled>            - Enable/disable typing indicator
│   ├── ratelimit <seconds>         - Set rate limit (0.5-10s)
│   ├── queuesize <size>            - Set max queue size (10-200)
│   ├── timeout <seconds>           - Set agent timeout (10-300s)
│   └── mcpguidance <enabled>       - Enable/disable MCP tool hints
└── context <message_id>            - Preview context for a message
```

## Command Details

### Queue Management

#### `[p]aurora queue status`
Displays current queue state including:
- Queue size (current/max)
- Rate limit setting
- Whether events are paused
- Number of tracked channels
- Number of tracked message IDs

**Example:**
```
[p]aurora queue status
```

#### `[p]aurora queue clear`
Clears all pending messages from the queue. Useful for:
- Recovering from backlog after downtime
- Clearing queue before maintenance
- Handling spam situations

**Example:**
```
[p]aurora queue clear
```

### Event Control

#### `[p]aurora events status`
Shows comprehensive event system status:
- Agent enabled/disabled state
- Event processing (active/paused)
- Current queue size
- All configuration settings

**Example:**
```
[p]aurora events status
```

#### `[p]aurora events pause`
Temporarily pauses event processing. The bot will:
- Stop responding to mentions and DMs
- Continue queuing synthesis tasks (if enabled)
- Keep the queue intact

Useful for:
- Temporary maintenance
- Rate limiting issues
- Testing other features

**Example:**
```
[p]aurora events pause
```

#### `[p]aurora events resume`
Resumes event processing after being paused.

**Example:**
```
[p]aurora events resume
```

### Configuration

#### `[p]aurora config replydepth <depth>`
Sets maximum number of parent messages to fetch in reply chains.

**Parameters:**
- `depth`: Integer between 1-10 (default: 5)

**Example:**
```
[p]aurora config replydepth 3
```

#### `[p]aurora config typing <enabled>`
Enable or disable typing indicator while the agent processes messages.

**Parameters:**
- `enabled`: `true` or `false` (default: true)

**Example:**
```
[p]aurora config typing false
```

#### `[p]aurora config ratelimit <seconds>`
Sets minimum time between processing messages from the same channel.

**Parameters:**
- `seconds`: Float between 0.5-10 (default: 2)

**Example:**
```
[p]aurora config ratelimit 3.5
```

**Note:** Takes effect immediately for the queue.

#### `[p]aurora config queuesize <size>`
Sets maximum number of messages that can be queued per guild.

**Parameters:**
- `size`: Integer between 10-200 (default: 50)

**Example:**
```
[p]aurora config queuesize 100
```

**Note:** Requires cog reload to take effect.

#### `[p]aurora config timeout <seconds>`
Sets maximum execution time for agent operations.

**Parameters:**
- `seconds`: Integer between 10-300 (default: 60)

**Example:**
```
[p]aurora config timeout 120
```

#### `[p]aurora config mcpguidance <enabled>`
Enable or disable MCP tool usage hints in prompts sent to the agent.

**Parameters:**
- `enabled`: `true` or `false` (default: true)

When enabled, prompts include guidance about using:
- `discord_read_messages()` for reading channel history
- `discord_send()` for sending responses

**Example:**
```
[p]aurora config mcpguidance true
```

### Context Preview

#### `[p]aurora context <message_id>`
Preview what context would be sent to the agent for a specific message.

**Parameters:**
- `message_id`: Discord message ID (must be in the current channel)

Shows:
- Message metadata (author, channel, timestamp)
- Reply chain length
- Generated prompt (truncated)
- Full prompt length

Useful for:
- Debugging context extraction
- Understanding what the agent sees
- Testing reply chain extraction

**Example:**
```
[p]aurora context 1234567890123456789
```

## Configuration Defaults

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `reply_thread_depth` | 5 | 1-10 | Parent messages to fetch |
| `enable_typing_indicator` | true | bool | Show typing while processing |
| `enable_dm_responses` | true | bool | Respond to DMs |
| `max_queue_size` | 50 | 10-200 | Max queued messages |
| `agent_timeout` | 60 | 10-300 | Max agent execution time (s) |
| `mcp_guidance_enabled` | true | bool | Include MCP tool hints |
| `rate_limit_seconds` | 2 | 0.5-10 | Min time between messages (s) |

## Best Practices

### Queue Management
- Monitor `[p]aurora queue status` regularly during high-traffic periods
- Clear the queue before performing cog maintenance
- Adjust `queuesize` based on your server's typical message volume

### Event Control
- Use `pause` during bot updates or when testing other features
- Always `resume` after maintenance to restore functionality

### Configuration
- Start with default settings and adjust based on observed behavior
- Increase `ratelimit` if the bot is responding too frequently
- Increase `timeout` if agent operations frequently time out
- Disable `mcpguidance` if prompts are getting too long

### Context Preview
- Use `context` to verify reply chains are being extracted correctly
- Check that MCP guidance is present when enabled
- Verify metadata includes all expected fields

## Troubleshooting

### Queue is full
- Run `[p]aurora queue clear` to empty the queue
- Consider increasing `queuesize` if this happens frequently
- Check if event processing is paused

### Bot not responding
- Verify events are not paused: `[p]aurora events status`
- Check agent is enabled for the guild
- Review logs for errors

### Rate limiting issues
- Increase `rate_limit_seconds` to slow down responses
- Clear queue to stop pending messages
- Temporarily pause events if needed

### Context seems incomplete
- Increase `reply_thread_depth` to fetch more parent messages
- Use `[p]aurora context <message_id>` to preview what's being sent
- Check logs for errors during context extraction
