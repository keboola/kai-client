# Kai Client

A Python client library for interacting with the Keboola AI Assistant Backend API. This library provides async support, SSE streaming, and comprehensive type safety through Pydantic models.

## Features

- **Command-line interface** for quick interactions without writing code
- **Async/await support** using `httpx`
- **Server-Sent Events (SSE) streaming** for real-time chat responses
- **Type-safe models** with Pydantic v2
- **Comprehensive error handling** with custom exception classes
- **Session management** for chat conversations
- **Full API coverage** including chat, history, and voting endpoints

## Installation

### Using uv (recommended)

```bash
uv add kai-client
```

### Using pip

```bash
pip install kai-client
```

### From source

```bash
git clone https://github.com/keboola/kai-client.git
cd kai-client
uv sync
```

## Breaking changes in 0.13.0

Two intentional breaking changes ship in this release:

1. **`from_storage_api()` discovers `kai-agent` instead of `kai-assistant`.**
   The modern agent backend is now the default. To keep connecting to the legacy
   backend (single-tenant deployments only), pass the `service` argument:

   ```python
   from kai_client import KaiBackend, KaiClient

   client = await KaiClient.from_storage_api(
       storage_api_token="your-token",
       storage_api_url="https://connection.keboola.com",
       service=KaiBackend.ASSISTANT,  # restores the pre-0.13.0 target
   )
   ```

   The `kai` CLI follows the same default; use `kai --service assistant ...`
   (or `KAI_SERVICE=assistant`) for the legacy backend.

2. **`service`, `timeout` and `stream_timeout` are keyword-only.** A previously
   legal positional call such as `from_storage_api(token, url, 60.0)` now raises
   `TypeError`; pass `timeout=60.0` instead.

