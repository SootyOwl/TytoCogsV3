# Aurora - Letta Integration for Red-DiscordBot

Aurora integrates the [Letta](https://www.letta.com/) autonomous AI agent into Red-DiscordBot, enabling dynamic, context-aware interactions within Discord servers. The agent operates autonomously, using MCP (Model Context Protocol) Discord tools to read message history and send responses directly.

## Architecture Overview

Aurora follows an **agent-centric architecture** where the Letta agent has direct control over Discord interactions through MCP tools. The cog's role is minimal:

1. **Event Detection**: Listen for bot mentions and DMs
2. **Context Enrichment**: Extract reply chains and message metadata
3. **Queue Management**: Rate-limit and queue messages to prevent overwhelming the agent
4. **Execution Monitoring**: Log agent tool calls and reasoning for debugging
5. **Error Handling**: Retry failed operations and prevent system overload

**Key Design Decision**: Aurora does NOT pre-fetch channel history or send responses on behalf of the agent. Instead, it provides the agent with IDs and minimal context, encouraging the agent to use `discord_read_messages()` to gather additional history and `discord_send()` to respond directly.

### Event Flow

```
Discord Message
    ↓
on_message Listener
    ↓
Extract Context (metadata + reply chain only)
    ↓
Build Prompt (with MCP tool guidance)
    ↓
Enqueue Event (with rate limiting & deduplication)
    ↓
Message Queue Processor
    ↓
Send to Letta Agent (with retry & circuit breaker)
    ↓
Agent Executes
    ├── Uses discord_read_messages() to gather context
    ├── Internal reasoning
    └── Uses discord_send() to respond directly
```

## External Requirements

- Self-hosted Letta instance or Letta Cloud access
- [mcp-discord](https://github.com/SootyOwl/mcp-discord) server configured in your Letta agent
- Discord bot token with message content intent enabled

## Installation

1. Install the cog:
```bash
[p]repo add tyto https://github.com/SootyOwl/TytoCogsV3
[p]cog install tyto aurora
[p]load aurora
```

2. Configure Letta API access:
```bash
[p]set api letta token,<your_letta_api_token>
[p]aurora lettaurl <your_letta_base_url>
```

3. Enable Aurora for your server:
```bash
[p]aurora enable <your_agent_id>
```

## Configuration

### Core Settings

| Setting | Command | Default | Description |
|---------|---------|---------|-------------|
| **Agent ID** | `[p]aurora enable <id>` | None | Letta agent ID for this guild |
| **Reply Depth** | `[p]aurora config replydepth <1-10>` | 5 | Maximum parent messages to fetch in reply chains |
| **Typing Indicator** | `[p]aurora config typing <true/false>` | true | Show typing while agent processes |
| **Rate Limit** | `[p]aurora config ratelimit <0.5-10>` | 2.0 | Minimum seconds between messages per channel |
| **Queue Size** | `[p]aurora config queuesize <10-200>` | 50 | Maximum queued messages |
| **Agent Timeout** | `[p]aurora config timeout <10-300>` | 60 | Maximum seconds for agent execution |
| **MCP Guidance** | `[p]aurora config mcpguidance <true/false>` | true | Include MCP tool hints in prompts |

### Configuration Best Practices

**Reply Depth**:
- Low activity servers: 5-7 (more conversation context)
- High activity servers: 2-3 (less noise)
- Support channels: 5+ (full thread history)

**Rate Limit**:
- High activity channels: 3-5 seconds (prevent spam responses)
- Low activity channels: 1-2 seconds (faster, more natural responses)

**Queue Size**:
- Small servers (<100 members): 50 (default)
- Medium servers (100-1000): 100-150
- Large servers (1000+): 150-200

**Agent Timeout**:
- Simple conversational responses: 30-60 seconds
- Complex operations (research, multi-tool use): 120-180 seconds
- Heavy analysis tasks: 180-300 seconds

## Commands Reference

See [COMMANDS.md](./COMMANDS.md) for detailed command documentation.

### Quick Command Reference

**Queue Management**:
- `[p]aurora queue status` - View queue state
- `[p]aurora queue clear` - Clear pending messages

**Event Control**:
- `[p]aurora events status` - View event system status
- `[p]aurora events pause` - Pause event processing
- `[p]aurora events resume` - Resume event processing
- `[p]aurora events errors` - View error statistics
- `[p]aurora events resetcircuit` - Reset circuit breaker

**Configuration**:
- `[p]aurora config replydepth <depth>` - Set reply chain depth
- `[p]aurora config typing <enabled>` - Toggle typing indicator
- `[p]aurora config ratelimit <seconds>` - Set rate limit
- `[p]aurora config queuesize <size>` - Set max queue size
- `[p]aurora config timeout <seconds>` - Set agent timeout
- `[p]aurora config mcpguidance <enabled>` - Toggle MCP hints

**Context Preview**:
- `[p]aurora context <message_id>` - Preview context for a message

## MCP Tool Integration

Aurora is designed to work with the `mcp-discord` server, which provides these tools to the Letta agent:

### Core Tools Used

**`discord_read_messages(channelId, limit)`**
- Agent uses this to read recent message history in a channel
- Aurora provides the `channelId` in prompts but does NOT pre-fetch history
- This allows the agent to decide how much context it needs

**`discord_send(channelId, message, replyToMessageId?)`**
- Agent uses this to send responses directly to Discord
- Aurora does NOT send responses on behalf of the agent
- Aurora only monitors execution and logs tool calls

**`discord_get_server_info(guildId)`**
- Agent can query server structure (channels, roles, members)
- Useful for understanding server context

**`discord_add_reaction(channelId, messageId, emoji)`**
- Agent can react to messages with emojis

### Why We Don't Pre-Fetch Channel History

Traditional Discord bot frameworks pre-fetch recent channel messages and include them in prompts. Aurora takes a different approach:

**Benefits of Agent-Driven Context Gathering**:
1. **Flexibility**: Agent decides how much history it needs (2 messages vs. 50)
2. **Efficiency**: Don't waste tokens on irrelevant history
3. **Scalability**: No need to track and manage channel history state
4. **Simplicity**: Cog code remains simple and focused

**What Aurora DOES Pre-Fetch**:
- **Reply chains**: Immediate conversation thread (configurable depth)
- **Message metadata**: Author, channel, guild, timestamp information

This provides enough context for the agent to understand the immediate situation, while allowing it to gather additional history as needed.

## Error Handling & Recovery

Aurora includes comprehensive error handling to ensure reliability:

### Circuit Breaker

Protects against repeated failures that could indicate Letta API issues:

**States**:
- **CLOSED (🟢)**: Normal operation
- **OPEN (🔴)**: Too many failures, blocking requests (60s cooldown)
- **HALF-OPEN (🟡)**: Testing recovery, limited requests allowed

**Configuration**:
- Failure threshold: 5 consecutive failures
- Recovery timeout: 60 seconds
- Half-open attempts: 3 test requests

**Commands**:
- `[p]aurora events status` - View circuit breaker state
- `[p]aurora events errors` - Detailed error statistics
- `[p]aurora events resetcircuit` - Manually reset (use carefully!)

### Retry Logic

Failed agent calls are automatically retried with exponential backoff:

**Configuration**:
- Max attempts: 3
- Base delay: 1 second
- Exponential base: 2x
- Max delay: 30 seconds
- Jitter: ±25% random variance

**Example retry sequence**:
1. First attempt fails → wait ~1s
2. Second attempt fails → wait ~2s
3. Third attempt fails → operation fails, circuit breaker may open

### Error Statistics

Aurora tracks detailed error statistics:
- Total operations and errors
- Error rate (overall and 5-minute window)
- Error breakdown by type
- Recent operation history

View with: `[p]aurora events errors`

### Graceful Degradation

When Letta is unavailable:
1. Circuit breaker opens after repeated failures
2. New messages are logged but not processed
3. Queue continues accepting messages (up to max size)
4. After recovery timeout, circuit enters half-open state
5. Successful requests restore normal operation

## Troubleshooting

### Agent Not Responding

**Check Status**:
```bash
[p]aurora events status
```

Look for:
- ✅ Agent enabled with valid ID
- ▶️ Event processing active (not paused)
- 🟢 Circuit breaker closed

**Common Causes**:
1. **Events Paused**: Use `[p]aurora events resume`
2. **Circuit Breaker Open**: Check `[p]aurora events errors`, wait for recovery or use `[p]aurora events resetcircuit`
3. **Invalid Agent ID**: Use `[p]aurora enable <correct_id>`
4. **MCP Tools Not Configured**: Ensure mcp-discord is set up in your Letta agent

### Queue Backing Up

**Check Queue**:
```bash
[p]aurora queue status
```

**Solutions**:
1. **Clear Queue**: `[p]aurora queue clear` (loses pending messages)
2. **Increase Queue Size**: `[p]aurora config queuesize 100`
3. **Increase Rate Limit**: `[p]aurora config ratelimit 3` (slower responses but less congestion)
4. **Check Agent Performance**: Use `[p]aurora config timeout 120` if agent is slow

### High Error Rate

**Check Errors**:
```bash
[p]aurora events errors
```

**Common Error Types**:
- **TimeoutError**: Agent taking too long → increase timeout
- **HTTPException**: Letta API issues → check Letta server status
- **NotFound**: Messages deleted during processing → normal, can ignore
- **Forbidden**: Missing Discord permissions → check bot permissions

**Actions**:
1. Review error breakdown to identify patterns
2. Check circuit breaker state
3. Review bot logs for detailed error messages
4. Verify Letta API connectivity
5. Ensure MCP Discord tools are functioning

### Context Not Including Recent Messages

**Remember**: Aurora only pre-fetches reply chains. The agent must use `discord_read_messages()` to gather additional context.

**Verify**:
1. Use `[p]aurora context <message_id>` to preview what's sent
2. Check reply depth: `[p]aurora config replydepth 7`
3. Verify MCP guidance is enabled: `[p]aurora config mcpguidance true`
4. Check agent logs to see if it's calling `discord_read_messages()`

**If agent isn't using MCP tools**:
- Ensure mcp-discord server is configured in your Letta agent
- Check that prompts include MCP guidance
- Review agent's system prompt and instructions

## Monitoring

### Key Metrics to Watch

**Queue Health**:
- Queue size should usually be near 0
- Sustained high queue size indicates processing bottleneck
- Check: `[p]aurora queue status`

**Error Rate**:
- Should be <5% under normal conditions
- >20% indicates significant issues
- >50% triggers alert logging
- Check: `[p]aurora events errors`

**Circuit Breaker**:
- Should remain CLOSED (🟢) during normal operation
- OPEN (🔴) indicates systemic failure
- HALF-OPEN (🟡) indicates recovery in progress
- Check: `[p]aurora events status`

### Recommended Monitoring Schedule

- **Daily**: Quick `[p]aurora events status` check
- **Weekly**: Review `[p]aurora events errors` for trends
- **After Changes**: Monitor for 1-2 hours after config changes
- **During Incidents**: Check status every 5-10 minutes

## Development & Testing

Aurora includes comprehensive unit tests:

```bash
pytest aurora/test_context.py aurora/test_queue.py aurora/test_prompts.py -v
```

**Test Coverage**:
- Context extraction (14 tests)
- Message queue (15 tests)
- Prompt generation (7 tests)
- **Total**: 36 tests

See test files for examples of mocking Discord objects and Letta responses.

## Architecture Decisions

### Why Agent-Centric Design?

Traditional bot frameworks tightly couple message handling with response generation. Aurora inverts this:

**Traditional Approach**:
```
Bot receives message → Bot fetches context → Bot asks LLM → Bot formats response → Bot sends response
```

**Aurora Approach**:
```
Bot receives message → Bot enriches metadata → Agent decides what context to fetch → Agent sends response
```

**Benefits**:
1. **Agent Autonomy**: Agent controls its own tool usage
2. **Simpler Code**: Cog doesn't manage response formatting or sending
3. **Better Scalability**: Agent can parallelize tool calls
4. **Flexibility**: Easy to add new MCP tools without changing cog code

### Why Only Reply Chains?

Aurora pre-fetches reply chains but not general channel history because:

1. **Immediate Context**: Reply chains provide directly relevant conversation
2. **Bounded Size**: Reply depth is limited (default: 5 messages)
3. **High Value**: Thread context has highest signal-to-noise ratio
4. **Agent Decision**: Agent can decide if it needs more history via `discord_read_messages()`

### Why Circuit Breaker?

Without a circuit breaker, Letta API outages could:
- Exhaust retry attempts on every queued message
- Create cascading delays as queue backs up
- Generate excessive error logs
- Waste resources on doomed requests

Circuit breaker provides:
- **Fast Failure**: Immediate rejection when service is known to be down
- **Automatic Recovery**: Tests service health and resumes when recovered
- **Resource Protection**: Prevents wasting retries on systemic issues

## Contributing

See the main [TytoCogsV3 README](../README.md) for contribution guidelines.

## License

See [LICENSE.md](../LICENSE.md) in the repository root.

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/SootyOwl/TytoCogsV3/issues).
