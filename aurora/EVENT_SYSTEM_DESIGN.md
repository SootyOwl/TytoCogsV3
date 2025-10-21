# Aurora Event System Design

## Overview

The Aurora event system enables the Letta-powered agent to respond intelligently to Discord messages by providing rich context and managing asynchronous message processing. The system is designed to work seamlessly with Letta's MCP Discord tools, which handle most Discord interactions server-side.

## Architecture Principles

1. **Stateful Agent**: Aurora leverages Letta's stateful architecture - conversation history is maintained server-side
2. **Context-Rich Prompts**: Each event includes relevant Discord context to help the agent make informed decisions
3. **MCP Tool Guidance**: Prompts include hints about available MCP Discord tools for the agent to gather additional context
4. **Async Processing**: Messages are queued and processed asynchronously to prevent blocking
5. **Graceful Degradation**: System handles errors and service interruptions elegantly

## Event Flow

```
Discord Message → Event Detection → Context Enrichment → Queue → Process → Letta Agent → Response → Discord
```

### 1. Event Detection (`on_message` listener)

**Triggers:**
- Bot is @mentioned in a server channel
- Direct message to the bot
- (Optional) Direct reply to bot's previous message

**Initial Checks:**
- Ignore messages from bots (including self)
- Verify agent is enabled for the guild
- Check if message triggers Red-DiscordBot commands (skip if so)
- Verify Letta client is initialized

### 2. Context Enrichment

Before sending to the agent, enrich the message with:

#### A. Message Metadata
```python
{
    "message_id": str,
    "timestamp": datetime,
    "author": {
        "id": str,
        "username": str,
        "display_name": str,
        "roles": list[str],  # server roles
        "is_bot": bool
    },
    "channel": {
        "id": str,
        "name": str,
        "type": "text" | "dm" | "thread" | "voice",
    },
    "guild": {
        "id": str,
        "name": str
    } | None  # None for DMs
}
```

#### B. Reply Chain Context

If message is a reply, fetch the immediate parent for context:
```python
async def extract_reply_context(message: discord.Message, max_depth: int = 5) -> list[dict]:
    """
    Recursively fetch parent messages up to max_depth to provide thread context.
    The agent can use discord_read_message() MCP tool for deeper exploration.
    Returns chronologically ordered list (oldest first).
    """
    chain = []
    current = message.reference
    depth = 0

    while current and depth < max_depth:
        try:
            parent = await message.channel.fetch_message(current.message_id)
            chain.insert(0, {
                "message_id": str(parent.id),
                "author": parent.author.display_name,
                "content": parent.content,
                "timestamp": parent.created_at.isoformat(),
                "is_bot": parent.author.bot
            })
            current = parent.reference
            depth += 1
        except (discord.NotFound, discord.Forbidden):
            break

    return chain
```

**Note:** We don't fetch recent channel history here because the agent can use its `discord_read_messages()` MCP tool to gather that context as needed. This approach:
- Reduces unnecessary API calls
- Gives the agent control over how much context it needs
- Avoids duplicate context gathering
- Keeps prompts focused and minimal

### 3. Prompt Construction

Build a context-aware prompt based on event type:

#### Server Channel Mention
```
You received a mention or reply on Discord from {author.display_name} ({author.id})

**Context:**
- Server: {guild.name}
- Channel: #{channel.name} (ID: {channel.id})
- Mentioned by: {author.display_name} ({author.roles})
- Time: {timestamp}
- Message ID: {message.id}

**Reply Thread:** (if applicable)
{format_reply_chain(reply_chain)}

**Current Message (the mention you're responding to):**
{author.display_name}: {message.content}

**Available Tools:**
You have access to MCP Discord tools to gather context as needed:
- discord_read_messages(channelId, limit): Read recent channel messages for context
- discord_get_server_info(guildId): Get detailed server information including channels
- discord_send(channelId, message, replyToMessageId): Send messages to channels, optionally as a reply
- discord_add_reaction(channelId, messageId, emoji): React to messages

To reply, use the discord_send tool:
- Each call creates a new message in the channel
- Use replyToMessageId to reply directly to a specific message
- For most responses, a single call is sufficient
- Only use multiple calls if absolutely necessary:
    * You are replying to multiple messages in the context from multiple users
```

