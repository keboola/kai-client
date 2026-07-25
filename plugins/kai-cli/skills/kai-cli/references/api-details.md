# Kai API Reference

## Authentication

All Kai API requests require two headers:
- `x-storageapi-token`: Keboola Storage API token
- `x-storageapi-url`: Keboola Storage API URL (e.g., `https://connection.keboola.com`)

## Client Configuration

### Production Mode (Auto-Discovery)

The Kai client automatically discovers the Kai API URL from the Keboola stack
(defaults to the **kai-agent** backend):

```python
from kai_client import KaiClient, KaiBackend

# Defaults to kai-agent
async with await KaiClient.from_storage_api(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com",
) as client:
    response = await client.ping()

# Legacy backend (single-tenant deployments only)
client = await KaiClient.from_storage_api(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com",
    service=KaiBackend.ASSISTANT,
)
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

Select the backend for auto-discovery (default `agent`):
```bash
kai --service assistant chat -m "Hello"   # legacy backend
```

The flag also reads the `KAI_SERVICE` environment variable and accepts the full
service ids (`kai-agent`, `kai-assistant`). It is ignored when `--base-url` is
given.

### Backend Support

Supported against **kai-agent** (the default): `ping`, `info`, `send_message`,
`chat`, `submit_approval`, `get_chat`, `delete_chat`, `get_history` /
`get_all_history`, `get_votes` / `vote` / `upvote` / `downvote`, `get_usage`,
`get_settings` / `update_settings` / `get_user_settings` /
`update_user_settings`, `get_tools`, `get_suggestions`.

**Not supported by kai-agent** — these use the older Vercel-AI-SDK-v6 /
tool-result protocols and only work against the legacy kai-assistant backend:
`send_tool_approval_response`, `approve_tool`, `reject_tool`, `send_tool_result`,
`confirm_tool`, `deny_tool`, `resume_stream`.

This split is derived from the kai-agent route surface and the protocol notes
carried by the methods themselves; only `ping` has been confirmed against a live
kai-agent deployment, so treat individual entries as expected rather than
individually verified.

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

### Tool Approval

When the AI needs to execute a write operation, it sends a `ToolCallEvent` with
`state="input-available"`. On **kai-agent** the stream stays open and blocked
until the decision is submitted, so call `submit_approval` from inside the
streaming loop — the same stream then continues with the tool output:

```python
async for event in client.send_message(chat_id, "Create a bucket"):
    if event.type == "tool-call" and event.state == "input-available":
        await client.submit_approval(
            chat_id=chat_id,
            tool_use_id=event.tool_call_id,  # the toolCallId of that event
            approved=True,                   # False to deny
            # reason="Not right now",
        )
```

`submit_approval` is a plain POST (not a stream) and returns an
`ApprovalResponse`. Read-only tools the backend runs on its own also pass
through `input-available`; submitting an approval for one of them returns a
"no pending approval" error that is safe to ignore.

On the legacy **kai-assistant** backend the first stream ends instead, and the
reply is sent with `approve_tool` / `reject_tool` (v6 flow, using the
`approval_id` from the `tool-approval-request` event) or `confirm_tool` /
`deny_tool` (older tool-result flow). Each of those returns a new stream. None
of them work against kai-agent.

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

### Vote Types

- `up`: Positive feedback
- `down`: Negative feedback

## Utility Methods

```python
# Generate new UUIDs
chat_id = client.new_chat_id()
message_id = client.new_message_id()
```
