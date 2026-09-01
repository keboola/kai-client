# SSE Event Types Reference

The Kai API uses Server-Sent Events (SSE) for streaming responses. This document details all event types and their handling.

## Event Types Overview

| Event Type | Description | Key Fields |
|-----------|-------------|------------|
| `text` | AI response text (streamed incrementally) | `text`, `state` |
| `step-start` | Processing step started | - |
| `tool-call` | Tool execution event | `tool_call_id`, `tool_name`, `state`, `input`, `output` |
| `tool-output-error` | Tool failed after approval | `tool_call_id`, `error_text` |
| `finish` | Stream completed | `finish_reason` |
| `error` | Error in stream | `message`, `code` |

## Text Events

Contain the AI's response text, streamed incrementally:

```python
{
    "event": "text",
    "data": {
        "text": "Here are your tables:",
        "state": "streaming"  # or "complete"
    }
}
```

**Handling:**
```python
if isinstance(event, TextEvent):
    print(event.text, end="", flush=True)
```

## Tool Call Events

Indicate tool execution at various stages:

### States

1. **`started`**: Tool invocation beginning
2. **`input-available`**: Tool parameters ready, waiting for approval
3. **`output-available`**: Tool completed successfully
4. **`output-error`**: Tool execution failed

### Example Event Structure

```python
{
    "event": "tool-call",
    "data": {
        "tool_call_id": "call_abc123",
        "tool_name": "create_bucket",
        "state": "input-available",
        "input": {
            "bucket_name": "test-bucket",
            "stage": "in"
        },
        "output": null
    }
}
```

### Approval Workflow

When `state` is `input-available`, a tool may be waiting for user approval. On
the default **kai-agent** backend the stream stays open and blocked until the
decision is POSTed, so answer with `submit_approval` from inside the loop and
keep iterating — the same stream carries the tool output afterwards:

```python
async for event in client.send_message(chat_id, text):
    process_event(event)

    if isinstance(event, ToolCallEvent) and event.state == "input-available":
        print(f"Tool {event.tool_name} needs approval")
        print(f"Input: {event.input}")

        await client.submit_approval(
            chat_id=chat_id,
            tool_use_id=event.tool_call_id,
            approved=user_approves,
            # reason="Not right now",
        )
```

`submit_approval` is a non-streaming POST returning an `ApprovalResponse`.
Read-only tools that the backend executes on its own also pass through
`input-available`; an approval submitted for one of those returns a "no pending
approval" error that is safe to ignore.

On the legacy **kai-assistant** backend the first stream ends instead, and the
decision is sent with `client.approve_tool(chat_id, approval_id)` /
`client.reject_tool(...)` — using the `approval_id` from the separate
`tool-approval-request` event — or with the older `client.confirm_tool(...)` /
`client.deny_tool(...)`. Each returns a new stream to consume. None of these
work against kai-agent.

## Tool Output Error Events

Indicates a tool failed after being approved:

```python
{
    "event": "tool-output-error",
    "data": {
        "tool_call_id": "call_abc123",
        "error_text": "Bucket already exists"
    }
}
```

**Handling:**
```python
if isinstance(event, ToolOutputErrorEvent):
    print(f"Tool failed: {event.error_text}")
```

## Finish Events

Signal stream completion:

```python
{
    "event": "finish",
    "data": {
        "finish_reason": "complete"
    }
}
```

### Finish Reasons

- `complete`: Normal completion
- `error`: Stream ended due to error
- `cancelled`: User or system cancelled
- `max_tokens`: Token limit reached

## Error Events

Indicate errors during streaming:

```python
{
    "event": "error",
    "data": {
        "message": "Internal server error",
        "code": "INTERNAL_ERROR"
    }
}
```

## Complete Event Processing Example

```python
async def process_chat(client, chat_id, text, auto_approve=False):
    """Process a chat with comprehensive event handling."""

    async for event in client.send_message(chat_id, text):
        match event:
            case TextEvent():
                print(event.text, end="", flush=True)

            case ToolCallEvent() if event.state == "started":
                print(f"\n[Starting tool: {event.tool_name}]")

            case ToolCallEvent() if event.state == "input-available":
                print(f"\n[Tool {event.tool_name} requires approval]")
                print(f"Input: {json.dumps(event.input, indent=2)}")

                # kai-agent: unblocks this stream, which then continues below
                await client.submit_approval(
                    chat_id=chat_id,
                    tool_use_id=event.tool_call_id,
                    approved=auto_approve or get_user_approval(),
                )

            case ToolCallEvent() if event.state == "output-available":
                print(f"\n[Tool completed: {event.tool_name}]")

            case ToolOutputErrorEvent():
                print(f"\n[Tool error: {event.error_text}]")

            case FinishEvent():
                print(f"\n[Finished: {event.finish_reason}]")

            case ErrorEvent():
                print(f"\n[Error {event.code}]: {event.message}")
```

## CLI JSON Output Format

When using `--json-output`, events are printed as JSON lines:

```bash
kai chat --json-output -m "List tables"
```

Output:
```json
{"event": "text", "data": {"text": "Here are", "state": "streaming"}}
{"event": "text", "data": {"text": " your tables:", "state": "streaming"}}
{"event": "text", "data": {"text": "\n1. users\n2. orders", "state": "complete"}}
{"event": "finish", "data": {"finish_reason": "complete"}}
```

Parse with jq:
```bash
kai chat --json-output -m "List tables" | jq -r 'select(.event == "text") | .data.text'
```