#### Direct Message
```
You received a direct message on Discord.

**From:** {author.display_name} (User ID: {author.id})
**Channel (DM) ID:** {channel.id}
**Time:** {timestamp}
**Message ID:** {message.id}

**Current Message:**
{message.content}

**Available Tools:**
- discord_read_messages(channelId, limit): Review your DM conversation history
- discord_send(channelId, message, replyToMessageId): Send a message in this DM channel

To reply, use the discord_send tool:
- Each call creates a new message in the DM channel
- Use replyToMessageId to reply directly to a specific message if needed
- For most responses, a single call is sufficient
- Only use multiple calls if absolutely necessary:
    * You are replying to multiple messages in the context
```

### 4. Message Queue System

**Purpose:** Prevent overwhelming the Letta agent with concurrent requests and implement rate limiting.

```python
from asyncio import Queue, Lock
from collections import defaultdict
from datetime import datetime, timedelta

class MessageQueue:
    """Manages incoming Discord messages for agent processing."""

    def __init__(self, max_size: int = 50):
        self.queue: Queue = Queue(maxsize=max_size)
        self.processing_lock: Lock = Lock()
        self.last_processed: dict[int, datetime] = defaultdict(lambda: datetime.min)
        self.rate_limit_seconds: int = 2  # Minimum seconds between messages per channel

    async def enqueue(self, event: dict) -> bool:
        """Add event to queue. Returns False if queue is full."""
        try:
            self.queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            log.warning(f"Message queue full, dropping event: {event['message_id']}")
            return False

    async def can_process(self, channel_id: int) -> bool:
        """Check if enough time has passed since last message from this channel."""
        last = self.last_processed[channel_id]
        elapsed = datetime.now() - last
        return elapsed.total_seconds() >= self.rate_limit_seconds

    async def dequeue(self) -> dict:
        """Get next event from queue (blocks if empty)."""
        return await self.queue.get()
```

**Event Structure:**
```python
{
    "event_type": "mention" | "dm",
    "message": discord.Message,
    "context": {
        "metadata": {...},
        "reply_chain": [...],  # Only immediate reply thread
    },
    "prompt": str,  # Pre-constructed prompt with MCP tool guidance
    "timestamp": datetime,
    "guild_id": int | None,
    "channel_id": int,
}
```

### 5. Message Processor Worker

Background task that processes queued messages:

```python
@tasks.loop(seconds=1)
async def process_message_queue(self):
    """Worker that processes messages from the queue."""
    if not self.letta or self.queue.empty():
        return

    try:
        event = await self.queue.dequeue()
        channel_id = event["channel_id"]

        # Rate limiting check
        if not await self.queue.can_process(channel_id):
            # Re-queue event for later
            await self.queue.enqueue(event)
            await asyncio.sleep(1)
            return

        guild_id = event.get("guild_id")
        if guild_id:
            agent_id = await self.config.guild_from_id(guild_id).agent_id()
        else:
            # DM handling - use global agent or user-specific agent
            agent_id = await self.config.dm_agent_id()

        if not agent_id:
            log.warning(f"No agent configured for event: {event['message_id']}")
            return

        # Show typing indicator while agent processes
        message: discord.Message = event["message"]
        async with message.channel.typing():
            # Send to Letta agent and monitor execution
            await self.send_to_agent(agent_id, event["prompt"])

        # Update last processed timestamp
        self.queue.last_processed[channel_id] = datetime.now()

    except Exception as e:
        log.exception(f"Error processing message from queue: {e}")
```

### 6. Agent Communication

The agent responds directly to Discord via MCP tools - the cog just monitors execution:

