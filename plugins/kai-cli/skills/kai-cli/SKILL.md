---
name: Kai CLI Usage Guide
description: This skill should be used when the user asks to "use kai", "run kai command", "chat with Keboola AI", "query Keboola", "list tables", "check kai history", "interact with Keboola assistant", "send message to kai", or mentions Kai CLI, Keboola AI Assistant, or wants to execute Kai commands. Provides comprehensive guidance for using the Kai CLI tool to interact with the Keboola AI Assistant.
version: 1.0.0
---

# Kai CLI Usage Guide

The Kai CLI is a command-line interface for interacting with the Keboola AI Assistant (Kai). It enables querying Keboola infrastructure, managing data, and executing operations through natural language conversations.

## Prerequisites

### Required Environment Variables

Before using any Kai command, ensure these environment variables are set:

```bash
export STORAGE_API_TOKEN="your-keboola-storage-api-token"
export STORAGE_API_URL="https://connection.keboola.com"
```

Alternatively, load from a `.env.local` file:
```bash
set -a && source .env.local && set +a
```

Or pass credentials via CLI flags:
```bash
kai --token YOUR_TOKEN --url https://connection.keboola.com COMMAND
```

### Backend Selection

Keboola exposes two AI backends. The CLI auto-discovers **kai-agent** (the
modern backend) by default; `--service assistant` selects the legacy
kai-assistant backend, which only exists on single-tenant deployments:

```bash
kai chat -m "Hello"                     # kai-agent (default)
kai --service assistant chat -m "Hello" # legacy backend
```

The flag can also be set with `KAI_SERVICE=agent|assistant` and is ignored when
`--base-url` is used for local development.

### Installation

Install from PyPI or run from source:
```bash
# From PyPI
pip install kai-client

# From source (in development)
uv run kai COMMAND
```

## Core Commands

### Health Check

Verify server connectivity:
```bash
kai ping
```

Returns server timestamp if successful.

### Server Information

Get server details including connected MCP servers:
```bash
kai info
```

### Interactive Chat

Start an interactive conversation:
```bash
kai chat
```

- Type messages and press Enter to send
- Type `exit` or `quit` to end the session
- Press Ctrl+C to interrupt

### Single Message

Send a one-off message without interactive mode:
```bash
kai chat -m "What tables do I have?"
kai chat -m "Show me the schema for my users table"
kai chat -m "List all configurations"
```

### Continue Existing Chat

Resume a previous conversation using its chat ID:
```bash
kai chat --chat-id CHAT_ID -m "Tell me more about that"
```

### Tool Approval

When Kai needs to execute write operations (creating buckets, running jobs, etc.), it requests approval:

**Interactive approval (default):**
```bash
kai chat -m "Create a bucket called test-bucket"
# Prompts: "Approve this tool call? [y/N]: "
```

**Auto-approve for automation:**
```bash
kai chat --auto-approve -m "Run job for configuration 12345"
```

> **Warning:** Use `--auto-approve` cautiously - it allows write operations without confirmation.

### JSON Output for Scripting

Get raw JSON events for programmatic use:
```bash
kai chat --json-output -m "List my buckets" | jq '.text'
```

## History Management

### View Chat History

List recent conversations:
```bash
kai history              # Last 10 chats
kai history --limit 50   # Last 50 chats
kai history --json-output
```

### Get Full Chat Details

Retrieve complete chat with all messages:
```bash
kai get-chat CHAT_ID
kai get-chat CHAT_ID --json-output > chat.json
```

### Delete a Chat

Remove a chat from history:
```bash
kai delete-chat CHAT_ID
kai delete-chat CHAT_ID -y  # Skip confirmation
```

## Voting System

Provide feedback on AI responses:
```bash
kai vote CHAT_ID MESSAGE_ID up    # Upvote helpful response
kai vote CHAT_ID MESSAGE_ID down  # Downvote poor response
kai get-votes CHAT_ID             # View all votes for a chat
```

## Command Reference

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `kai ping` | Check server health | - |
| `kai info` | Get server information | - |
| `kai chat` | Start chat session | `-m`, `--chat-id`, `--auto-approve`, `--json-output` |
| `kai history` | View chat history | `-n/--limit`, `--json-output` |
| `kai get-chat` | Get chat details | `--json-output` |
| `kai delete-chat` | Delete a chat | `-y/--yes` |
| `kai vote` | Vote on message | `up` or `down` |
| `kai get-votes` | Get votes for chat | `--json-output` |

## Common Usage Patterns

### Query Keboola Data

```bash
# List available resources
kai chat -m "What tables do I have?"
kai chat -m "Show me all my configurations"
kai chat -m "List buckets in my project"

# Get specific information
kai chat -m "Show schema for table in.c-bucket.users"
kai chat -m "What data types are in my sales table?"
```

### Execute Operations

```bash
# Create resources (requires approval)
kai chat -m "Create a bucket called analytics"

# Run jobs
kai chat --auto-approve -m "Run the transformation job for config 12345"
```

### Workflow Example

```bash
# 1. Start a conversation
kai chat -m "Help me analyze my user data"

# 2. Note the chat ID from output, continue conversation
kai chat --chat-id CHAT_ID -m "Filter by active users only"

# 3. Review the full conversation
kai get-chat CHAT_ID

# 4. Provide feedback
kai vote CHAT_ID MSG_ID up
```

## Error Handling

Common error scenarios:

- **Missing credentials**: Set `STORAGE_API_TOKEN` and `STORAGE_API_URL`
- **Connection refused**: Check network and server availability with `kai ping`
- **Authentication failed**: Verify token is valid and has required permissions
- **Rate limited**: Wait and retry, or reduce request frequency

## Additional Resources

### Reference Files

For detailed API information and advanced usage:
- **`references/api-details.md`** - Complete API method documentation
- **`references/sse-events.md`** - SSE event types and handling

### Example Files

Working examples in `examples/`:
- **`basic-chat.sh`** - Simple chat interaction
- **`workflow-automation.sh`** - Automated workflow with tool approval
