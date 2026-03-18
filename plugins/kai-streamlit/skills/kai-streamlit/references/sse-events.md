# SSE Event Types for Streamlit Integration

The KaiClient streams responses as Server-Sent Events. This reference covers how each event type maps to Streamlit UI elements.

## Event Types

| Event Type | Class | Key Fields | Streamlit Action |
|------------|-------|------------|-----------------|
| `text` | `TextEvent` | `text`, `state` | Append to accumulated text, update `placeholder.markdown()` |
| `step-start` | `StepStartEvent` | — | Ignore (internal processing boundary) |
| `tool-call` | `ToolCallEvent` | `tool_call_id`, `tool_name`, `state`, `input`, `output` | Show inline status via `container.info()` |
| `tool-approval-request` | `ToolApprovalRequestEvent` | `approval_id`, `tool_call_id` | Store in session state, render Approve/Deny buttons |
| `tool-output-error` | `ToolOutputErrorEvent` | `tool_call_id`, `error_text` | `container.error(event.error_text)` |
| `finish` | `FinishEvent` | `finish_reason` | Streaming complete, finalize UI |
| `error` | `ErrorEvent` | `message`, `code` | `container.error(event.message)` |
| `data-usage` | `UsageEvent` | `usage.prompt_tokens`, `usage.completion_tokens` | Optional: display token counts |

## Tool Call States

The `tool-call` event arrives multiple times with different `state` values:

1. **`started`** — Tool invocation beginning. Usually ignore in UI.
2. **`input-available`** — Parameters ready. Show "Calling **tool_name**..." and cache `tool_name` by `tool_call_id`.
3. **`output-available`** — Tool completed. Show "**tool_name** completed." Note: `tool_name` is often `None` in this event — look it up from the cache.

## Gotcha: tool_name is None on output-available

The `output-available` event frequently has `tool_name=None`. Track names by `tool_call_id`:

```python
tool_names: dict[str, str] = {}

if event.type == "tool-call":
    call_id = getattr(event, "tool_call_id", "")
    name = getattr(event, "tool_name", None)
    if name:
        tool_names[call_id] = name
    display_name = name or tool_names.get(call_id, "tool")
```

## Tool Approval Request

When Kai calls a write operation, streaming pauses and emits:

```python
ToolApprovalRequestEvent(
    type="tool-approval-request",
    approval_id="uuid",       # Use with client.approve_tool() / reject_tool()
    tool_call_id="uuid",
)
```

After approval/rejection, streaming resumes with the same event types.

## Next Actions

Kai may append suggested actions at the end of a response in a fenced code block:

```
\`\`\`next_actions
- Explore tables in a specific bucket
- Query sample data from a table
\`\`\`
```

The tag is `next_actions` (not plain backticks). Parse with:

```python
re.search(r'\n```[^\n]*\n((?:\s*[-*]\s+.+\n?)+)\s*```\s*$', text)
```

## Event Processing Pattern

```python
async for event in client.send_message(chat_id, text):
    match event.type:
        case "text":
            accumulated += event.text
            text_placeholder.markdown(accumulated + "▌")
        case "tool-call":
            # Handle tool states (see above)
        case "tool-approval-request":
            pending = {"approval_id": event.approval_id, ...}
        case "error":
            container.error(event.message)
        case "finish":
            pass  # Stream complete
```
