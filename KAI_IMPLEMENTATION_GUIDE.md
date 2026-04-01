# KAI Implementation Guide

> Reference implementation extracted from `keboola/profitline-js-app` (branch `fi-demo`).
> Intended as system context for AI agents implementing KAI in Keboola Data Apps.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Environment & Configuration](#2-environment--configuration)
3. [Backend Implementation (FastAPI)](#3-backend-implementation-fastapi)
4. [Frontend Implementation (Next.js / React)](#4-frontend-implementation-nextjs--react)
5. [Chat Message Protocol](#5-chat-message-protocol)
6. [Key Code Patterns](#6-key-code-patterns)
7. [UI Patterns](#7-ui-patterns)
8. [File Reference Map](#8-file-reference-map)

---

## 1. Architecture Overview

### Deployment Topology

```
Browser
  |
  :8888 (Nginx — external port, exposed by Docker)
  |
  +-- /api/chat*  -->  :8050 (FastAPI backend — KAI proxy)
  +-- /api/*      -->  :8050 (FastAPI backend — business logic)
  +-- /*          -->  :3000 (Next.js frontend — standalone)
```

All three processes run inside a single Docker container managed by **Supervisord**, with **Nginx** as the reverse proxy.

### The Polling Proxy Pattern

**Problem:** Keboola's edge proxy enforces a hard ~20-30 second request timeout that kills long-lived SSE (Server-Sent Events) streams before KAI finishes responding.

**Solution:** A polling-based proxy architecture:

1. **Frontend** sends a chat request to the **backend** (`POST /api/chat`).
2. **Backend** opens a long-lived SSE connection to the **KAI service**, buffering events in memory.
3. **Backend** returns a `stream_id` immediately.
4. **Frontend** polls `GET /api/chat/{stream_id}/poll?cursor=N` every 500-1500ms for buffered events.
5. Each poll is a fast, short-lived HTTP request that won't hit the edge proxy timeout.

```
Frontend         Backend (FastAPI)         KAI Service
   |                   |                       |
   |-- POST /api/chat ->|                       |
   |                   |-- POST /api/chat ----->|
   |<- {stream_id} ---|                       |
   |                   |<-- SSE stream --------|
   |                   |   (buffered in memory) |
   |-- GET /poll ------>|                       |
   |<- {events,cursor} |                       |
   |-- GET /poll ------>|                       |
   |<- {events,done}  -|                       |
```

### KAI Service Discovery

The KAI service URL is not hardcoded. It is discovered dynamically via the Keboola Storage API:

```
GET {KBC_URL_BASE}/v2/storage
  -> response.services[] -> find(id == "kai-assistant") -> .url
```

The discovered URL is cached for the lifetime of the backend process.

---

## 2. Environment & Configuration

### Backend Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `KBC_URL` | Yes | Keboola Storage API URL | `https://connection.europe-west3.gcp.keboola.com/v2/storage` |
| `KBC_TOKEN` | Yes | Keboola Storage API token | (bearer token) |
| `KBC_PROJECTID` | Recommended | Project ID (for Storage UI links in system context) | `12345` |
| `KAI_TOKEN` | Optional | Dedicated KAI-enabled token (falls back to `KBC_TOKEN`) | (bearer token) |
| `DEV_USER_EMAIL` | Dev only | Simulate user context locally | `demo@keboola.com` |

### Frontend Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BACKEND_URL` | Dev only | Backend URL for local proxy (default: `http://localhost:8050`) |
| `LOCAL_OIDC_EMAIL` | Dev only | Simulate OIDC user header |

### Nginx Configuration for KAI

The `/api/chat` location requires special Nginx settings to support the polling proxy:

```nginx
location /api/chat {
    proxy_pass http://127.0.0.1:8050;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;
    gzip off;                          # Compression buffers SSE chunks
    tcp_nodelay on;                    # Push heartbeats immediately
    chunked_transfer_encoding off;
    add_header X-Accel-Buffering no;   # Tell upstream not to buffer
}
```

### Next.js Local Dev Proxy

In `next.config.ts`:

```typescript
async rewrites() {
  return [
    { source: '/api/:path*', destination: 'http://localhost:8050/api/:path*' },
  ]
}
```

---

## 3. Backend Implementation (FastAPI)

All KAI backend logic lives in a single file: `backend/main.py`.

### 3.1 Service Discovery

```python
_kai_url: str | None = None

async def _discover_kai_url() -> str:
    global _kai_url
    if _kai_url:
        return _kai_url
    kbc_token = os.getenv("KBC_TOKEN", "").strip()
    kbc_url = os.getenv("KBC_URL", "").strip().rstrip("/")
    if not kbc_token or not kbc_url:
        raise HTTPException(500, "KBC_TOKEN / KBC_URL not configured")
    base = kbc_url.split("/v2/")[0] if "/v2/" in kbc_url else kbc_url
    resp = await _http_client.get(
        f"{base}/v2/storage",
        headers={"x-storageapi-token": kbc_token},
        timeout=30.0,
    )
    services = resp.json().get("services", [])
    svc = next((s for s in services if s["id"] == "kai-assistant"), None)
    if not svc:
        raise HTTPException(500, f"kai-assistant not found. Available: {[s['id'] for s in services]}")
    _kai_url = svc["url"].rstrip("/")
    return _kai_url
```

### 3.2 Authentication Headers

```python
def _kai_headers() -> tuple[str, str, dict]:
    """Return (base_url, token, headers) for Kai requests.
    Uses KAI_TOKEN if set, falls back to KBC_TOKEN."""
    kai_token = os.getenv("KAI_TOKEN", "").strip() or os.getenv("KBC_TOKEN", "").strip()
    kbc_url = os.getenv("KBC_URL", "").strip().rstrip("/")
    base = kbc_url.split("/v2/")[0] if "/v2/" in kbc_url else kbc_url
    return base, kai_token, {
        "Content-Type": "application/json",
        "x-storageapi-token": kai_token,
        "x-storageapi-url": base,
    }
```

### 3.3 Stream Buffer & Consumer

```python
_streams: dict[str, dict] = {}  # stream_id -> {events, done, error, task}
_STREAM_TTL = 600

async def _kai_stream_consumer(stream_id: str, resp: httpx.Response, client: httpx.AsyncClient) -> None:
    """Background task: reads Kai SSE stream and appends raw event lines to the buffer."""
    buf = _streams[stream_id]
    try:
        raw = b""
        async for chunk in resp.aiter_bytes():
            raw += chunk
            while b"\n\n" in raw:
                event_bytes, raw = raw.split(b"\n\n", 1)
                event_str = event_bytes.decode("utf-8", errors="replace").strip()
                if event_str:
                    buf["events"].append(event_str)
    except Exception as exc:
        buf["error"] = str(exc)
    finally:
        buf["done"] = True
        await resp.aclose()
        await client.aclose()

async def _start_kai_stream(kai_url: str, headers: dict, body: dict) -> str:
    """Start a background Kai stream and return its stream_id."""
    stream_id = str(uuid.uuid4())
    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0))
    req = client.build_request("POST", f"{kai_url}/api/chat", headers=headers, json=body)
    resp = await client.send(req, stream=True)
    if resp.status_code != 200:
        error_body = await resp.aread()
        await resp.aclose()
        await client.aclose()
        raise HTTPException(resp.status_code, error_body.decode("utf-8", errors="replace")[:500])
    _streams[stream_id] = {"events": [], "done": False, "error": None, "cursor": 0}
    task = asyncio.create_task(_kai_stream_consumer(stream_id, resp, client))
    _streams[stream_id]["task"] = task
    return stream_id
```

### 3.4 API Endpoints

**Start chat stream:**

```python
@app.post("/api/chat")
async def kai_chat(request: Request):
    kai_url = await _discover_kai_url()
    _base, _token, headers = _kai_headers()
    body = await request.json()
    stream_id = await _start_kai_stream(kai_url, headers, body)
    return {"stream_id": stream_id}
```

**Poll for events:**

```python
@app.get("/api/chat/{stream_id}/poll")
async def kai_poll(stream_id: str, cursor: int = 0):
    buf = _streams.get(stream_id)
    if not buf:
        raise HTTPException(404, "Stream not found or expired")
    events = buf["events"][cursor:]
    new_cursor = cursor + len(events)
    return {
        "events": events,
        "cursor": new_cursor,
        "done": buf["done"],
        "error": buf["error"],
    }
```

**Tool approval:**

```python
@app.post("/api/chat/{chat_id}/{action}/{approval_id}")
async def kai_tool_approval(chat_id: str, action: str, approval_id: str):
    kai_url = await _discover_kai_url()
    _base, _token, headers = _kai_headers()
    approved = action == "approve"
    payload = {
        "id": chat_id,
        "message": {
            "id": str(uuid.uuid4()),
            "role": "user",
            "parts": [{
                "type": "tool-approval-response",
                "approvalId": approval_id,
                "approved": approved,
                **({"reason": "User denied"} if not approved else {}),
            }],
        },
        "selectedChatModel": "chat-model",
        "selectedVisibilityType": "private",
    }
    stream_id = await _start_kai_stream(kai_url, headers, payload)
    return {"stream_id": stream_id}
```

---

## 4. Frontend Implementation (Next.js / React)

### 4.1 Provider Tree

```
layout.tsx
  └── Providers (providers.tsx)
        └── PersistQueryClientProvider (TanStack Query + localStorage)
              └── KaiChatProvider (React Context — all KAI state)
                    ├── KaiWidget (portal-rendered floating chat)
                    └── children (app pages)
```

`KaiChatProvider` is mounted in `providers.tsx`:

```tsx
import { KaiChatProvider } from '@/lib/kai-context'

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <PersistQueryClientProvider client={queryClient} persistOptions={...}>
      <KaiChatProvider>
        {children}
      </KaiChatProvider>
    </PersistQueryClientProvider>
  )
}
```

### 4.2 State Management (KaiChatProvider)

All KAI state is managed via React Context in `lib/kai-context.tsx`.

**Context value interface:**

```typescript
interface KaiChatContextValue {
  messages: ChatMessage[]
  conversationId: string
  isStreaming: boolean
  toolStatus: string | null
  pendingApproval: PendingApproval | null
  input: string
  setInput: (v: string) => void
  sendMessage: (text: string, bypassCache?: boolean) => Promise<void>
  handleApproval: (approved: boolean) => Promise<void>
  handleNewConversation: () => void
  handleSelectConversation: (id: string) => void
  handleDeleteConversation: (id: string) => void
  handleDeleteAllConversations: () => void
  handleRenameConversation: (id: string, title: string) => void
  handleExportConversation: (id: string) => void
  abortStreaming: () => void
  conversationList: ConversationSummary[]
  panelOpen: boolean
  setPanelOpen: (v: boolean) => void
  suggestions: string[]
  pageContext: string | null
  setPageContext: (ctx: string | null) => void
  isCached: boolean
  loadingConversation: boolean
}
```

**Access via hook:**

```typescript
const { messages, sendMessage, isStreaming, suggestions } = useKaiChat()
```

### 4.3 Component Hierarchy

```
KaiWidget (floating button + panel, portal-rendered to document.body)
  └── KaiChat (compact=true)
        ├── ConversationPanel (sidebar, portal-rendered)
        ├── Messages area
        │     └── ChatMessage[] (memoized)
        ├── Follow-up suggestions
        ├── Tool approval UI
        └── Input form

/assistant page (full-page view)
  └── KaiChat (compact=false, with toolbar)
```

### 4.4 Polling Client

The frontend polling logic lives in `lib/kai-context.tsx`:

```typescript
const CHAT_API_BASE = process.env.NODE_ENV === 'development' ? 'http://localhost:8050' : ''

async function pollKaiStream(
  startUrl: string,
  startOptions: RequestInit,
  callbacks: SSECallbacks,
  signal?: AbortSignal,
) {
  // 1. Start the stream
  const startRes = await fetch(startUrl, { ...startOptions, signal })
  if (!startRes.ok) { /* error handling for 401, 403, 500 */ }
  const { stream_id } = await startRes.json()

  // 2. Poll for events
  let cursor = 0
  let done = false

  while (!done) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')

    const pollRes = await fetch(
      `${CHAT_API_BASE}/api/chat/${stream_id}/poll?cursor=${cursor}`,
      { signal },
    )
    const poll = await pollRes.json()

    // Process each SSE event from the buffer
    for (const eventStr of poll.events) {
      for (const line of eventStr.split('\n')) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (raw === '[DONE]') continue
        const data = JSON.parse(raw)

        if (data.type === 'text-delta' && data.delta)
          callbacks.onDelta(data.delta)
        else if (data.type === 'tool-approval-request')
          callbacks.onToolApproval?.({ approvalId: data.approvalId, toolCallId: data.toolCallId })
        else if (data.type === 'tool-call' || data.type === 'tool-input-start')
          callbacks.onToolCall?.(data.toolName, data.state)
      }
    }

    cursor = poll.cursor
    done = poll.done
    if (poll.error) throw new Error(poll.error)

    // Adaptive poll interval
    if (!done) await new Promise(r => setTimeout(r, poll.events.length > 0 ? 500 : 1500))
  }
}
```

### 4.5 System Context Injection

System context is built from live app data and injected **only on the first message** of a conversation:

```typescript
function buildSystemContext(params: {
  revenue: number | undefined
  margin: number | undefined
  revDelta: number | undefined
  groups: Array<{ group_id: string; group_name: string }> | undefined
  userEmail: string | undefined
  userRole: string | undefined
  connectionUrl: string | undefined
  projectId: string | null | undefined
}): string {
  return `[Context: Profit Line Dashboard app. Revenue: ${revStr}${deltaStr}, GM: ${marginStr}, ${groupCount} groups. PLs: SW, MS, PN. User: ${userEmail} (${userRole}). Query project data to answer accurately.]

Links: [Name](/account/{id}?period=l12m) or [Name](/group/{id}?period=l12m).
Groups: ${groups?.slice(0, 10).map(g => `${g.group_name}=/group/${g.group_id}`).join(', ')}
${kbcBase ? `Project: ${kbcBase}` : ''}

IMPORTANT: End every response with a \`\`\`next_actions code block containing 2-3 suggested follow-up questions as bullet points.`
}
```

Data sources for context (via TanStack Query hooks):
- `useOrgKpis()` — revenue, margin, YoY delta
- `useOrgGroups()` — customer group names and IDs
- `useCurrentUser()` — email, role, admin flag
- `usePlatformInfo()` — Keboola connection URL, project ID

### 4.6 Page Context Detection

The `KaiWidget` detects the current page from the URL and updates context-aware suggestions:

```typescript
useEffect(() => {
  const name = searchParams.get('name')
  if (pathname.startsWith('/group/') && name) {
    setPageContext(decodeURIComponent(name))       // e.g., "Team Alpha"
  } else if (pathname.startsWith('/account/') && name) {
    setPageContext(decodeURIComponent(name))       // e.g., "Acme Corp"
  } else if (pathname === '/performance') {
    setPageContext('Team Performance')
  } else {
    setPageContext(null)                            // Global context
  }
}, [pathname, searchParams, setPageContext])
```

### 4.7 Conversation Storage (localStorage)

```typescript
// lib/chat-storage.ts
const STORAGE_KEY = 'kai-conversations'
const MAX_CONVERSATIONS = 50

interface Conversation {
  id: string
  title: string            // Auto-derived from first user message
  messages: ChatMessage[]
  chatId: string           // For resuming KAI stream
  createdAt: string
  updatedAt: string
}
```

Features:
- Max 50 conversations, auto-prune oldest
- Auto-derive title from first user message (truncated at word boundary, max 60 chars)
- Cross-tab sync via `CustomEvent` + `storage` event listeners
- Export conversation as Markdown file
- Full CRUD: read, save, rename, delete, delete all

### 4.8 Response Caching

```typescript
const CACHE_TTL = 5 * 60 * 1000 // 5 minutes

// Before sending to KAI, check cache:
const cached = responseCache.current.get(cacheKey)
if (cached && Date.now() - cached.ts < CACHE_TTL) {
  // Return cached response immediately (no API call)
  setIsCached(true)
  return
}

// After receiving response, cache it:
responseCache.current.set(cacheKey, { content: accumulated, ts: Date.now() })
```

Users can bypass cache via `sendMessage(text, bypassCache=true)`.

---

## 5. Chat Message Protocol

### User Message (sent to KAI)

```json
{
  "id": "<chat_id (UUID, persists across messages in a conversation)>",
  "message": {
    "id": "<message_id (UUID, unique per message)>",
    "role": "user",
    "parts": [
      {
        "type": "text",
        "text": "<system_context (first msg only)>\n\n<user_query>"
      }
    ]
  },
  "selectedChatModel": "chat-model",
  "selectedVisibilityType": "private"
}
```

### Tool Approval Response

```json
{
  "id": "<chat_id>",
  "message": {
    "id": "<new UUID>",
    "role": "user",
    "parts": [
      {
        "type": "tool-approval-response",
        "approvalId": "<approval_id from KAI>",
        "approved": true,
        "reason": "User denied"  // only if approved === false
      }
    ]
  },
  "selectedChatModel": "chat-model",
  "selectedVisibilityType": "private"
}
```

### SSE Event Types (from KAI, buffered by backend)

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `text-delta` | Streamed text chunk | `delta: string` |
| `tool-input-start` | Tool execution starting | `toolCallId`, `toolName` |
| `tool-input-available` | Tool input ready | `toolCallId`, `toolName` |
| `tool-output-available` | Tool result ready | `toolCallId` |
| `tool-call` | Tool state change | `toolCallId`, `toolName`, `state` |
| `tool-approval-request` | Requires human approval | `approvalId`, `toolCallId` |
| `[DONE]` | Stream complete | (none) |

### Tool Status Friendly Names

```typescript
const friendly: Record<string, string> = {
  search: 'Searching tables...',
  get_tables: 'Reading table schema...',
  get_table: 'Reading table schema...',
  query_data: 'Running SQL query...',
  get_buckets: 'Browsing storage...',
  get_project_info: 'Loading project info...',
}
```

---

## 6. Key Code Patterns

### Pattern 1: Backend Polling Proxy (FastAPI + httpx)

This is the core pattern for proxying KAI through a FastAPI backend. It handles the SSE buffering to work around edge proxy timeouts.

```python
import asyncio
import uuid
import httpx
from fastapi import FastAPI, Request, HTTPException

app = FastAPI()

_streams: dict[str, dict] = {}

async def _kai_stream_consumer(stream_id: str, resp: httpx.Response, client: httpx.AsyncClient) -> None:
    buf = _streams[stream_id]
    try:
        raw = b""
        async for chunk in resp.aiter_bytes():
            raw += chunk
            while b"\n\n" in raw:
                event_bytes, raw = raw.split(b"\n\n", 1)
                event_str = event_bytes.decode("utf-8", errors="replace").strip()
                if event_str:
                    buf["events"].append(event_str)
    except Exception as exc:
        buf["error"] = str(exc)
    finally:
        buf["done"] = True
        await resp.aclose()
        await client.aclose()

async def _start_kai_stream(kai_url: str, headers: dict, body: dict) -> str:
    stream_id = str(uuid.uuid4())
    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0))
    req = client.build_request("POST", f"{kai_url}/api/chat", headers=headers, json=body)
    resp = await client.send(req, stream=True)
    if resp.status_code != 200:
        error_body = await resp.aread()
        await resp.aclose(); await client.aclose()
        raise HTTPException(resp.status_code, error_body.decode()[:500])
    _streams[stream_id] = {"events": [], "done": False, "error": None}
    asyncio.create_task(_kai_stream_consumer(stream_id, resp, client))
    return stream_id

@app.post("/api/chat")
async def kai_chat(request: Request):
    kai_url = await _discover_kai_url()
    _, _, headers = _kai_headers()
    body = await request.json()
    stream_id = await _start_kai_stream(kai_url, headers, body)
    return {"stream_id": stream_id}

@app.get("/api/chat/{stream_id}/poll")
async def kai_poll(stream_id: str, cursor: int = 0):
    buf = _streams.get(stream_id)
    if not buf:
        raise HTTPException(404, "Stream not found or expired")
    events = buf["events"][cursor:]
    return {
        "events": events,
        "cursor": cursor + len(events),
        "done": buf["done"],
        "error": buf["error"],
    }
```

### Pattern 2: Frontend Polling Loop (React + fetch)

This pattern shows how to consume the polling proxy from the frontend, parsing SSE events and dispatching callbacks.

```typescript
interface SSECallbacks {
  onDelta: (text: string) => void
  onToolApproval?: (approval: { approvalId: string; toolCallId: string }) => void
  onToolCall?: (toolName: string | null, state: string) => void
}

const CHAT_API_BASE = process.env.NODE_ENV === 'development' ? 'http://localhost:8050' : ''

async function pollKaiStream(
  startUrl: string,
  startOptions: RequestInit,
  callbacks: SSECallbacks,
  signal?: AbortSignal,
) {
  // 1. Start stream
  const startRes = await fetch(startUrl, { ...startOptions, signal })
  if (!startRes.ok) throw new Error(`Request failed (${startRes.status})`)
  const { stream_id } = await startRes.json()

  // 2. Poll loop
  let cursor = 0, done = false
  while (!done) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const pollRes = await fetch(`${CHAT_API_BASE}/api/chat/${stream_id}/poll?cursor=${cursor}`, { signal })
    const poll = await pollRes.json()

    for (const eventStr of poll.events) {
      for (const line of eventStr.split('\n')) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (raw === '[DONE]') continue
        try {
          const data = JSON.parse(raw)
          if (data.type === 'text-delta') callbacks.onDelta(data.delta)
          else if (data.type === 'tool-approval-request') callbacks.onToolApproval?.(data)
          else if (data.type === 'tool-call') callbacks.onToolCall?.(data.toolName, data.state)
        } catch {}
      }
    }

    cursor = poll.cursor
    done = poll.done
    if (poll.error) throw new Error(poll.error)
    if (!done) await new Promise(r => setTimeout(r, poll.events.length > 0 ? 500 : 1500))
  }
}
```

### Pattern 3: System Context Builder & Message Sending

This pattern shows how to inject app-specific context into the first KAI message and manage streaming state.

```typescript
// In your KaiChatProvider:

const sendMessage = useCallback(async (text: string, bypassCache = false) => {
  if (!text.trim() || isStreaming) return

  // 1. Check response cache (5-min TTL)
  if (!bypassCache) {
    const cached = responseCache.current.get(text.trim().toLowerCase())
    if (cached && Date.now() - cached.ts < 5 * 60 * 1000) {
      setMessages(prev => [...prev, { role: 'user', content: text }, { role: 'assistant', content: cached.content }])
      return
    }
  }

  // 2. Add user message to UI
  setMessages(prev => [...prev, { role: 'user', content: text }])
  setIsStreaming(true)

  // 3. Inject system context on first message only
  let messageText = text
  if (isFirstMessage.current) {
    const pageCtx = pageContext ? ` The user is currently viewing: ${pageContext}.` : ''
    messageText = `${systemContext}${pageCtx}\n\n${text}`
    isFirstMessage.current = false
  }

  // 4. Add empty assistant message (will be filled by streaming)
  let accumulated = ''
  setMessages(prev => [...prev, { role: 'assistant', content: '' }])

  // 5. Start polling
  const controller = new AbortController()
  try {
    await pollKaiStream(
      `${CHAT_API_BASE}/api/chat`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: chatId,
          message: {
            id: crypto.randomUUID(),
            role: 'user',
            parts: [{ type: 'text', text: messageText }],
          },
          selectedChatModel: 'chat-model',
          selectedVisibilityType: 'private',
        }),
      },
      {
        onDelta: (delta) => {
          accumulated += delta
          setMessages(prev => {
            const next = [...prev]
            next[next.length - 1] = { role: 'assistant', content: accumulated }
            return next
          })
        },
        onToolCall: (toolName, state) => { setToolStatus(friendly[toolName] ?? `Running ${toolName}...`) },
        onToolApproval: (approval) => setPendingApproval(approval),
      },
      controller.signal,
    )
  } catch (err) {
    if (!(err instanceof DOMException && err.name === 'AbortError')) {
      setMessages(prev => {
        const next = [...prev]
        next[next.length - 1] = { role: 'assistant', content: `**Error:** ${err.message}` }
        return next
      })
    }
  }

  setIsStreaming(false)
  // Cache response
  if (accumulated) responseCache.current.set(text.trim().toLowerCase(), { content: accumulated, ts: Date.now() })
  saveCurrentConversation(messagesRef.current)
}, [isStreaming, systemContext, chatId, pageContext])
```

---

## 7. UI Patterns

### Floating Widget

- **Portal-rendered** to `document.body` (avoids parent z-index/overflow issues)
- **Position:** fixed, bottom-right (bottom: 20px, right: 20px)
- **Button:** z-index 996, 52x52px circle, blue gradient
- **Panel:** z-index 997, 480x640px, opens above button
- **Animation:** Framer Motion (opacity + y + scale transitions)
- **Auto-hides** on `/assistant` page (full-page chat already showing)

### Follow-up Suggestions

KAI is instructed to end responses with a `next_actions` code block:

```typescript
const CODE_BLOCK_RE = /```(?:next_actions|suggestions?|follow.?up)?\s*\n([\s\S]*?)```/g