Tool approvals on kai-agent use `submit_approval()`; the older `approve_tool` /
`reject_tool` / `confirm_tool` / `deny_tool` methods remain for kai-assistant.
See [Backend Support](#backend-support).

## Quick Start

```python
import asyncio
from kai_client import KaiClient

async def main():
    # Production: Auto-discover the kai-agent URL from your Keboola stack
    client = await KaiClient.from_storage_api(
        storage_api_token="your-keboola-token",
        storage_api_url="https://connection.keboola.com"  # Your stack URL
    )

    async with client:
        # Check server health
        ping = await client.ping()
        print(f"Server time: {ping.timestamp}")

        # Start a new chat
        chat_id = client.new_chat_id()

        # Send a message and stream the response
        async for event in client.send_message(chat_id, "What can you help me with?"):
            if event.type == "text":
                print(event.text, end="", flush=True)
            elif event.type == "tool-call":
                print(f"\n[Calling tool: {event.tool_name}]")
            elif event.type == "finish":
                print(f"\n[Finished: {event.finish_reason}]")

asyncio.run(main())
```

## Command-Line Interface

The package includes a `kai` CLI for quick interactions without writing code.

### Setup

Set your credentials as environment variables:

```bash
export STORAGE_API_TOKEN="your-keboola-token"
export STORAGE_API_URL="https://connection.keboola.com"
```

The CLI also auto-loads a `.env.local` file from the current directory if present, so you can put your credentials there instead:

```bash
# .env.local
STORAGE_API_TOKEN=your-keboola-token
STORAGE_API_URL=https://connection.keboola.com
```

### Commands

#### Health & Info

```bash
kai ping              # Check if the server is alive
kai info              # Show server version, uptime, connected MCP servers
kai --version         # Show CLI version
```

#### Chat

```bash
# Start an interactive chat session
kai chat

# Send a single message (non-interactive)
kai chat -m "What tables do I have?"

# Continue an existing conversation
kai chat --chat-id <chat-id> -m "Tell me more about that"

# Auto-approve tool calls (skips interactive confirmation prompts)
kai chat --auto-approve -m "Create a bucket called test-bucket"

# Output raw JSON events (useful for scripting and piping)
kai chat --json-output -m "List my tables"
```

In interactive mode, type your messages and press Enter. Type `exit`, `quit`, or press Ctrl+C to end.

**Tool approval:** When Kai calls a write tool (e.g., `update_descriptions`, `run_job`, `create_config`), the CLI pauses and asks you to approve or deny. Use `--auto-approve` to skip this prompt.

#### History & Chat Management

```bash
# View recent chat history (default: 10)
kai history

# Show more chats
kai history -n 25

# Output history as JSON
kai history --json-output

# Get full details of a specific chat (including messages)
kai get-chat <chat-id>
kai get-chat <chat-id> --json-output

# Delete a chat (prompts for confirmation)
kai delete-chat <chat-id>

# Delete without confirmation
kai delete-chat <chat-id> -y
```

#### Voting

```bash
# Vote on a message
kai vote <chat-id> <message-id> up
kai vote <chat-id> <message-id> down

# Get votes for a chat
kai get-votes <chat-id>
kai get-votes <chat-id> --json-output
```

### Global Options

These options apply to all commands:

```bash
# Pass credentials directly (instead of env vars)
kai --token "your-token" --url "https://connection.keboola.com" ping

# Use a custom base URL for local development
kai --base-url http://localhost:3000 chat -m "Hello"

# Choose which backend to auto-discover (default: agent)
kai --service assistant chat -m "Hello"   # legacy backend
KAI_SERVICE=assistant kai chat -m "Hello" # same, via env var

# Pin Kai's queries to a specific workspace (e.g. a Data App's own WORKSPACE_ID)
kai --workspace-id "12345" chat -m "What tables can I see?"
```

`--service` accepts `agent` / `assistant` (or the full service ids `kai-agent` /
`kai-assistant`) and is read from `KAI_SERVICE` when not passed. It is ignored
when `--base-url` is given, since that skips discovery entirely.

`--workspace-id` also reads the `WORKSPACE_ID` env var, which Keboola already injects into
Data App containers — so inside a Data App you typically don't need to pass it explicitly.

### Help

```bash
kai --help              # General help
kai chat --help         # Command-specific help
kai history --help
```

### Local Development vs Production

| Setting | Local Dev | Production |
|---------|-----------|------------|
| Base URL | `http://localhost:3000` | Auto-discovered |
| Setup | Manual `base_url` parameter | Use `from_storage_api()` |

```python
# Local development (explicit base_url)
client = KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com",
    base_url="http://localhost:3000"
)

# Production (auto-discovers kai-agent URL)
client = await KaiClient.from_storage_api(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
)
```

## Usage Examples

### Simple Chat (Non-Streaming)

```python
async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    # Simple one-shot conversation
    chat_id, response = await client.chat("What is 2 + 2?")
    print(response)
```

### Continuing a Conversation

```python
async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    # Create a chat session
    chat_id = client.new_chat_id()

    # First message
    async for event in client.send_message(chat_id, "Hello!"):
        if event.type == "text":
            print(event.text, end="")
    print()

    # Continue the conversation (reuse same chat_id)
    async for event in client.send_message(chat_id, "What did I just say?"):
        if event.type == "text":
            print(event.text, end="")
    print()
```

### Handling Tool Calls

```python
async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    chat_id = client.new_chat_id()

    async for event in client.send_message(chat_id, "List my Keboola tables"):
        match event.type:
            case "text":
                print(event.text, end="")
            case "step-start":
                print("\n--- New step ---")
            case "tool-call":
                if event.state == "input-available":
                    print(f"\n[Calling {event.tool_name} with {event.input}]")
                elif event.state == "output-available":
                    print(f"\n[{event.tool_name} returned: {event.output}]")
            case "finish":
                print(f"\n[Done: {event.finish_reason}]")
```

### Restricting Tool Usage

Pass `tool_restrictions` to limit which tools the assistant may use. All three
fields are optional and independent — provide any combination:

```python
from kai_client import KaiClient, ToolRestrictions

async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    chat_id = client.new_chat_id()

    async for event in client.send_message(
        chat_id,
        "Show me my tables",
        tool_restrictions=ToolRestrictions(
            allowed_tools=["list_tables", "get_table_detail"],  # allowlist
            disallowed_tools=["run_job"],                        # denylist
            read_only_mode=True,                                 # read-only tools only
        ),
    ):
        if event.type == "text":
            print(event.text, end="")
```

Restrictions serialize to `toolRestrictions: {allowedTools, disallowedTools, readOnlyMode}`
on `POST /api/chat`. They are **first-message-wins**: the backend persists the
restrictions from the first message of a chat and silently ignores
`tool_restrictions` sent on follow-up messages of the same chat.

### Chat History

```python
async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    # Get recent chats
    history = await client.get_history(limit=20)
    for chat in history.chats:
        print(f"Chat {chat.id}: {chat.title}")

    # Iterate through all history
    async for chat in client.get_all_history():
        print(f"Chat: {chat.title}")

    # Get full chat details with messages
    chat_detail = await client.get_chat(chat_id="some-chat-id")
    for message in chat_detail.messages:
        print(f"{message.role}: {message.parts}")
```

### Voting on Messages

```python
async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    # Upvote a helpful response
    await client.upvote(chat_id="chat-uuid", message_id="message-uuid")

    # Or downvote
    await client.downvote(chat_id="chat-uuid", message_id="message-uuid")

    # Get all votes for a chat
    votes = await client.get_votes(chat_id="chat-uuid")
```

### Tool Approval for Write Operations

Some tools (like `update_descriptions`, `run_job`, `create_config`) require
explicit approval before execution. On **kai-agent** (the default backend) a
tool waiting for approval appears as a `tool-call` event in the
`input-available` state, and the stream stays open — and blocked — until you
POST the decision with `submit_approval()`. So the decision has to be made from
*inside* the streaming loop; the same stream then delivers the tool output and
the rest of the answer.

```python
from kai_client import KaiClient

client = await KaiClient.from_storage_api(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com",
)

async with client:
    chat_id = client.new_chat_id()

    async for event in client.send_message(chat_id, "Create a new bucket"):
        if event.type == "text":
            print(event.text, end="")
        elif event.type == "tool-call":
            if event.state == "input-available":
                print(f"\nTool {event.tool_name} needs approval: {event.input}")
                # Unblocks this stream; iteration continues with the result.
                await client.submit_approval(
                    chat_id=chat_id,
                    tool_use_id=event.tool_call_id,
                    approved=True,          # False to deny
                    # reason="Not right now",
                )
            elif event.state == "output-available":
                print(f"\nTool {event.tool_name} completed")
```

Note that read-only tools the backend executes on its own also pass through
`input-available`; submitting an approval for one of those returns a "no pending
approval" error, which is safe to ignore.

On the legacy **kai-assistant** backend the flow is different: the first stream
ends, the server emits a separate `tool-approval-request` event carrying an
`approval_id`, and you reply with `approve_tool()` / `reject_tool()` (or
`confirm_tool()` / `deny_tool()` on older deployments), each of which returns a
new stream.

### Using SSE Stream Parser

```python
from kai_client import KaiClient, SSEStreamParser

async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    parser = SSEStreamParser()
    chat_id = client.new_chat_id()

    async for event in client.send_message(chat_id, "Hello!"):
        parser.process_event(event)

    # Access accumulated data
    print(f"Full response: {parser.text}")
    print(f"Tool calls: {parser.tool_calls}")
    print(f"Finished: {parser.finished}")
```

### Error Handling

```python
from kai_client import (
    KaiClient,
    KaiError,
    KaiAuthenticationError,
    KaiRateLimitError,
    KaiNotFoundError,
)

async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    try:
        async for event in client.send_message("chat-id", "Hello"):
            print(event)
    except KaiAuthenticationError as e:
        print(f"Authentication failed: {e}")
    except KaiRateLimitError as e:
        print(f"Rate limited, try again later: {e}")
    except KaiNotFoundError as e:
        print(f"Chat not found: {e}")
    except KaiError as e:
        print(f"API error: {e.code} - {e.message}")
```

## API Reference

### KaiClient

The main client class for interacting with the Kai API.

#### Factory Method (Recommended for Production)

```python
client = await KaiClient.from_storage_api(
    storage_api_token: str,        # Keboola Storage API token
    storage_api_url: str,          # Keboola connection URL (e.g., https://connection.keboola.com)
    service: KaiBackend = KaiBackend.AGENT,  # Backend to discover (keyword-only)
    timeout: float = 300.0,        # Request timeout in seconds
    stream_timeout: float = 600.0,  # Streaming timeout in seconds
    workspace_id: str | None = None,  # Pin queries to this workspace (e.g. a Data App's WORKSPACE_ID)
)
```

This method auto-discovers the **kai-agent** service URL from your Keboola stack
(the modern agent backend). To target the legacy `kai-assistant` backend
(single-tenant deployments only), pass `service=KaiBackend.ASSISTANT`.

#### Backend Support

`kai-client` targets the **kai-agent** backend by default. The following methods
are supported against kai-agent:

`ping`, `info`, `send_message`, `chat`, `submit_approval`, `get_chat`,
`delete_chat`, `get_history` / `get_all_history`, `get_votes` / `vote` /
`upvote` / `downvote`, `get_usage`, `get_settings` / `update_settings` /
`get_user_settings` / `update_user_settings`, `get_tools`, `get_suggestions`.

These methods use the older Vercel-AI-SDK-v6 / tool-result protocols and are
**not supported by kai-agent** (kept only for the legacy backend):
`send_tool_approval_response`, `approve_tool`, `reject_tool`, `send_tool_result`,
`confirm_tool`, `deny_tool`, `resume_stream`. Use `submit_approval` for tool
approvals on kai-agent.

> This split is derived from the kai-agent route surface and the protocol notes
> carried by the methods themselves; only `ping` has been confirmed against a
> live kai-agent deployment, so treat individual entries as expected rather than
> individually verified.

#### Constructor (For Local Development)

```python
KaiClient(
    storage_api_token: str,      # Keboola Storage API token
    storage_api_url: str,        # Keboola connection URL
    base_url: str = "http://localhost:3000",  # Kai API base URL
    timeout: float = 300.0,      # Request timeout in seconds
    stream_timeout: float = 600.0,  # Streaming timeout in seconds
    backend: KaiBackend | None = None,  # Which backend base_url points at, if known
    workspace_id: str | None = None,  # Pin queries to this workspace (e.g. a Data App's WORKSPACE_ID)
)
```

`client.backend` records the discovered backend when the client comes from
`from_storage_api()`, and stays `None` here — the backend behind an arbitrary
`base_url` is unknown. Pass `backend=` explicitly if your code needs to branch
on it (for example to pick an approval flow).

> **Data Apps:** when Kai is embedded inside a running Data App, pass that app's own
> `WORKSPACE_ID` env var (Keboola injects it into every Data App container) as `workspace_id`
> so Kai's queries run against the app's own — potentially more restricted — workspace instead
> of the default per-branch one. This is forwarded as the `x-workspace-id` header on every
> request.

#### Methods

| Method | Description |
|--------|-------------|
| `from_storage_api(...)` | **[Class method]** Create client with auto-discovered URL |
| `new_chat_id()` | Generate a new UUID for a chat session |
| `ping()` | Check server health |
| `info()` | Get server information |
| `send_message(chat_id, text, ...)` | Send a message and stream response |
| `chat(text, ...)` | Simple non-streaming chat (returns text) |
| `submit_approval(chat_id, tool_use_id, approved, ...)` | Approve or deny a pending tool call (kai-agent) |
| `approve_tool(chat_id, approval_id, ...)` | Approve a pending tool call (legacy v6 flow, kai-assistant only) |
| `reject_tool(chat_id, approval_id, ...)` | Reject a pending tool call (legacy v6 flow, kai-assistant only) |
| `confirm_tool(chat_id, tool_call_id, ...)` | Approve a pending tool call (legacy tool-result flow, kai-assistant only) |
| `deny_tool(chat_id, tool_call_id, ...)` | Deny a pending tool call (legacy tool-result flow, kai-assistant only) |
| `get_chat(chat_id)` | Get chat details with messages |
| `get_history(limit, ...)` | Get chat history |
| `get_all_history()` | Iterate through all history |
| `delete_chat(chat_id)` | Delete a chat |
| `vote(chat_id, message_id, type)` | Vote on a message |
| `upvote(chat_id, message_id)` | Upvote a message |
| `downvote(chat_id, message_id)` | Downvote a message |
| `get_votes(chat_id)` | Get votes for a chat |

### SSE Event Types

| Event Type | Description | Fields |
|------------|-------------|--------|
| `text` | Text content | `text`, `state` |
| `step-start` | Processing step started | - |
| `tool-call` | Tool being called | `tool_call_id`, `tool_name`, `state`, `input`, `output` |
| `tool-approval-request` | Tool needs user approval | `approval_id`, `tool_call_id` |
| `tool-output-error` | Tool execution failed | `tool_call_id`, `error_text` |
| `finish` | Stream completed | `finish_reason` |
| `error` | Error occurred | `message`, `code` |

The `tool-call` event has these states: `started`, `input-available` (waiting for approval or auto-executing), `output-available` (completed).

### Exceptions

| Exception | Error Code | Description |
|-----------|------------|-------------|
| `KaiError` | - | Base exception |
| `KaiAuthenticationError` | `unauthorized:chat` | Invalid credentials |
| `KaiForbiddenError` | `forbidden:chat` | Access denied |
| `KaiNotFoundError` | `not_found:chat` | Resource not found |
| `KaiRateLimitError` | `rate_limit:chat` | Rate limit exceeded |
| `KaiBadRequestError` | `bad_request:api` | Invalid request |
| `KaiStreamError` | - | SSE stream error |
| `KaiConnectionError` | - | Connection failed |
| `KaiTimeoutError` | - | Request timed out |

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/keboola/kai-client.git
cd kai-client

# Install with dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linting
uv run ruff check .
```

### Running Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=kai_client

# Specific test file
uv run pytest tests/test_client.py
```

## Claude Code Plugin

This repository includes a [Claude Code](https://claude.com/claude-code) plugin that teaches Claude how to use the Kai CLI correctly.

### Installation

#### Option 1: Download directly (no clone required)

Download the plugin to your Claude Code plugins directory:

```bash
# Create plugins directory if it doesn't exist
mkdir -p ~/.claude/plugins

# Download the plugin using curl
curl -L https://github.com/keboola/kai-client/archive/refs/heads/main.tar.gz | \
  tar -xz --strip-components=2 -C ~/.claude/plugins kai-client-main/plugins/kai-cli
```

Or using wget:

```bash
mkdir -p ~/.claude/plugins
wget -qO- https://github.com/keboola/kai-client/archive/refs/heads/main.tar.gz | \
  tar -xz --strip-components=2 -C ~/.claude/plugins kai-client-main/plugins/kai-cli
```

#### Option 2: Clone and link (for development)

```bash
# Clone the repository
git clone https://github.com/keboola/kai-client.git
cd kai-client

# Option A: Run Claude Code with the plugin directory
claude --plugin-dir plugins/kai-cli

# Option B: Symlink to your plugins directory for persistent access
ln -s "$(pwd)/plugins/kai-cli" ~/.claude/plugins/kai-cli
```

#### Verify Installation

After installation, the plugin should be available in Claude Code. Ask Claude to "use kai" or "help me with kai cli" to trigger the skill.

### What the Plugin Provides

The plugin includes a skill that activates when you ask Claude to:
- "use kai" or "run kai command"
- "chat with Keboola AI" or "query Keboola"
- "list tables", "check kai history"
- "interact with Keboola assistant"

It teaches Claude about:
- **Environment setup** - Setting `STORAGE_API_TOKEN` and `STORAGE_API_URL`
- **Core commands** - `ping`, `info`, `chat`, `history`, `get-chat`, `delete-chat`, `vote`
- **Tool approval** - Interactive prompts vs `--auto-approve` for write operations
- **Scripting** - Using `--json-output` for automation

### Plugin Structure

```
plugins/kai-cli/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
└── skills/
    └── kai-cli/
        ├── SKILL.md             # Main skill guide
        ├── references/
        │   ├── api-details.md   # Python API documentation
        │   └── sse-events.md    # SSE event types reference
        └── examples/
            ├── basic-chat.sh    # Basic usage examples
            └── workflow-automation.sh
```

## License

MIT License - see [LICENSE](LICENSE) for details.