```python
async def send_to_agent(
    self,
    agent_id: str,
    prompt: str
):
    """
    Send enriched prompt to Letta agent and monitor execution.
    The agent will use discord_send() MCP tool to respond directly.
    """
    try:
        stream = self.letta.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[MessageCreate(role="user", content=prompt)],
            stream_tokens=False,  # Get complete chunks, not token-by-token
            max_steps=50,  # Prevent infinite loops
        )

        # Monitor agent execution for logging/debugging
        tool_calls = []
        async for chunk in stream:
            match chunk.message_type:
                case "reasoning_message":
                    # Log internal reasoning for debugging
                    if chunk.reasoning:
                        log.debug(f"Agent reasoning: {chunk.reasoning}")

                case "tool_call_message":
                    # Track tool usage
                    if chunk.tool_call and chunk.tool_call.name:
                        tool_calls.append(chunk.tool_call.name)
                        log.info(f"Agent calling tool: {chunk.tool_call.name}")

                case "tool_return_message":
                    # Log tool results
                    if chunk.status == "success":
                        log.debug(f"Tool {chunk.name} succeeded")
                    else:
                        log.warning(f"Tool {chunk.name} failed: {chunk.stderr}")

                case "assistant_message":
                    # Agent may have internal thoughts not sent to Discord
                    if chunk.content:
                        log.debug(f"Agent internal message: {chunk.content[:100]}...")

                case None:
                    if str(chunk) == "done":
                        log.info(f"Agent execution completed. Tools used: {', '.join(set(tool_calls))}")
                        break

    except Exception as e:
        log.exception(f"Error during agent execution for agent {agent_id}: {e}")
        raise
```

**Key Insight:** The agent uses `discord_send(channelId, message)` to respond directly to Discord. The cog's role is to:
1. Detect Discord events (mentions, DMs)
2. Build context-rich prompts
3. Send prompts to the agent
4. Monitor execution for logging/debugging
5. Handle errors

The cog does **NOT** need to:
- ❌ Parse and extract assistant responses
- ❌ Format messages for Discord (agent handles this)
- ❌ Handle Discord character limits (agent can split messages itself)
- ❌ Send replies (agent does this via MCP tools)

## Configuration Schema

```python
default_guild = {
    "agent_id": None,
    "enabled": False,
    # Event system settings
    "reply_thread_depth": 5,  # Max parent messages to fetch in reply chains
    "enable_typing_indicator": True,
    "enable_dm_responses": True,  # Respond to DMs
    "max_queue_size": 50,
    "agent_timeout": 60,  # Max seconds for agent execution
    "mcp_guidance_enabled": True,  # Include MCP tool hints in prompts
    "rate_limit_seconds": 2,  # Min seconds between messages per channel
}
```

## Error Handling Strategy

1. **Letta API Errors:**
   - Retry with exponential backoff (max 3 retries)
   - Log error details for debugging
   - Send user-friendly error message to Discord
   - Circuit breaker after repeated failures

2. **Discord API Errors:**
   - Handle rate limits gracefully
   - Retry failed message sends
   - Log permission errors

3. **Queue Overflow:**
   - Log dropped messages
   - Optionally notify admins
   - Consider increasing queue size

4. **Context Gathering Failures:**
   - Gracefully degrade to sending message without context
   - Log what failed for debugging

## MCP Tool Integration

