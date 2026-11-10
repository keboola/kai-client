---
name: Kai JavaScript Integration Guide
description: This skill should be used when the user asks to "build a JS app with Kai", "create a JavaScript data app", "integrate Kai with Express", "stream Kai responses in JavaScript", "add Kai chat to a web app", "build a Keboola chat UI in JS", "create a JS data app", or mentions JavaScript/Express/Node.js with Kai, kai-agent, or Keboola AI Assistant. Provides patterns, gotchas, and working code for building JavaScript apps that integrate with the Kai API.
version: 2.0.0
---

# Building JavaScript Data Apps with Kai

This guide covers the patterns, pitfalls, and working solutions for integrating the Keboola AI Assistant (Kai) into JavaScript web apps deployed on Keboola.

## Prerequisites

### Dependencies

```bash
npm install express dotenv
```

### Credentials

Kai needs a Storage API token and the stack URL. Load from `.env.local` for local dev:

```javascript
require("dotenv").config({ path: ".env.local" });

const API_URL = process.env.STORAGE_API_URL || process.env.KBC_URL || "";
const WORKSPACE_ID = process.env.WORKSPACE_ID || "";

function isKaiEnabled() {
  const value = (process.env.KAI_ENABLED || "").trim().toLowerCase();
  return !["", "0", "false", "no", "off"].includes(value);
}

// 1. KAI_STORAGE_API_TOKEN — injected into apps deployed with Kai.
// 2. KAI_ENABLED without it — Kai is unavailable; never fall back to another token.
// 3. Otherwise STORAGE_API_TOKEN — a project member's personal token.
function resolveKaiToken() {
  const kaiToken = process.env.KAI_STORAGE_API_TOKEN || "";
  if (kaiToken) {
    if (!WORKSPACE_ID) {
      return { token: "", error: "Kai is not available: KAI_STORAGE_API_TOKEN needs WORKSPACE_ID." };
    }
    return { token: kaiToken, error: null };
  }
  if (isKaiEnabled()) {
    return {
      token: "",
      error: "Kai is not available in this run of the app: KAI_ENABLED is set but " +
        "KAI_STORAGE_API_TOKEN is missing. Redeploy the app as a user who is allowed " +
        "to create Storage API tokens.",
    };
  }
  return { token: process.env.STORAGE_API_TOKEN || "", error: null };
}

const { token: TOKEN, error: KAI_CONFIG_ERROR } = resolveKaiToken();
```

`.env.local`:
```
STORAGE_API_TOKEN=your-keboola-token
STORAGE_API_URL=https://connection.keboola.com
```

In Keboola production, credentials come from environment variables mapped from Data App secrets.

> **`KAI_STORAGE_API_TOKEN`** is injected, together with `KAI_ENABLED=1`, into Data Apps
> deployed with Kai (`runtime.kai.enabled`). It is a dedicated Kai token that kai-agent scopes
> to the app's own workspace. When `KAI_ENABLED` is set but the token is missing, the app was
> started without a user who could create tokens: show the error in the UI, keep the rest of
> the app running, and do **not** fall back to `STORAGE_API_TOKEN`. Never set either variable
> in `.env.local`.

> **Never use `KBC_TOKEN` for Kai.** It is the app's own token with no Keboola user behind it,
> and kai-agent refuses it with 403 `Storage token has no associated Keboola user`.

> **Don't crash at startup.** Resolve the token once, and report `KAI_CONFIG_ERROR` through an
> endpoint such as `GET /api/config` so the browser can show it; `POST /api/chat` answers 503.

> **`WORKSPACE_ID`** is injected automatically into every Data App container by Keboola — you
> don't set it yourself. Send it as the `x-workspace-id` header on every Kai request. With the
> Kai token it is required: a missing header, or a workspace that is not the app's own, is a
> 403. Locally it is normally empty and the header is omitted.

### Backend

Discover and call **`kai-agent`**. Do not use the legacy `kai-assistant` service: it does not
scope the Kai token to the app's workspace, and this skill's approval flow is kai-agent's.

## Critical Patterns

### 1. Express Backend as Auth Proxy

kai-agent requires `x-storageapi-token`, `x-storageapi-url` and, in a Data App,
`x-workspace-id`. The token is a secret that **must not be exposed to the browser**. The
Express backend:
1. Handles service discovery (finds the kai-agent URL)
2. Adds auth headers before forwarding requests
3. Streams SSE responses straight through

```javascript
function kaiHeaders() {
  return {
    "Content-Type": "application/json",
    "x-storageapi-token": TOKEN,
    "x-storageapi-url": API_URL,
    ...(WORKSPACE_ID && { "x-workspace-id": WORKSPACE_ID }),
  };
}

async function proxySSE(payload, res) {
  const kaiUrl = await discoverKaiUrl();
  const abort = new AbortController();
  res.on("close", () => abort.abort());

  const upstream = await fetch(`${kaiUrl}/api/chat`, {
    method: "POST",
    headers: kaiHeaders(),
    body: JSON.stringify(payload),
    signal: abort.signal,
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

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

app.post("/api/chat", async (req, res) => {
  if (KAI_CONFIG_ERROR) return res.status(503).json({ error: KAI_CONFIG_ERROR });
  const { id, text } = req.body || {};
  if (!UUID_RE.test(id || "") || typeof text !== "string" || !text.trim()) {
    return res.status(400).json({ error: "Expected { id: <chat UUID>, text }" });
  }
  try {
    await proxySSE(
      {
        id,
        message: { id: crypto.randomUUID(), role: "user", parts: [{ type: "text", text }] },
        selectedVisibilityType: "private",
        supportsApprovalRequestedEvent: true,
        // Questions and plan cards wait forever and need more than Approve/Deny.
        toolRestrictions: { disallowedTools: ["AskUserQuestion", "ExitPlanMode"] },
      },
      res
    );
  } catch (err) {
    // Express 4 does not catch async errors; an unhandled rejection stops the process.
    if (!res.headersSent) res.status(500).json({ error: err.message });
    else res.end();
  }
});
```

