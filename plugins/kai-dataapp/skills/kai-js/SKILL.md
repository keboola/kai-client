---
name: Kai JavaScript Integration Guide
description: This skill should be used when the user asks to "build a JS app with Kai", "create a JavaScript data app", "integrate Kai with Express", "stream Kai responses in JavaScript", "add Kai chat to a web app", "build a Keboola chat UI in JS", "create a JS data app", or mentions JavaScript/Express/Node.js with Kai, kai-assistant, or Keboola AI Assistant. Provides patterns, gotchas, and working code for building JavaScript apps that integrate with the Kai API.
version: 1.0.0
---

# Building JavaScript Data Apps with Kai

This guide covers the patterns, pitfalls, and working solutions for integrating the Keboola AI Assistant (Kai) into JavaScript web apps deployed on Keboola.

## Prerequisites

### Dependencies

```bash
npm install express dotenv
```

### Credentials

Kai requires two environment variables. Load from `.env.local` for local dev:

```javascript
require("dotenv").config({ path: ".env.local" });

const TOKEN = process.env.STORAGE_API_TOKEN || process.env.KBC_TOKEN || "";
const API_URL = process.env.STORAGE_API_URL || process.env.KBC_URL || "";
```

`.env.local`:
```
STORAGE_API_TOKEN=your-keboola-token
STORAGE_API_URL=https://connection.keboola.com
```

In Keboola production, credentials come from environment variables mapped from Data App secrets.

## Critical Patterns

### 1. Express Backend as Auth Proxy

The kai-assistant API requires `x-storageapi-token` and `x-storageapi-url` headers. These are secrets that **must not be exposed to the browser**. The Express backend:
1. Handles service discovery (finds the kai-assistant URL)
2. Adds auth headers before forwarding requests
3. Streams SSE responses straight through

```javascript
async function proxySSE(payload, res) {
  const kaiUrl = await discoverKaiUrl();

  const upstream = await fetch(`${kaiUrl}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-storageapi-token": TOKEN,
      "x-storageapi-url": API_URL,
    },
    body: JSON.stringify(payload),
  });

  if (!upstream.ok) {
    const text = await upstream.text();
    return res.status(upstream.status).json({ error: text });
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    res.write(decoder.decode(value, { stream: true }));
  }

  res.end();
}
```

### 2. Service Discovery

Auto-discover the kai-assistant URL from the Keboola Storage API:

```javascript
let _kaiUrl = null;

