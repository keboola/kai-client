# JavaScript + Kai App Patterns

## App Architecture

A Kai-integrated JS app follows this structure:

```
1. Express server resolves the Kai token once (KAI_STORAGE_API_TOKEN, then STORAGE_API_TOKEN)
2. Browser asks GET /api/config whether Kai is available, and shows the reason if not
3. Service discovery finds the kai-agent URL on first request
4. Browser sends chat payload to Express backend
5. Backend adds auth headers (incl. x-workspace-id), forwards to kai-agent
6. SSE response streams through Express to the browser
7. Frontend parses SSE events, updates DOM in real time
8. A tool waiting for approval keeps the stream open; Approve/Deny POSTs the decision
9. Suggestions extracted from response, rendered as buttons
```

## Why Not Call Kai Directly from the Browser?

kai-agent requires `x-storageapi-token`, `x-storageapi-url` and `x-workspace-id` headers. Exposing the token to the browser means anyone can read your Keboola data. The Express backend keeps credentials server-side.

## SSE Parsing — No EventSource

`EventSource` only supports GET requests. Kai's chat endpoint is POST. Use `fetch` + `ReadableStream`:

```javascript
const res = await fetch("/api/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  const chunks = buffer.split("\n\n");
  buffer = chunks.pop();

  for (const chunk of chunks) {
    // Parse each "data: {json}" line
  }
}
```

## Streaming Cursor

Show a blinking cursor during streaming:

```javascript
content.innerHTML = renderMarkdown(accumulated) + '<span class="cursor"></span>';
```

Remove it when streaming completes:
```javascript
content.innerHTML = renderMarkdown(accumulated);
```

CSS:
```css
.cursor {
  display: inline-block;
  width: 2px;
  height: 16px;
  background: #8b8bf5;
  animation: blink 0.8s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }
```

## Inline Tool Call Indicators

Show tool status inline within the message container:

```javascript
function addToolIndicator(container, text, completed) {
  const div = document.createElement("div");
  div.className = "tool-indicator" + (completed ? " completed" : "");
  div.textContent = text;
  container.appendChild(div);
}

// During streaming:
if (state === "input-available") {
  content.innerHTML = renderMarkdown(accumulated);
  addToolIndicator(container, `Calling ${displayName}...`);
}
```

## Avoiding Empty Bubbles

If the fetch fails or returns no text, remove the assistant message container:

```javascript
const res = await readSSEStream(url, options, onEvent);

if (!res) {
  container.remove(); // Fetch failed, error already shown
} else if (accumulated) {
  content.innerHTML = renderMarkdown(accumulated);
} else {
  container.remove(); // Stream produced no text
}
```

## Approval Card While Streaming

The chat stream stays open while a tool waits, so the Approve/Deny buttons must work while
`isStreaming` is true. Queue the requests and keep each one's chat id, so a decision always goes
to the chat it belongs to:

```javascript
let pendingApprovals = []; // { chatId, toolCallId, toolName }, oldest first

// In the stream's event handler:
case "tool-approval-request":
  pendingApprovals.push({ chatId: turnChatId, toolCallId: data.toolCallId, toolName });
  if (pendingApprovals.length === 1) showNextApproval();
  break;

async function handleApproval(approved) {
  const approval = pendingApprovals[0];
  const res = await fetch(`/api/chat/${approval.chatId}/approval`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      toolUseId: approval.toolCallId,
      approved,
      ...(approved ? {} : { reason: "User denied" }),
    }),
  });
  if (res.ok || res.status === 409) {
    // 409 is final: already resolved, timed out or the chat was stopped.
    dropApproval(approval.toolCallId);
  }
  // Otherwise keep the card so the user can try again.
}

function dropApproval(toolCallId) {
  pendingApprovals = pendingApprovals.filter((a) => a.toolCallId !== toolCallId);
  showNextApproval();
}
```

Also call `dropApproval` when a `tool-output-available` or `tool-output-error` event arrives for
the tool (e.g. kai-agent denied it on timeout). When the stream ends, clear the queue: a
decision can no longer apply.

## New Chat Reset

Stop the running turn, abort its stream and reset all state:

```javascript
newChatBtn.addEventListener("click", () => {
  if (isStreaming) fetch(`/api/chat/${chatId}/stop`, { method: "POST" }); // backend proxies to kai-agent
  if (streamAbort) streamAbort.abort(); // the AbortController passed to the chat fetch
  chatId = crypto.randomUUID();
  messagesEl.innerHTML = "";
  suggestionsEl.innerHTML = "";
  pendingApprovals = [];
  approvalBar.classList.add("hidden");
  chatInput.focus();
});
```

Without the abort, a turn blocked on an approval keeps the input disabled until kai-agent
denies the tool (after 5 minutes). Aborting alone does not stop the turn on kai-agent, which
is what the stop call is for.

## Error Display

Show errors as distinct styled elements, not inside message bubbles:

```javascript
function addError(text) {
  const div = document.createElement("div");
  div.className = "error-msg";
  div.textContent = text;
  messagesEl.appendChild(div);
}
```

## UUID Requirement

Both the chat id and `message.id` must be valid UUIDs. Use `crypto.randomUUID()` for the chat
id in the browser; the backend makes the message id:

```javascript
const payload = { id: chatId, text }; // chatId = crypto.randomUUID()
```

Non-UUID strings cause a 400 Bad Request from the API. The backend builds the kai-agent
message from `text` and adds `selectedVisibilityType`, `supportsApprovalRequestedEvent` and
`toolRestrictions` before forwarding.

## Keboola Deployment

### Directory Structure

```
my-kai-app/
├── server.js
├── package.json
├── public/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── keboola-config/
    ├── nginx/default.conf       # proxy_buffering off for SSE
    ├── supervisord/app.conf     # node process management
    └── setup.sh                 # npm ci --production
```

### Critical: Nginx Buffering

Without `proxy_buffering off`, Nginx buffers SSE responses and delivers them all at once when the stream ends — no real-time updates:

```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 600s;
```

### Credentials in Production

Keboola maps Data App secrets to environment variables and injects `KBC_URL`, `KBC_TOKEN` and
`WORKSPACE_ID`; an app deployed with Kai also gets `KAI_STORAGE_API_TOKEN` and `KAI_ENABLED=1`.

```javascript
const API_URL = process.env.STORAGE_API_URL || process.env.KBC_URL;
// Token: KAI_STORAGE_API_TOKEN; with KAI_ENABLED and no Kai token, Kai is unavailable;
// otherwise STORAGE_API_TOKEN. See resolveKaiToken() in SKILL.md.
```

`KBC_TOKEN` is the app's own token: keep it for the app's own Storage calls, never for Kai —
kai-agent refuses it with 403. The Kai token is for Kai only.
