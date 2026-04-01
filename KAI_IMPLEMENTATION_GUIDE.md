# KAI Implementation Guide

> Reference implementation extracted from `keboola/profitline-js-app` (branch `fi-demo`).
> Intended as system context for AI agents implementing KAI in Keboola Data Apps.

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

**Problem:** Keboola's edge proxy enforces a ~20-30s request timeout that kills long-lived SSE streams.

**Solution:** Backend buffers KAI's SSE stream in memory; frontend polls for buffered events via short-lived HTTP requests.

```
Frontend         Backend (FastAPI)         KAI Service
   |-- POST /api/chat ->|-- POST /api/chat ----->|
   |<- {stream_id} ---|                         |
   |                   |<-- SSE stream (buffered)|
   |-- GET /poll ------>|                        |
   |<- {events,cursor} |                        |
   |-- GET /poll ------>|                        |
   |<- {events,done}  -|                        |
```

### KAI Service Discovery

KAI URL is discovered dynamically: `GET {KBC_URL_BASE}/v2/storage` → find service with `id == "kai-assistant"` → use its `.url`. Cached for process lifetime.

---

## 2. Environment & Configuration

### Backend Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `KBC_URL` | Yes | Keboola Storage API URL |
| `KBC_TOKEN` | Yes | Keboola Storage API token |
| `KBC_PROJECTID` | Recommended | Project ID (for Storage UI links in system context) |
| `KAI_TOKEN` | Optional | Dedicated KAI-enabled token (falls back to `KBC_TOKEN`) |
| `DEV_USER_EMAIL` | Dev only | Simulate user context locally |

### Frontend Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BACKEND_URL` | Dev only | Backend URL for local proxy (default: `http://localhost:8050`) |
| `LOCAL_OIDC_EMAIL` | Dev only | Simulate OIDC user header |

### Nginx — Critical Settings for `/api/chat`

```nginx
proxy_buffering off; proxy_cache off; proxy_read_timeout 600s;
gzip off; tcp_nodelay on; chunked_transfer_encoding off;
add_header X-Accel-Buffering no;
```

These prevent buffering/compression of SSE chunks. See `keboola-config/nginx/sites/default.conf`.

---

## 3. Backend Implementation (FastAPI)

All KAI backend logic lives in `backend/main.py`.

### Service Discovery & Auth

- `_discover_kai_url()` — Fetches `GET {base}/v2/storage`, finds `kai-assistant` service, caches URL globally.
- `_kai_headers()` → `(base_url, token, headers)` — Uses `KAI_TOKEN` if set, falls back to `KBC_TOKEN`. Headers: `Content-Type`, `x-storageapi-token`, `x-storageapi-url`.

### Stream Buffer

In-memory dict `_streams[stream_id] = {events: [], done: bool, error: str|None}`.

- `_kai_stream_consumer(stream_id, resp, client)` — Background task that reads SSE bytes from KAI, splits on `\n\n`, appends decoded event strings to the buffer. Sets `done=True` on completion/error.
- `_start_kai_stream(kai_url, headers, body)` → `stream_id` — Opens streaming `POST` to KAI via `httpx.AsyncClient` (600s timeout), spawns consumer task.

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Forwards request body to KAI, returns `{stream_id}` |
| `/api/chat/{stream_id}/poll?cursor=N` | GET | Returns `{events[], cursor, done, error}` from buffer |
| `/api/chat/{chat_id}/{action}/{approval_id}` | POST | Tool approval/rejection — wraps as `tool-approval-response` message, starts new KAI stream |

---

## 4. Frontend Implementation (Next.js / React)

### Provider Tree

```
layout.tsx → Providers (providers.tsx)
  → PersistQueryClientProvider (TanStack Query + localStorage)
    → KaiChatProvider (React Context — all KAI state)
      → KaiWidget + children
```

### KaiChatProvider (`lib/kai-context.tsx`)

Central React Context managing all chat state. Key methods:
- `sendMessage(text, bypassCache?)` — Checks 5-min response cache, injects system context on first message, starts poll loop, accumulates streaming response
- `handleApproval(approved)` — Sends tool approval/rejection via `/api/chat/{chatId}/{action}/{approvalId}`
- `abortStreaming()` — Cancels active poll via `AbortController`

Access via `useKaiChat()` hook.

### Polling Client (`pollKaiStream()` in `lib/kai-context.tsx`)

1. `POST` to `/api/chat` → get `stream_id`
2. Poll `GET /api/chat/{stream_id}/poll?cursor=N` in a loop
3. Parse each buffered SSE event: split lines, find `data:` prefix, `JSON.parse`
4. Dispatch to callbacks: `onDelta` (text), `onToolApproval`, `onToolCall`
5. Adaptive interval: 500ms if events received, 1500ms if idle
6. Supports `AbortSignal` for cancellation

### System Context Injection

Built from live app data via TanStack Query hooks (`useOrgKpis`, `useOrgGroups`, `useCurrentUser`, `usePlatformInfo`). Injected as prefix to the **first message only** — includes revenue/margin KPIs, group names with deep links, user email/role, and a `next_actions` instruction.

### Page Context Detection

