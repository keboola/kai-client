# Kai API Reference

## Authentication

All Kai API requests require two headers:
- `x-storageapi-token`: Keboola Storage API token
- `x-storageapi-url`: Keboola Storage API URL (e.g., `https://connection.keboola.com`)

## Client Configuration

### Production Mode (Auto-Discovery)

The Kai client automatically discovers the Kai API URL from the Keboola stack:

```python
from kai_client import KaiClient

async with await KaiClient.from_storage_api(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    response = await client.ping()
```

### Local Development Mode

For local development, specify the base URL explicitly:

```python
client = KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com",
    base_url="http://localhost:3000"
)
```

Or via environment variable:
```bash
export KAI_BASE_URL="http://localhost:3000"
```

Or CLI flag:
```bash
kai --base-url http://localhost:3000 chat -m "Hello"
```

## API Methods

### Health & Info

```python
# Check server health
response = await client.ping()
# Returns: PingResponse(timestamp="2024-01-15T10:30:00Z")

# Get server information
info = await client.info()
# Returns: InfoResponse with app_name, app_version, server_version, mcp_connections
```

### Chat Operations

#### Send Message (Streaming)

```python
async for event in client.send_message(
    chat_id="uuid",
    text="What tables do I have?",
    visibility="private",  # or "public"
):
    if isinstance(event, TextEvent):
        print(event.text, end="")
    elif isinstance(event, ToolCallEvent):
        if event.state == "input-available":
            # Tool needs approval
            pass
    elif isinstance(event, FinishEvent):
        print(f"Finished: {event.finish_reason}")
```

#### Simple Chat (Non-Streaming)

```python
chat_id, response_text = await client.chat("What tables do I have?")
```

#### Continue Existing Chat

```python
async for event in client.send_message(
    chat_id="existing-chat-id",
    text="Tell me more",
):
    # Process events
```

#### Restricting Tool Usage

Pass `tool_restrictions` to limit which tools the assistant may use. All three
fields are optional and independent:

```python
from kai_client import ToolRestrictions

async for event in client.send_message(
    chat_id="uuid",
    text="Show me my tables",
    tool_restrictions=ToolRestrictions(
        allowed_tools=["list_tables", "get_table_detail"],  # allowlist
        disallowed_tools=["run_job"],                        # denylist
        read_only_mode=True,                                 # read-only tools only
    ),
):
    # Process events
```

This serializes to `toolRestrictions: {allowedTools, disallowedTools, readOnlyMode}`
in the `POST /api/chat` request body. Restrictions are **first-message-wins**: the
backend persists them from the first message of a chat and ignores
`toolRestrictions` sent on follow-up messages of the same chat.

### Tool Approval

When the AI needs to execute operations, it sends a `ToolCallEvent` with `state="input-available"`:

```python
# Approve the tool call
async for event in client.confirm_tool(
    chat_id=chat_id,
    tool_call_id=tool_event.tool_call_id,
    tool_name=tool_event.tool_name,
):
    # Process results

# Deny the tool call
async for event in client.deny_tool(
    chat_id=chat_id,
    tool_call_id=tool_event.tool_call_id,
    tool_name=tool_event.tool_name,
):
    # Process denial response
```

### History Management

```python
# Get paginated history
history = await client.get_history(limit=10)
for chat in history.chats:
    print(f"{chat.id}: {chat.title}")

# Iterate through all history
async for chat in client.get_all_history(batch_size=100):
    print(chat.id)

# Get specific chat with messages
chat_detail = await client.get_chat(chat_id)
for message in chat_detail.messages:
    print(f"{message.role}: {message.content}")

# Delete a chat
await client.delete_chat(chat_id)
```

### Voting

```python
# Vote on a message
vote = await client.vote(chat_id, message_id, VoteType.UP)
# or
vote = await client.upvote(chat_id, message_id)
vote = await client.downvote(chat_id, message_id)

# Get all votes for a chat
votes = await client.get_votes(chat_id)
```

## Timeouts

Default timeouts:
- Regular requests: 300 seconds (5 minutes)
- Streaming requests: 600 seconds (10 minutes)

Configure custom timeouts:
```python
client = KaiClient(
    storage_api_token="token",
    storage_api_url="url",
    timeout=120,         # 2 minutes for regular requests
    stream_timeout=300,  # 5 minutes for streaming
)
```

## Exception Handling

```python
from kai_client.exceptions import (
    KaiError,
    KaiAuthenticationError,
    KaiForbiddenError,
    KaiNotFoundError,
    KaiRateLimitError,
    KaiBadRequestError,
    KaiStreamError,
    KaiConnectionError,
    KaiTimeoutError,
)

try:
    await client.send_message(chat_id, "Hello")
except KaiAuthenticationError:
    print("Invalid token")
except KaiNotFoundError:
    print("Chat not found")
except KaiRateLimitError:
    print("Too many requests")
except KaiConnectionError:
    print("Network error")
except KaiTimeoutError:
    print("Request timed out")
except KaiError as e:
    print(f"Error {e.code}: {e.message}")
```

## Data Models

### Message Parts

Messages can contain multiple parts:

- `TextPart`: Plain text content
- `ToolCallPart`: Tool invocation details
- `ToolResultPart`: Result from tool execution

### Tool Call States

- `started`: Tool call beginning
- `input-available`: Waiting for user approval
- `output-available`: Tool completed successfully
- `output-error`: Tool execution failed

### Visibility Types

- `private`: Chat visible only to creator
- `public`: Chat visible to all project members

### Tool Restrictions

`ToolRestrictions` (passed via `send_message(tool_restrictions=...)`) has three
optional fields, serialized under `toolRestrictions` on `POST /api/chat`:

- `allowed_tools` (`allowedTools`): allowlist — only these tools may be used
- `disallowed_tools` (`disallowedTools`): denylist — these tools may not be used
- `read_only_mode` (`readOnlyMode`): when `True`, only read-only tools may be used

Restrictions are **first-message-wins**: they are persisted from the first
message of a chat and ignored on follow-up messages of the same chat.

### Vote Types

- `up`: Positive feedback
- `down`: Negative feedback

## Utility Methods

```python
# Generate new UUIDs
chat_id = client.new_chat_id()
message_id = client.new_message_id()
```
