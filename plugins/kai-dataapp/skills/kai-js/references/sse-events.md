# SSE Event Types for JavaScript Integration

The kai-agent API streams responses as Server-Sent Events. This reference covers how each event type maps to frontend UI actions.

## SSE Format

Kai uses **data-only SSE** — no `event:` lines. The event type is inside the JSON payload:

```
data: {"type":"start","messageId":"uuid"}
data: {"type":"text-delta","id":"text-1","delta":"Hello "}
data: {"type":"tool-input-start","toolCallId":"toolu_1","toolName":"get_tables"}
data: {"type":"tool-input-available","toolCallId":"toolu_1","toolName":"get_tables","input":{}}
data: {"type":"tool-output-available","toolCallId":"toolu_1","output":"..."}
data: {"type":"finish"}
data: [DONE]
```

## Event Types

| Event Type | Key Fields | Frontend Action |
|------------|------------|-----------------|
| `start` | `messageId` | Ignore (internal) |
| `text-start` | `id` | Ignore (text block starting) |
| `text-delta` | `id`, `delta` | Append `delta` to accumulated text, update UI |
| `text-end` | `id` | Ignore (text block complete) |
| `reasoning-start` / `reasoning-delta` / `reasoning-end` | `id`, `delta` | Ignore, or show as "thinking" |
| `tool-input-start` | `toolCallId`, `toolName` | Cache `toolName` by `toolCallId` |
| `tool-input-available` | `toolCallId`, `toolName`, `input` | Show "Calling **toolName**..." |
| `tool-approval-request` | `toolCallId`, `approvalId` | Show Approve/Deny; the stream stays open |
| `tool-output-available` | `toolCallId`, `output` | Show "**toolName** completed." |
| `tool-output-error` | `toolCallId`, `errorText` | Show the tool failure |
| `data-*` (e.g. `data-usage`, `data-status`) | `data` | Ignore |
| `finish` | — | Turn complete, sent once; a stream that ends without it was cut off |
| `error` | `errorText` | Show error to user |
| `[DONE]` | — | Raw SSE terminator, not JSON |

## Gotcha: toolName only on the input events

`tool-output-available` and `tool-output-error` carry only `toolCallId`. Track names by it:

```javascript
const toolNames = {};

switch (type) {
  case "tool-input-start":
    toolNames[data.toolCallId] = data.toolName;
    break;
  case "tool-input-available":
    showCalling(data.toolName);
    break;
  case "tool-output-available":
    showCompleted(toolNames[data.toolCallId] || "tool");
    break;
}
```

## Tool Approval Request

When a tool needs the user's decision, kai-agent emits (only if the chat request set
`supportsApprovalRequestedEvent: true`):

```json
{
  "type": "tool-approval-request",
  "toolCallId": "toolu_1",
  "approvalId": "toolu_1"
}
```

The stream **stays open** and blocked. Send the decision with a separate, non-streaming request
through your backend to `POST {kai}/api/chat/{chatId}/approval`:

```json
{ "toolUseId": "toolu_1", "approved": false, "reason": "User denied" }
```

The original stream then continues with `tool-output-available` (or `tool-output-error`) and
the rest of the answer. The POST answers 404 while the approval is not registered yet
(retry once: kai-agent already waits 10 s for it), and 409 once it can no longer apply
(final). An undecided write is denied after 5 minutes, and its `tool-output-*` event follows.

Questions (`AskUserQuestion`) and plan cards (`ExitPlanMode`) arrive the same way but never
time out; the reference example disallows them with
`toolRestrictions: { disallowedTools: ["AskUserQuestion", "ExitPlanMode"] }`.

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
    case "tool-input-start":
    case "tool-input-available":
    case "tool-output-available":
    case "tool-output-error":
      // Handle tool progress (see above)
      break;
    case "tool-approval-request":
      pendingApprovals.push({ chatId, toolCallId: data.toolCallId });
      break;
    case "error":
      showError(data.errorText);
      break;
    case "finish":
      finished = true; // Sent once at the end of the turn
      break;
  }
}
```