Build the upstream body on the server: the browser sends only the chat id and the text, so it
cannot set the role, metadata or tool restrictions of the message. `toolRestrictions` is taken
from the chat's first message.

### 2. Service Discovery

Auto-discover the kai-agent URL from the Keboola Storage API:

```javascript
let _kaiUrl = null;

async function discoverKaiUrl() {
  if (_kaiUrl) return _kaiUrl;

  const res = await fetch(`${API_URL.replace(/\/$/, "")}/v2/storage`, {
    headers: { "x-storageapi-token": TOKEN },
  });
  if (!res.ok) throw new Error(`Storage API discovery failed: ${res.status}`);
  const data = await res.json();
  const svc = (data.services || []).find((s) => s.id === "kai-agent");

  if (!svc || !svc.url) {
    throw new Error("kai-agent service not found");
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
  selectedVisibilityType: "private",
  supportsApprovalRequestedEvent: true, // emit tool-approval-request when a tool waits
};
```

> **Gotcha:** Non-UUID strings (like `"test-123"`) cause a 400 Bad Request.

`selectedChatModel` is optional on kai-agent; leave it out.

### 4. SSE Format

Kai's SSE uses **data-only lines** with the event type inside the JSON — no `event:` lines:

```
data: {"type":"text-delta","id":"text-1","delta":"Hello "}
data: {"type":"text-delta","id":"text-1","delta":"world!"}
data: {"type":"finish"}
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

  case "tool-input-start":
    toolNames[data.toolCallId] = data.toolName;
    break;

  case "tool-input-available":
    showToolCalling(data.toolName);
    break;

  case "tool-output-available":
    showToolCompleted(toolNames[data.toolCallId] || "tool");
    break;

  case "tool-output-error":
    showToolFailed(toolNames[data.toolCallId] || "tool", data.errorText);
    break;

  case "tool-approval-request":
    showApprovalUI(chatId, data.toolCallId);
    break;

  case "error":
    showError(data.errorText);
    break;
}
```

> **Gotcha:** `tool-output-available` and `tool-output-error` carry no `toolName`. Cache it
> from `tool-input-start` by `toolCallId`.

## Tool Approval Flow

Most tools run without asking. A tool that changes something waits for a decision, and on
kai-agent the chat stream **stays open** meanwhile:

1. The stream emits `{ type: "tool-approval-request", toolCallId, approvalId }` (only when the
   chat request set `supportsApprovalRequestedEvent: true`; `approvalId` equals `toolCallId`).
2. Show the user what Kai wants to run and let them decide. Never approve automatically.
3. The backend POSTs the decision to `{kai}/api/chat/{chatId}/approval` with the same headers
   and `{ toolUseId: <toolCallId>, approved, reason? }`. The response is plain JSON, not a stream.
4. The **original** stream continues with the tool's output and the rest of the answer.

```javascript
// Backend route
app.post("/api/chat/:chatId/approval", async (req, res) => {
  if (KAI_CONFIG_ERROR) return res.status(503).json({ error: KAI_CONFIG_ERROR });
  const { chatId } = req.params;
  const { toolUseId, approved, reason } = req.body || {};
  if (!UUID_RE.test(chatId) || typeof toolUseId !== "string" || typeof approved !== "boolean") {
    return res.status(400).json({ error: "Expected { toolUseId, approved } for a chat UUID" });
  }
  try {
    const kaiUrl = await discoverKaiUrl();
    let upstream;
    for (let attempt = 1; attempt <= 2; attempt++) {
      upstream = await fetch(`${kaiUrl}/api/chat/${chatId}/approval`, {
        method: "POST",
        headers: kaiHeaders(),
        body: JSON.stringify({ toolUseId, approved, ...(!approved && reason && { reason }) }),
      });
      if (upstream.status !== 404) break; // 404: not registered yet, retry once
    }
    const text = await upstream.text();
    if (!upstream.ok) return res.status(upstream.status).json({ error: text });
    res.status(upstream.status).type("application/json").send(text);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});
```

Responses to the POST:
- **200** — accepted; the outcome arrives on the open chat stream.
- **404** — the approval is not registered yet. kai-agent already waits 10 s for it before
  answering, so one retry is enough.
- **409** — final: the approval was already resolved, timed out, the chat was stopped, or Kai
  restarted (`error.subtype`). Do not retry; drop the card.

A write left undecided is denied after 5 minutes; its `tool-output-*` event then arrives on
the stream, so drop a queued card when its tool's output arrives. When the chat stream ends,
any card still shown can no longer apply — hide it.

Questions to the user (`AskUserQuestion`) and plan cards (`ExitPlanMode`) also arrive as
`tool-approval-request`, but they never time out and need `answers` rather than a plain
approve. Disallow them with `toolRestrictions` as above unless you build that UI.

In strict mode (direct-grant input mapping, `read_only_storage_access: false`) Kai has no
write tools, so only those interactive tools could ask.

### Stopping a Turn

Closing the chat stream does **not** stop the turn on kai-agent: it keeps running, and the
next message to that chat gets 409 `A message is already being processed`. To stop it (e.g.
on New Chat), proxy `POST {kai}/api/chat/{chatId}/stop` with the same headers; it is
idempotent. A stream that ends without a `finish` event was cut off, not completed.

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