async function discoverKaiUrl() {
  if (_kaiUrl) return _kaiUrl;

  const res = await fetch(`${API_URL.replace(/\/$/, "")}/v2/storage`, {
    headers: { "x-storageapi-token": TOKEN },
  });
  const data = await res.json();
  const svc = (data.services || []).find((s) => s.id === "kai-assistant");

  if (!svc || !svc.url) {
    throw new Error("kai-assistant service not found");
  }

  _kaiUrl = svc.url.replace(/\/$/, "");
  return _kaiUrl;
}
```

Cache the result — it won't change during the app's lifetime.

> **Gotcha:** Constructing the URL manually will break across regions. Always discover it.

### 3. Chat Request Payload

Both chat IDs and message IDs must be valid UUIDs:

```javascript
const payload = {
  id: crypto.randomUUID(),          // chat ID
  message: {
    id: crypto.randomUUID(),        // message ID
    role: "user",
    parts: [{ type: "text", text: "Hello!" }],
  },
  selectedChatModel: "chat-model",
  selectedVisibilityType: "private",
};
```

> **Gotcha:** Non-UUID strings (like `"test-123"`) cause a 400 Bad Request.

### 4. SSE Format

Kai's SSE uses **data-only lines** with the event type inside the JSON — no `event:` lines:

```
data: {"type":"text-delta","id":"0","delta":"Hello "}
data: {"type":"text-delta","id":"0","delta":"world!"}
data: {"type":"finish","finishReason":"stop"}
data: [DONE]
```

Parse with:
```javascript
function* parseSSEChunk(text) {
  for (const line of text.split("\n")) {
    if (!line.startsWith("data:")) continue;
    const raw = line.slice(5).trim();
    if (raw === "[DONE]") continue;
    try {
      const data = JSON.parse(raw);
      yield { type: data.type || "unknown", data };
    } catch {
      // skip
    }
  }
}
```

> **Gotcha:** Do NOT use `EventSource` — it only supports GET. Use `fetch` + `ReadableStream`.

### 5. Streaming with ReadableStream

```javascript
async function readSSEStream(url, fetchOptions, onEvent) {
  const res = await fetch(url, fetchOptions);
  if (!res.ok) return null;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();

    for (const part of parts) {
      if (!part.trim()) continue;
      for (const event of parseSSEChunk(part + "\n\n")) {
        onEvent(event);
      }
    }
  }

  return res;
}
```

### 6. Handling Event Types

```javascript
switch (type) {
  case "text-delta":
    accumulated += data.delta;
    updateUI(accumulated);
    break;

  case "tool-call":
    if (data.toolName) toolNames[data.toolCallId] = data.toolName;
    const name = data.toolName || toolNames[data.toolCallId] || "tool";
    if (data.state === "input-available") showToolCalling(name);
    if (data.state === "output-available") showToolCompleted(name);
    break;

  case "tool-approval-request":
    showApprovalUI(data.approvalId, data.toolCallId);
    break;

  case "error":
    showError(data.message);
    break;
}
```

> **Gotcha:** `output-available` events often have `toolName: null`. Cache the name from `input-available` using `toolCallId` as key.

## Tool Approval Flow

When Kai calls a write tool, streaming pauses with a `tool-approval-request`. Send an approval response to resume:

```javascript
// Backend route (merged approve + reject)
app.post("/api/chat/:chatId/:action/:approvalId", async (req, res) => {
  const { chatId, action, approvalId } = req.params;
  const approved = action === "approve";

  const payload = {
    id: chatId,
    message: {
      id: crypto.randomUUID(),
      role: "user",
      parts: [{
        type: "tool-approval-response",
        approvalId,
        approved,
        ...(approved ? {} : { reason: "User denied" }),
      }],
    },
    selectedChatModel: "chat-model",
    selectedVisibilityType: "private",
  };

  await proxySSE(payload, res);
});
```

Frontend calls `/api/chat/{chatId}/approve/{approvalId}` or `/api/chat/{chatId}/reject/{approvalId}`.

## Suggested Actions

Kai appends suggested next actions in fenced code blocks:

```
\`\`\`next_actions
- Explore tables in a specific bucket
- Search for a configuration by name
\`\`\`
```

Extract and render as clickable buttons:

```javascript
function extractSuggestions(text) {
  const m = text.trimEnd().match(/\n```[^\n]*\n((?:\s*[-*]\s+.+\n?)+)\s*```\s*$/);
  if (m) {
    return {
      body: text.slice(0, m.index).trimEnd(),
      suggestions: m[1].trim().split("\n")
        .map(l => l.replace(/^\s*[-*]\s+/, "").trim())
        .filter(Boolean),
    };
  }
  return { body: text, suggestions: [] };
}
```

## Keboola Deployment

### Nginx Config

**Critical:** `proxy_buffering off` is required for SSE streaming:

```nginx
server {
    listen 8888;
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
    }
}
```

### Supervisord Config

```ini
[program:app]
command=node /home/apprunner/app/server.js
directory=/home/apprunner/app
autostart=true
autorestart=true
environment=PORT="3000"
```

### Setup Script

```bash
#!/bin/bash
set -e
cd /home/apprunner/app
npm ci --production
```

## Reference Example

A complete working JS data app is available at `examples/js-dataapp/` in the kai-client repository.

## Additional Resources

- **`references/sse-events.md`** — Full SSE event type reference
- **`references/js-patterns.md`** — JavaScript-specific patterns and architecture
