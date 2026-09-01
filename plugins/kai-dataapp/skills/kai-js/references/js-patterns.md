# JavaScript + Kai App Patterns

## App Architecture

A Kai-integrated JS app follows this structure:

```
1. Express server loads credentials from .env.local or env vars
2. Service discovery finds kai-assistant URL on first request
3. Browser sends chat payload to Express backend
4. Backend adds auth headers, forwards to kai-assistant
5. SSE response streams through Express to the browser
6. Frontend parses SSE events, updates DOM in real time
7. Tool approvals pause stream, user clicks Approve/Deny
8. Suggestions extracted from response, rendered as buttons
```

## Why Not Call Kai Directly from the Browser?

The kai-assistant API requires `x-storageapi-token` and `x-storageapi-url` headers. Exposing these to the browser means anyone can read your Keboola data. The Express backend keeps credentials server-side.

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

## New Chat Reset

Reset all state:

```javascript
newChatBtn.addEventListener("click", () => {
  chatId = crypto.randomUUID();
  messagesEl.innerHTML = "";
  suggestionsEl.innerHTML = "";
  approvalBar.classList.add("hidden");
  pendingApproval = null;
  chatInput.focus();
});
```

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

Both `chat_id` and `message.id` must be valid UUIDs. Use `crypto.randomUUID()`:

```javascript
const payload = {
  id: chatId,  // crypto.randomUUID()
  message: {
    id: crypto.randomUUID(),
    role: "user",
    parts: [{ type: "text", text }],
  },
  selectedChatModel: "chat-model",
  selectedVisibilityType: "private",
};
```

Non-UUID strings cause a 400 Bad Request from the API.

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

Keboola maps Data App secrets to environment variables. The server reads both naming conventions:

```javascript
const TOKEN = process.env.STORAGE_API_TOKEN || process.env.KBC_TOKEN;
const API_URL = process.env.STORAGE_API_URL || process.env.KBC_URL;
```