function parseKaiContent(raw: string): { clean: string; suggestions: string[] } {
  const suggestions: string[] = []
  const clean = raw.replace(CODE_BLOCK_RE, (_match, body: string) => {
    const lines = body.split('\n').map(l => l.replace(/^[-*]\s*/, '').trim()).filter(Boolean)
    suggestions.push(...lines)
    return ''  // Strip from displayed content
  })
  return { clean, suggestions }
}
```

If KAI doesn't provide suggestions, fallback keyword-based suggestions are generated from response content.

### Markdown Rendering

Custom `react-markdown` components:

```typescript
const markdownComponents = {
  a: ({ href, children }) => {
    if (href.startsWith('/')) {
      return <Link href={href}>{children}</Link>        // Internal: Next.js router
    }
    return <a href={href} target="_blank">{children}</a>  // External: new tab
  },
  table: ({ children }) => <KaiTableChart>{children}</KaiTableChart>,  // Auto-convert to interactive chart
}
```

### Pin to Dashboard

Tables rendered by KAI include a **Pin** button (via `KaiTableChart`). Clicking it calls `pinChart()` from `lib/dashboard-storage.ts`, which saves the chart data (headers, rows, chart type, source question) to localStorage. This powers a **custom dashboard** page where users can view, rearrange, and manage all charts they've pinned from KAI conversations. The pinning is entirely client-side — no backend endpoint is needed. The Pin button appears on every table KAI returns, alongside the CSV export button.

### Stalled Detection

If no new content arrives for 1.5 seconds during streaming, show a "querying data" indicator:

```typescript
useEffect(() => {
  if (!isLastAssistant || !isStreaming) return
  const timer = setTimeout(() => {
    if (contentRef.current === message.content && isStreaming) setStalled(true)
  }, 1500)
  return () => clearTimeout(timer)
}, [message.content, isLastAssistant, isStreaming])
```

---

## 8. File Reference Map

### Backend

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app, all KAI endpoints (discovery, headers, stream buffer, poll, approval) |
| `backend/services/user_context.py` | Email-based auth & role resolution |
| `backend/services/audit_log.py` | Audit logging middleware |
| `backend/pyproject.toml` | Dependencies: fastapi, httpx, uvicorn, pandas |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/lib/kai-context.tsx` | `KaiChatProvider` React Context, `pollKaiStream()`, `buildSystemContext()`, all chat logic |
| `frontend/lib/chat-storage.ts` | Conversation CRUD, localStorage persistence, `useConversationList()` hook |
| `frontend/components/kai/KaiWidget.tsx` | Floating chat button + panel (portal-rendered) |
| `frontend/components/kai/KaiChat.tsx` | Main chat UI (messages, input, suggestions, tool approval) |
| `frontend/components/kai/ChatMessage.tsx` | Individual message rendering (markdown, copy, streaming cursor) |
| `frontend/components/kai/ConversationPanel.tsx` | Conversation history sidebar |
| `frontend/components/kai/KaiTableChart.tsx` | Auto-convert tables to interactive ECharts |
| `frontend/app/providers.tsx` | Provider tree (TanStack Query + KaiChatProvider) |
| `frontend/app/assistant/page.tsx` | Full-page `/assistant` chat view |
| `frontend/app/api/chat/route.ts` | Dev-only Next.js proxy to backend |