`KaiWidget` reads `pathname` + `searchParams` to detect current page (group, account, performance) and updates context-aware suggestions.

### Conversation Storage (`lib/chat-storage.ts`)

localStorage-based, max 50 conversations with auto-prune. Auto-derives title from first user message. Cross-tab sync via `CustomEvent` + `storage` event. Full CRUD + Markdown export.

### Response Caching

5-minute in-memory cache keyed on lowercased query text. Bypass via `sendMessage(text, true)`.

---

## 5. Chat Message Protocol

### User Message

```json
{
  "id": "<chat_id (persists across conversation)>",
  "message": {
    "id": "<unique message UUID>",
    "role": "user",
    "parts": [{ "type": "text", "text": "<system_context (first msg)>\n\n<query>" }]
  },
  "selectedChatModel": "chat-model",
  "selectedVisibilityType": "private"
}
```

### Tool Approval Response

Same envelope, with part `{"type": "tool-approval-response", "approvalId": "...", "approved": bool}`. Add `"reason"` only when `approved: false`.

### SSE Event Types (from KAI)

| Event Type | Key Fields |
|------------|------------|
| `text-delta` | `delta: string` |
| `tool-input-start` | `toolCallId`, `toolName` |
| `tool-input-available` | `toolCallId`, `toolName` |
| `tool-output-available` | `toolCallId` |
| `tool-call` | `toolCallId`, `toolName`, `state` |
| `tool-approval-request` | `approvalId`, `toolCallId` |
| `[DONE]` | (stream complete) |

---

## 6. UI Patterns

### Follow-up Suggestions

KAI is instructed to end responses with a ` ```next_actions ` code block containing 2-3 bullet points. Frontend strips these blocks via regex (`/```(?:next_actions|suggestions?|follow.?up)?\s*\n([\s\S]*?)```/g`) and renders them as clickable suggestion chips. Fallback: keyword-based suggestions from response content.

### Pin to Dashboard

`KaiTableChart` renders tables with a **Pin** button → `pinChart()` from `lib/dashboard-storage.ts` saves chart data to localStorage → powers a custom dashboard page. Entirely client-side.

### Markdown Rendering

Custom `react-markdown` components: internal links (`/...`) use Next.js `<Link>`, external links open in new tab, tables auto-convert to interactive ECharts via `KaiTableChart`.

### Widget

Portal-rendered to `document.body` (avoids z-index/overflow issues). Fixed bottom-right, animated with Framer Motion. Auto-hides on `/assistant` page.

---

## 7. File Reference Map

**Backend:**
- `backend/main.py` — FastAPI app: KAI proxy, poll, approval endpoints, service discovery
- `backend/services/user_context.py` — Email-based auth & role resolution
- `backend/services/audit_log.py` — Audit logging middleware

**Frontend:**
- `frontend/lib/kai-context.tsx` — KaiChatProvider, pollKaiStream(), buildSystemContext(), all chat logic
- `frontend/lib/chat-storage.ts` — Conversation CRUD, localStorage, useConversationList()
- `frontend/components/kai/KaiWidget.tsx` — Floating chat button + panel
- `frontend/components/kai/KaiChat.tsx` — Main chat UI (messages, input, suggestions, approval)
- `frontend/components/kai/ChatMessage.tsx` — Message rendering (markdown, copy, streaming cursor)
- `frontend/components/kai/ConversationPanel.tsx` — Conversation history sidebar
- `frontend/components/kai/KaiTableChart.tsx` — Auto-convert tables to interactive ECharts
- `frontend/app/providers.tsx` — Provider tree (TanStack Query + KaiChatProvider)
- `frontend/app/assistant/page.tsx` — Full-page `/assistant` chat view

**Configuration:**
- `keboola-config/nginx/sites/default.conf` — Nginx routing with SSE settings
- `keboola-config/setup.sh` — Container setup (uv sync for backend)
- `keboola-config/supervisord/services/python.conf` — Uvicorn process config
- `keboola-config/supervisord/services/node.conf` — Next.js standalone process config

**Key dependencies:** Backend: `fastapi`, `httpx`, `uvicorn`, `pandas`. Frontend: `@tanstack/react-query`, `react-markdown`, `framer-motion`, `echarts-for-react`.

---

## 8. Design Decisions

| Decision | Rationale |
|----------|-----------|
| Polling instead of SSE | Keboola edge proxy ~20-30s timeout kills long SSE connections |
| In-memory event buffer | Decouples KAI's long stream from short frontend polls |
| System context on first message only | Reduces token usage; KAI maintains conversation context |
| 5-min response cache | Avoids re-running expensive KAI queries for identical questions |
| Portal-rendered widget | Avoids z-index/overflow issues from parent CSS |
| No kai-client package | Custom polling architecture needs full control |
| `KAI_TOKEN` → `KBC_TOKEN` fallback | Supports dedicated KAI token or reuse of general Storage token |
| Dynamic KAI URL discovery | KAI URL varies by Keboola stack; discovered at runtime |
| localStorage conversations | Simple, no backend state; max 50 with auto-prune |
| `next_actions` code block | Structured extraction of follow-up suggestions from KAI |
| Pin-to-dashboard | Client-side chart pinning via `dashboard-storage.ts` |
