# SSE Event Types for JavaScript Integration

The kai-assistant API streams responses as Server-Sent Events. This reference covers how each event type maps to frontend UI actions.

## SSE Format

Kai uses **data-only SSE** — no `event:` lines. The event type is inside the JSON payload:

```
data: {"type":"text-delta","id":"0","delta":"Hello "}
data: {"type":"start-step"}
data: {"type":"tool-call","toolCallId":"uuid","toolName":"get_tables","state":"input-available"}
data: {"type":"finish","finishReason":"stop"}
data: [DONE]
```

## Event Types

| Event Type | Key Fields | Frontend Action |
|------------|------------|-----------------|
| `start` | `messageId` | Ignore (internal) |
| `start-step` | — | Ignore (internal processing boundary) |
| `text-start` | `id` | Ignore (text block starting) |
| `text-delta` | `id`, `delta` | Append `delta` to accumulated text, update UI |
| `text-end` | `id` | Ignore (text block complete) |
| `tool-call` | `toolCallId`, `toolName`, `state` | Show inline tool status |
| `tool-approval-request` | `approvalId`, `toolCallId` | Show Approve/Deny buttons |
| `finish-step` | — | Ignore (step boundary) |
| `finish` | `finishReason` | Streaming complete, finalize UI |
| `error` | `message`, `code` | Show error to user |
| `[DONE]` | — | Raw SSE terminator, not JSON |

## Tool Call States

The `tool-call` event arrives multiple times with different `state` values:

1. **`started`** — Tool invocation beginning. Usually ignore in UI.
2. **`input-available`** — Parameters ready. Show "Calling **toolName**..." and cache `toolName` by `toolCallId`.
3. **`output-available`** — Tool completed. Show "**toolName** completed." Note: `toolName` is often `null` in this event — look it up from the cache.

## Gotcha: toolName is null on output-available

The `output-available` event frequently has `toolName: null`. Track names by `toolCallId`:

```javascript
const toolNames = {};

if (type === "tool-call") {
  const { toolCallId, toolName, state } = data;
  if (toolName) toolNames[toolCallId] = toolName;
  const displayName = toolName || toolNames[toolCallId] || "tool";

  if (state === "input-available") showCalling(displayName);
  if (state === "output-available") showCompleted(displayName);
}
```

## Tool Approval Request

When Kai calls a write operation, streaming pauses and emits:

```json
{
  "type": "tool-approval-request",
  "approvalId": "uuid",
  "toolCallId": "uuid"
}
```

Send an approval response via `POST /api/chat` with a `tool-approval-response` message part to resume.

## Next Actions

Kai may append suggested actions at the end of a response in a fenced code block:

```
\`\`\`next_actions
- Explore tables in a specific bucket
- Query sample data from a table
\`\`\`
```

The tag is `next_actions` (not plain backticks). Parse with:

```javascript
text.match(/\n```[^\n]*\n((?:\s*[-*]\s+.+\n?)+)\s*```\s*$/)
```

## Event Processing Pattern

```javascript
for (const { type, data } of parseSSEChunk(chunk)) {
  switch (type) {
    case "text-delta":
      accumulated += data.delta;
      content.innerHTML = renderMarkdown(accumulated) + "▌";
      break;
    case "tool-call":
      // Handle tool states (see above)
      break;
    case "tool-approval-request":
      pendingApproval = { approvalId: data.approvalId, toolCallId: data.toolCallId };
      break;
    case "error":
      showError(data.message);
      break;
    case "finish":
      break; // Stream complete
  }
}
```