### Configuration

| File | Purpose |
|------|---------|
| `keboola-config/nginx/sites/default.conf` | Nginx routing (`/api/chat` with SSE settings) |
| `frontend/next.config.ts` | Next.js rewrites for local dev proxy |
| `keboola-config/setup.sh` | Container setup script (`uv sync` for backend) |
| `keboola-config/supervisord/services/python.conf` | Uvicorn process config |
| `keboola-config/supervisord/services/node.conf` | Next.js standalone process config |

### Dependencies

**Backend (Python):**
- `fastapi` + `uvicorn` — API framework
- `httpx` — Async HTTP client (for KAI SSE streaming)
- `pandas` / `numpy` — Data processing

**Frontend (Node):**
- `@tanstack/react-query` — Server state management + cache persistence
- `react-markdown` + `remark-gfm` — Markdown rendering
- `framer-motion` — Animations
- `echarts-for-react` — Chart rendering (KaiTableChart)
- `lucide-react` — Icons

---

## Design Decisions Summary

| Decision | Rationale |
|----------|-----------|
| Polling instead of SSE streaming | Keboola edge proxy has ~20-30s timeout that kills long SSE connections |
| Backend buffers SSE events in memory | Decouples KAI's long-running stream from short frontend poll requests |
| System context on first message only | Reduces token usage; KAI maintains conversation context |
| 5-min response cache | Avoids re-running expensive KAI queries for identical questions |
| Portal-rendered widget | Avoids z-index/overflow issues from parent CSS contexts |
| No kai-client package dependency | Custom implementation gives full control over polling architecture |
| `KAI_TOKEN` fallback to `KBC_TOKEN` | Allows dedicated KAI-enabled token or reuse of general Storage token |
| Dynamic KAI URL discovery | KAI service URL varies by Keboola stack; discovered at runtime from Storage API |
| localStorage for conversations | Simple, no backend state needed; max 50 with auto-prune |
| `next_actions` code block convention | Structured way to extract follow-up suggestions from KAI responses |
| Pin-to-dashboard from KAI charts | Users can build a custom dashboard by pinning any chart KAI generates; stored client-side in localStorage via `dashboard-storage.ts` |