The agent has access to MCP Discord tools (via `mcp-discord` server from SootyOwl/mcp-discord#dev). The event system should:

1. **Include Tool Hints:** Prompts should mention relevant MCP tools the agent can use
2. **Tool Availability:** Check which tools are actually enabled for the agent

**Available MCP Discord Tools (relevant for Aurora):**

**Message & Context Tools:**
- `discord_search_messages(guildId, ...)`: Powerful message history querying system
- `discord_read_messages(channelId, limit)`: Read up to 100 messages from a channel (default: 50)
- `discord_send(channelId, message)`: Send a message to a channel
- `discord_delete_message(channelId, messageId, reason)`: Delete a specific message

**Server & Channel Info:**
- `discord_get_server_info(guildId)`: Get detailed server info including channels, member count, features
- `discord_list_servers()`: List all servers the bot is in

**Reactions:**
- `discord_add_reaction(channelId, messageId, emoji)`: Add a single emoji reaction
- `discord_add_multiple_reactions(channelId, messageId, emojis)`: Add multiple reactions at once
- `discord_remove_reaction(channelId, messageId, emoji, userId)`: Remove a specific reaction

**Forum Tools:**
- `discord_get_forum_channels(guildId)`: List forum channels in a server
- `discord_create_forum_post(forumChannelId, title, content, tags)`: Create a new forum post
- `discord_get_forum_post(threadId)`: Get details about a forum post
- `discord_reply_to_forum(threadId, message)`: Reply to a forum post
- `discord_delete_forum_post(threadId, reason)`: Delete a forum post

**Channel Management:**
- `discord_create_text_channel(guildId, channelName, topic, reason)`: Create a new text channel
- `discord_delete_channel(channelId, reason)`: Delete a channel
- `discord_create_category(guildId, name, position, reason)`: Create a channel category
- `discord_edit_category(categoryId, name, position, reason)`: Edit a category
- `discord_delete_category(categoryId, reason)`: Delete a category

**Webhooks:**
- `discord_create_webhook(channelId, name, avatar, reason)`: Create a webhook
- `discord_send_webhook_message(webhookId, webhookToken, content, username, avatarURL, threadId)`: Send via webhook
- `discord_edit_webhook(webhookId, webhookToken, name, avatar, channelId, reason)`: Edit a webhook
- `discord_delete_webhook(webhookId, webhookToken, reason)`: Delete a webhook

**Guidance Examples for Prompts:**
- "Use `discord_read_messages(channelId, limit)` to get recent conversation context"
- "You can react to messages with `discord_add_reaction(channelId, messageId, emoji)`"
- "Get server details with `discord_get_server_info(guildId)`"

**Tool Call Tracking:** Log which tools the agent uses to understand behavior patterns

## Performance Considerations

1. **Rate Limiting:** Prevent API abuse and respect Discord/Letta limits
2. **Caching:** Cache recent messages/context to reduce API calls
3. **Batch Processing:** Consider batching multiple mentions in quick succession
4. **Memory Management:** Clear old queue entries, limit context size
5. **Async Operations:** Use asyncio efficiently to prevent blocking

## Testing Strategy

1. **Unit Tests:**
   - Context extraction utilities
   - Prompt construction
   - Message splitting logic
   - Queue operations

2. **Integration Tests:**
   - Mock Discord messages
   - Mock Letta responses
   - End-to-end event flow

3. **Load Tests:**
   - Queue behavior under high volume
   - Rate limiting effectiveness
   - Memory usage over time

## Future Enhancements

1. **Smart Context Selection:** Use embeddings to find most relevant past messages
2. **Conversation Threading:** Maintain separate contexts for different conversation threads
3. **Proactive Engagement:** Agent initiates conversations based on channel activity patterns
4. **Multi-Agent Collaboration:** Multiple agents in same server with role differentiation
5. **Learning from Reactions:** Use Discord reactions as feedback for agent improvement
6. **Voice Channel Integration:** Transcribe and respond to voice messages

## Implementation Checklist

- [ ] Create `context.py` module with metadata and reply chain extraction
- [ ] Create `queue.py` module with MessageQueue implementation
- [ ] Create `prompts.py` module with prompt templates (emphasizing MCP tool usage)
- [ ] Implement `on_message` event handler in `aurora.py`
- [ ] Implement message processor worker in `aurora.py`
- [ ] Add configuration options to Config schema
- [ ] Create admin commands for event system management
- [ ] Add comprehensive error handling
- [ ] Write unit tests for all modules
- [ ] Write integration tests
- [ ] Update README.md with event system documentation
- [ ] Add inline documentation and docstrings

## Key Simplifications

Since the Letta agent has `mcp-discord` tools with direct Discord API access:

1. **No pre-fetching channel history** - The agent uses `discord_read_messages()` when needed
2. **Minimal context in prompts** - Just metadata and reply thread, not full conversation
3. **Agent-driven context gathering** - The agent decides what additional context it needs
4. **Reduced API calls** - We only fetch what's absolutely necessary (reply chains)
5. **Clearer guidance** - Prompts explicitly suggest using MCP tools for context
6. **No response handling** - Agent responds directly via `discord_send()` MCP tool
7. **Simplified cog role** - Just detect events, enrich context, send to agent, monitor execution
