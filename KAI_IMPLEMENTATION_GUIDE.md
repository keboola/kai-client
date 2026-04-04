# KAI Implementation Guide

> **Verbatim blueprint** for integrating KAI (Keboola AI Assistant) into Next.js data apps.
> Agents: copy code from `kai-nextjs/` directory verbatim. Only modify lines marked `// CUSTOMIZE:`.
> This file is self-contained. Reading it + `kai-nextjs/` is sufficient to integrate KAI.

---

## 1. Architecture Overview

### Deployment Topology

```
Browser
  │
  :8888 (Nginx — external port, exposed by Docker)
  │
  ├── /api/chat*  →  :8050 (FastAPI backend — KAI proxy)
  ├── /api/*      →  :8050 (FastAPI backend — business logic)
  └── /*          →  :3000 (Next.js frontend — standalone)
```

All three processes run inside a single Docker container managed by **Supervisord**, with **Nginx** as the reverse proxy.

### The Polling Proxy Pattern

**Problem:** Keboola's edge proxy enforces a ~20-30s request timeout that kills long-lived SSE streams.

**Solution:** Backend buffers KAI's SSE stream in memory; frontend polls for buffered events via short-lived HTTP requests.

```
Frontend              Backend (FastAPI)              KAI Service
   │── POST /api/chat ──→│── POST {kai_url}/api/chat ──→│
   │← {stream_id} ───────│                               │
   │                      │←── SSE stream (buffered) ─────│
   │── GET /poll ────────→│                               │
   │← {events, cursor} ──│                               │
   │── GET /poll ────────→│      (repeats until done)     │
   │← {events, done} ────│                               │
```

### KAI Service Discovery

KAI URL is discovered dynamically at runtime:
1. Extract base URL: `KBC_URL.split("/v2/")[0]`
2. `GET {base}/v2/storage` with `x-storageapi-token` header
3. Find service with `id == "kai-assistant"` → use its `.url`
4. Cache globally for process lifetime

---

## 2. Project Structure

After integration, your app should have these KAI-related files:

```
frontend/
├── app/
│   ├── providers.tsx                 # KaiChatProvider wraps app
│   └── (dashboard)/
│       └── assistant/page.tsx        # Full-screen KAI chat page
├── components/
│   └── kai/                          # 20+ chat components (copy from kai-nextjs/)
│       ├── Chat.tsx                  # Sheet/drawer wrapper
│       ├── ChatButton.tsx            # Header toggle button
│       ├── SheetChatContent.tsx      # Main chat layout
│       ├── ChatHeader.tsx            # KAI logo + actions
│       ├── ChatHistoryDropdown.tsx   # Sidebar history
│       ├── ChatHistoryPanel.tsx      # Fullscreen history
│       ├── ChatInput.tsx             # Textarea + send/stop
│       ├── ChatMessageList.tsx       # Scrollable messages
│       ├── ChatContent.tsx           # Message renderer
│       ├── ChatWelcome.tsx           # Initial screen         // CUSTOMIZE
│       ├── ChatMessage.tsx           # Message wrapper
│       ├── MessageBubble.tsx         # Markdown + tools       // CUSTOMIZE
│       ├── MessageActions.tsx        # Copy/thumbs
│       ├── NextActionButtons.tsx     # Suggestion pills       // CUSTOMIZE
│       ├── SuggestedPrompts.tsx      # Legacy shim
│       ├── InlineTaskGroup.tsx       # Tool call summary
│       ├── ToolCallGroup.tsx         # Tool list
│       ├── ToolCallPanel.tsx         # Status panel
│       ├── ToolApprovalCard.tsx      # Approve/decline
│       ├── KaiTableChart.tsx         # Table→chart + pin
│       ├── ThinkingIndicator.tsx     # Animated dots
│       └── TipsBanner.tsx            # Streaming tips          // CUSTOMIZE
├── lib/
│   ├── kai-context.tsx               # KaiChatProvider         // CUSTOMIZE (system context)
│   ├── chat-storage.ts               # Conversation CRUD
│   ├── dashboard-storage.ts          # Multi-dashboard storage
│   ├── chart-config-storage.ts       # Chart library
│   ├── chart-utils.ts                # ECharts builder
│   └── utils.ts                      # cn() utility
└── app/(dashboard)/custom/           # My Dashboards page
    ├── page.tsx                      # Grid canvas
    ├── ChartBuilderSidebar.tsx       # Chart builder           // CUSTOMIZE
    └── chart-builder/
        ├── DraggableField.tsx
        ├── SortableFieldChip.tsx
        └── FieldWell.tsx

backend/
└── main.py                           # Add KAI proxy code from kai-nextjs/backend/kai-proxy.py

keboola-config/
├── nginx/sites/default.conf          # Nginx with SSE settings
├── supervisord/services/
│   ├── python.conf                   # FastAPI process
│   └── node.conf                     # Next.js process
└── setup.sh                          # Container startup
```

---

## 3. Environment & Configuration

### Backend Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `KBC_URL` | Yes | Keboola Storage API URL (may include `/v2/storage`) |
| `KBC_TOKEN` | Yes | Keboola Storage API token |
| `KBC_PROJECTID` | Recommended | Project ID (for links in system context) |
| `KAI_TOKEN` | Optional | Dedicated KAI-enabled token (falls back to `KBC_TOKEN`) |
| `DEV_USER_EMAIL` | Dev only | Simulate user context locally |

### Frontend Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BACKEND_URL` | Dev only | Backend URL for local proxy (`http://localhost:8050`) |
| `LOCAL_OIDC_EMAIL` | Dev only | Simulate OIDC user header |

### Nginx — Critical Settings for `/api/chat`

```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 600s;
gzip off;
tcp_nodelay on;
add_header X-Accel-Buffering no;
```

These prevent buffering/compression of SSE chunks. See full config in Section 12.

### Frontend Dependencies (add to package.json)

```json
{
  "@tanstack/react-query": "^5",
  "react-markdown": "^9",
  "remark-gfm": "^4",
  "framer-motion": "^11",
  "echarts-for-react": "^3",
  "echarts": "^5",
  "lucide-react": "^0.400",
  "clsx": "^2",
  "tailwind-merge": "^2",
  "react-draggable": "^4",
  "react-resizable": "^3",
  "@dnd-kit/core": "^6",
  "@dnd-kit/sortable": "^10",
  "@dnd-kit/utilities": "^3",
  "html2canvas-pro": "^1"
}
```

### Backend Dependencies (add to pyproject.toml)

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "httpx>=0.28",
    "python-dotenv>=1.0",
]
```

---

## 4. Backend: KAI Proxy

All KAI proxy code is in `kai-nextjs/backend/kai-proxy.py`. Copy it into your `backend/main.py`.

### Module State

```python
_kai_url: Optional[str] = None   # Discovered KAI URL (cached globally)
_streams: dict[str, dict] = {}   # stream_id → {events: list, done: bool, error: str|None}
```

### Key Functions

| Function | Purpose |
|----------|---------|
| `_kbc_base_url()` | Strips `/v2/storage` from `KBC_URL` |
| `_discover_kai_url()` | Discovers KAI service URL via Storage API |
| `_kai_auth_headers()` | Builds auth headers (`KAI_TOKEN` → `KBC_TOKEN` fallback) |
| `_kai_stream_consumer()` | `asyncio.create_task()` coroutine — reads raw SSE bytes, splits on `\n\n`, buffers events |
| `_start_kai_stream()` | Opens streaming POST, spawns consumer, returns `stream_id` |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Forward request to KAI, return `{stream_id}` |
| `/api/chat/{stream_id}/poll?cursor=N` | GET | Return `{events[], cursor, done, error}` |
| `/api/chat/{chat_id}/{action}/{approval_id}` | POST | Tool approval → new `{stream_id}` |

### Registration in main.py

```python
# Add to your existing main.py:

@app.post("/api/chat")
async def chat_start(request: Request):
    payload = await request.json()
    kai_url = await _discover_kai_url()
    headers = _kai_auth_headers()
    stream_id = await _start_kai_stream(kai_url, headers, payload)
    return {"stream_id": stream_id}

@app.get("/api/chat/{stream_id}/poll")
async def chat_poll(stream_id: str, cursor: int = 0):
    buffer = _streams.get(stream_id)
    if buffer is None:
        raise HTTPException(status_code=404, detail=f"Stream {stream_id!r} not found")
    events = buffer["events"][cursor:]
    new_cursor = cursor + len(events)
    done = buffer["done"]
    error = buffer["error"]
    if done and new_cursor >= len(buffer["events"]):
        _streams.pop(stream_id, None)
    return {"events": events, "cursor": new_cursor, "done": done, "error": error}

@app.post("/api/chat/{chat_id}/{action}/{approval_id}")
async def chat_approval(chat_id: str, action: str, approval_id: str, request: Request):
    payload = await request.json()
    approved = payload.get("approved", True)
    approval_message = {
        "id": chat_id,
        "message": {
            "id": str(uuid4()),
            "role": "user",
            "parts": [{
                "type": "tool-approval-response",
                "approvalId": approval_id,
                "approved": approved,
                **({"reason": payload["reason"]} if not approved and "reason" in payload else {}),
            }],
        },
        "selectedChatModel": "chat-model",
        "selectedVisibilityType": "private",
    }
    kai_url = await _discover_kai_url()
    headers = _kai_auth_headers()
    stream_id = await _start_kai_stream(kai_url, headers, approval_message)
    return {"stream_id": stream_id}
```

---

## 5. Frontend Architecture

### Provider Tree

```
layout.tsx → Providers (providers.tsx)
  → QueryClientProvider (TanStack Query: staleTime 5min, gcTime 1hr, retry 1)
    → KaiChatProvider (React Context — all KAI state)
      → children (pages + Chat widget)
```

### KaiChatProvider (`kai-nextjs/lib/kai-context.tsx`)

Central React Context managing all chat state. Provides:

**State:**
- `messages: KaiMessage[]` — Current conversation messages
- `isStreaming: boolean` — Whether KAI is responding
- `conversationId: string` — Current conversation ID
- `conversations: Conversation[]` — All saved conversations
- `toolCalls: ToolCallState[]` — Active tool executions
- `connectionUrl, projectId` — Keboola platform info

**Layout:**
- `isOpen: boolean` — Sheet visibility
- `layoutMode: 'sidebar' | 'fullscreen'` — Current layout
- `toggleChat(), openChat(), closeChat()` — Visibility controls
- `expand(), collapse()` — Layout mode controls

**Chat Actions:**
- `sendMessage(text, bypassCache?)` — Send message with 5-min response cache
- `handleApproval(approved, approvalId)` — Tool approval/rejection
- `abortStreaming()` — Cancel via AbortController
- `startNewConversation()` — Reset state
- `loadConversation(id), deleteConversation(id)` — History management

**Key Implementation Details:**

1. **System context injection** — `buildSystemContext()` is called on the **first message only**. It prepends app-specific context (page descriptions, KPI data, table schemas) to the user's query. Subsequent messages only include the current page context.

2. **SSE event parsing** — `parseSSEEvent(raw)` splits raw SSE text on newlines, finds `data:` lines, strips the prefix, and JSON.parses. Events arrive as raw strings with `data:` prefixes from the backend buffer.

3. **Polling client** — `pollKaiStream()` polls `GET /api/chat/{streamId}/poll?cursor=N` with adaptive intervals: 500ms when events received, 1500ms when idle. Supports `AbortSignal` for cancellation.

4. **Text reveal mechanism** — Accumulated text is revealed in chunks (15% of backlog per 30ms interval) for a typing effect. Snaps past partial tool call markers.

5. **Response caching** — 5-minute in-memory cache keyed on lowercased query text. Bypass via `sendMessage(text, true)`.

6. **Tool call markers** — Zero-width-space delimited: `\u200B[tool:toolCallId]\u200B`. Injected inline during streaming, split at render time for chip display.

### `// CUSTOMIZE:` in kai-context.tsx

The `buildSystemContext()` function is the **primary customization point**. It must include:

```typescript
// CUSTOMIZE: Replace this entire function with your app's context
function buildSystemContext(pathname: string): string {
  return `
You are KAI, an AI assistant for [App Name].

## Current Page
${getPageDescription(pathname)}

## Navigation
${pages.map(p => `- [${p.label}](${p.href}): ${p.description}`).join('\n')}

## Data Tables
${tables.map(t => `### ${t.name}\nColumns: ${t.columns.join(', ')}\nGrain: ${t.grain}`).join('\n\n')}

## KPI Calculations
${kpis.map(k => `- **${k.label}**: ${k.formula} (source: ${k.source})`).join('\n')}

## Response Guidelines
- End every response with a \`\`\`next_actions code block containing 2-3 suggested follow-up questions
- When showing data, prefer tables over prose
- Link to relevant pages using markdown: [Page Name](/route)
`
}
```

---

## 6. Component Hierarchy

All components are in `kai-nextjs/components/kai/`. Copy verbatim.

### Shell Layer

| Component | Lines | Purpose |
|-----------|-------|---------|
| `Chat.tsx` | 53 | Right-side sheet/drawer with sidebar (420px) and fullscreen modes |
| `ChatButton.tsx` | 33 | Header toggle button (Sparkles icon, press 'A' shortcut) |
| `SheetChatContent.tsx` | 100 | Main layout: header + history panel + messages + input |

### Header & Navigation

| Component | Lines | Purpose |
|-----------|-------|---------|
| `ChatHeader.tsx` | 107 | KAI logo, history dropdown, new/expand/close buttons |
| `ChatHistoryDropdown.tsx` | 198 | Sidebar mode: searchable conversation dropdown |
| `ChatHistoryPanel.tsx` | 167 | Fullscreen mode: left sidebar with conversation list |

### Messages & Input

| Component | Lines | Purpose |
|-----------|-------|---------|
| `ChatMessageList.tsx` | 63 | Auto-scrolling container (smooth scroll, 80px threshold) |
| `ChatContent.tsx` | 97 | Maps messages to bubbles + tool approvals + actions |
| `ChatMessage.tsx` | 95 | Message wrapper with avatar + bubble + tools |
| `MessageBubble.tsx` | 484 | **Largest component** — markdown rendering, inline tool chips, KaiTableChart integration |
| `MessageActions.tsx` | 44 | Hover-revealed copy/thumbs buttons |
| `ChatInput.tsx` | 122 | Textarea with send/stop button, Shift+Enter for newline |
| `ChatWelcome.tsx` | 89 | Initial screen with starter prompts (`// CUSTOMIZE`) |

### Suggestions & Indicators

| Component | Lines | Purpose |
|-----------|-------|---------|
| `NextActionButtons.tsx` | 113 | "What's next?" suggestion pills from `next_actions` blocks |
| `SuggestedPrompts.tsx` | 49 | Legacy suggestion shim |
| `ThinkingIndicator.tsx` | 19 | Three animated bouncing dots |
| `TipsBanner.tsx` | 55 | Animated tips during streaming (`// CUSTOMIZE`) |

### Tool Execution

| Component | Lines | Purpose |
|-----------|-------|---------|
| `InlineTaskGroup.tsx` | 119 | Collapsible tool call summary with status icons |
| `ToolCallGroup.tsx` | 62 | Simple tool call list |
| `ToolCallPanel.tsx` | 136 | Colored status panel (blue/amber/green/red) |
| `ToolApprovalCard.tsx` | 50 | "Action Required" card with approve/decline |

### Data Visualization

| Component | Lines | Purpose |
|-----------|-------|---------|
| `KaiTableChart.tsx` | 154 | Table/chart toggle, pin to dashboard, numeric detection |

### Component Dependencies

```
Chat ← kai-context, SheetChatContent
SheetChatContent ← ChatHeader, ChatMessageList, ChatWelcome, ChatInput, TipsBanner, ChatHistoryPanel
ChatHeader ← ChatHistoryDropdown, kai-context
ChatContent ← MessageBubble, MessageActions, NextActionButtons, ThinkingIndicator, ToolApprovalCard
MessageBubble ← KaiTableChart, kai-context (TOOL_CALL_MARKER_RE)
KaiTableChart ← dashboard-storage (pinChart, unpinChart, isPinned)
NextActionButtons ← kai-context (sendMessage, collapse)
```

---

## 7. My Dashboards

My Dashboards is a **mandatory feature** in every KAI-enabled app. It provides a drag-and-drop chart canvas where users can:

1. **Pin charts from KAI conversations** → KaiTableChart's Pin button saves to dashboard
2. **Build custom charts** → Chart builder sidebar with drag/drop field wells
3. **Manage multiple dashboards** → Create, rename, delete named dashboards
4. **Export** → PNG/PDF via html2canvas-pro

### Architecture

```
KAI Chat                                    My Dashboards
┌──────────────────────┐                   ┌──────────────────────────────┐
│ KaiTableChart        │   pinChart()      │ Dashboard Canvas (page.tsx)  │
│   Table data →       │──────────────────→│   Drag/resize grid           │
│   [Pin to Dashboard] │                   │   Magnetic snap (24px)       │
└──────────────────────┘                   │   Collision detection        │
                                           │                              │
ChartBuilderSidebar                        │ Chart Types:                 │
┌──────────────────────┐                   │   PinnedChart (static/KAI)   │
│ Data source selector │   Save & Add     │   DynamicChart (live query)  │
│ Drag/drop field wells│──────────────────→│                              │
│ Chart type picker    │                   │ Export: PNG / PDF            │
│ Live preview         │                   └──────────────────────────────┘
└──────────────────────┘
```

### Files (from `kai-nextjs/custom-dashboard/` and `kai-nextjs/lib/`)

| File | Purpose |
|------|---------|
| `lib/dashboard-storage.ts` | Multi-dashboard CRUD, max 20 charts, max 10 dashboards |
| `lib/chart-config-storage.ts` | Chart library (saved configs), max 50 |
| `lib/chart-utils.ts` | `buildOption()` → ECharts options from table data |
| `custom-dashboard/page.tsx` | Grid canvas with drag/resize/snap/export |
| `custom-dashboard/ChartBuilderSidebar.tsx` | 3-mode builder (`// CUSTOMIZE: data sources`) |
| `custom-dashboard/chart-builder/*.tsx` | DnD field components |

### Backend Requirements

Add these endpoints for dynamic charts:

```python
# backend/routers/query.py
@router.get("/api/data-schema")
def data_schema():
    """Returns available data sources with their dimensions and measures."""
    # CUSTOMIZE: Define your app's data sources
    return {
        "sources": [
            {
                "id": "table_short_name",
                "label": "Table Display Name",
                "dimensions": [{"name": "col", "label": "Column Label"}],
                "measures": [{"name": "col", "label": "Column Label", "agg": "sum"}],
                "date_col": "date_column_name",
                "supports_period": True,
            }
        ]
    }

@router.get("/api/query-data")
def query_data(source: str, dimensions: str, measures: str, period: str = "12m"):
    """Execute user-built query and return results."""
    # CUSTOMIZE: Build SQL/pandas query from parameters
    ...
```

### NavTabs Integration

```tsx
// Add to NavTabs component:
{ label: 'My Dashboards', href: '/custom' }
// Place AFTER all data pages, BEFORE AI Assistant tab
```

---

## 8. Chat Message Protocol

### User Message

```json
{
  "id": "<chat_id (persists across conversation)>",
  "message": {
    "id": "<unique UUID>",
    "role": "user",
    "parts": [{ "type": "text", "text": "<system_context (first msg)>\n\n<query>" }]
  },
  "selectedChatModel": "chat-model",
  "selectedVisibilityType": "private"
}
```

### Tool Approval Response

Same envelope, with part:
```json
{
  "type": "tool-approval-response",
  "approvalId": "<approval_id>",
  "approved": true,
  "reason": "optional, only when approved: false"
}
```

### SSE Event Types (from KAI)

| Event Type | Key Fields | Meaning |
|------------|------------|---------|
| `text-delta` | `delta: string` | Streaming text chunk |
| `tool-input-start` | `toolCallId`, `toolName` | Tool started |
| `tool-input-available` | `toolCallId`, `toolName`, `args` | Tool args ready |
| `tool-output-available` | `toolCallId` | Tool output ready |
| `tool-call` | `toolCallId`, `toolName`, `state` | State change |
| `tool-approval-request` | `approvalId`, `toolCallId` | User must approve |
| `[DONE]` | — | Stream complete |

---

## 9. Customization Guide

These are the ONLY parts that vary between apps. Everything else is copied verbatim.

### 9.1 `kai-context.tsx` → `buildSystemContext()`

**What:** The system prompt injected on the first message. Describes your app's pages, data, KPIs, and response guidelines.

**Pattern:**
```typescript
function buildSystemContext(pathname: string): string {
  // CUSTOMIZE: Replace with your app's context
  const pageDescriptions: Record<string, string> = {
    '/': 'Overview page showing [your KPIs]',
    '/details': 'Detailed breakdown of [your data]',
    // ... one entry per page
  }

  const currentPage = pageDescriptions[pathname] || 'Unknown page'

  return `You are KAI, an AI assistant for ${APP_NAME}.

## Current Page
${currentPage}

## Available Pages
${Object.entries(pageDescriptions).map(([path, desc]) => `- [${desc}](${path})`).join('\n')}

## Data Tables
// Describe each Keboola table: columns, grain, relationships

## Metrics & KPIs
// List each KPI with its formula and data source

## Response Guidelines
- Be concise and data-driven
- Use tables for structured data
- Link to relevant app pages using [Page Name](/route) syntax
- End every response with:
\`\`\`next_actions
- Suggested follow-up 1
- Suggested follow-up 2
\`\`\`
`
}
```

### 9.2 `ChatWelcome.tsx` → Starter Prompts

**What:** The welcome screen shown before any messages. Contains 3 starter prompt buttons.

```tsx
// CUSTOMIZE: Replace these with app-specific starter queries
const starters = [
  { icon: BarChart2, label: 'How is [metric] trending?', query: 'Show me [metric] trends' },
  { icon: Users, label: 'Top [entities]', query: 'Who are the top [entities]?' },
  { icon: Clock, label: 'Peak [time periods]', query: 'When are the peak [time periods]?' },
]
```

### 9.3 `TipsBanner.tsx` → Tips Array

**What:** Rotating tips shown during KAI streaming responses.

```tsx
// CUSTOMIZE: Replace with app-specific tips
const TIPS = [
  'Tip: Ask about [domain-specific insight]',
  'Tip: Try "Compare X vs Y" for [comparison type]',
  // ... 5-7 tips
]
```

### 9.4 `NextActionButtons.tsx` → Page Name Highlights

**What:** Page names in suggestion pills are highlighted in brand-primary color.

```tsx
// CUSTOMIZE: Replace with your app's page names
const PAGE_NAMES = ['Overview', 'Details'] // CUSTOMIZE: Add your app's page names
```

### 9.5 `MessageBubble.tsx` → ARG_LABELS + Table IDs

**What:** Friendly labels for tool call arguments and Keboola table ID mappings.

```tsx
// CUSTOMIZE: Map your app's Keboola table short names to full IDs
const TABLE_ID_MAP: Record<string, string> = {
  'short_name': 'out.c-bucket.table_name',
}
```

### 9.6 `ChartBuilderSidebar.tsx` → Data Sources

**What:** Available data sources for the chart builder.

```tsx
// CUSTOMIZE: Replace with your app's data sources
type DataSource = 'table1' | 'table2' | 'table3'
const SOURCE_LABELS: Record<DataSource, string> = { ... }
const SOURCE_BADGE_COLORS: Record<DataSource, string> = { ... }
```

---

## 10. Styling: KAI CSS

Copy `kai-nextjs/css/kai-sheet.css` into your `app/globals.css` after the `@theme` block.

Key CSS classes:
- `.kai-prose` — Markdown prose overrides matching brand colors
- `.kai-dot` — Bouncing animation for thinking indicator
- `.kai-textarea` — Auto-sizing textarea with `field-sizing: content`
- `.kai-sheet` — Fixed right-side drawer with CSS transitions
- `.kai-sheet-overlay` — Semi-transparent overlay for fullscreen mode

Layout modes controlled by data attributes:
```css
.kai-sheet[data-state="open"]           /* Visible */
.kai-sheet[data-layout="sidebar"]       /* 420px width */
.kai-sheet[data-layout="fullscreen"]    /* 100% width */
```

---

## 11. Deployment

### Nginx Config (`keboola-config/nginx/sites/default.conf`)

```nginx
server {
    listen 8888;
    server_name _;

    # Keboola health probe: POST to exact root only
    # MUST be exact match — a server-level if() intercepts ALL POSTs
    location = / {
        if ($request_method = POST) {
            return 200;
        }
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Chat/SSE streaming — MUST come BEFORE /api/
    location /api/chat {
        proxy_pass http://127.0.0.1:8050;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        gzip off;
        tcp_nodelay on;
        add_header X-Accel-Buffering no;
    }

    # Other API routes
    location /api/ {
        proxy_pass http://127.0.0.1:8050;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Next.js frontend (catch-all)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Supervisord — Python Backend (`keboola-config/supervisord/services/python.conf`)

```ini
[program:python-api]
command=uv run uvicorn main:app --host 127.0.0.1 --port 8050
directory=/app/backend
autostart=true
autorestart=true
startsecs=5
startretries=3
stopsignal=TERM
stopwaitsecs=10
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

### Supervisord — Next.js Frontend (`keboola-config/supervisord/services/node.conf`)

```ini
[program:node-frontend]
command=node /app/frontend/.next/standalone/server.js
directory=/app
environment=PORT=3000,HOSTNAME=127.0.0.1
autostart=true
autorestart=true
startsecs=5
startretries=3
stopsignal=TERM
stopwaitsecs=10
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

### Container Startup (`keboola-config/setup.sh`)

```bash
#!/bin/bash
set -Eeuo pipefail
# Install Python deps only. Next.js is pre-built.
cd /app/backend && uv sync
```

### Build Commands

```bash
# Frontend (run BEFORE deployment, commit output)
cd frontend && npm install && npm run build
# Output: .next/standalone/server.js — MUST be committed to repo

# Backend (runs at container startup via setup.sh)
cd backend && uv sync
```

### Local Development

```bash
# Terminal 1: Backend
cd backend && uv sync && uv run uvicorn main:app --host 127.0.0.1 --port 8050

# Terminal 2: Frontend
cd frontend && npm install && npm run dev -- --port 3000
```

---

## 12. Verification Checklist

After deployment, verify every item. Items marked 🔧 can be auto-fixed.

### Tier 1: Infrastructure

1. `GET /api/health` → `{"status": "ok"}`
2. `GET /api/platform` → `{connection_url, project_id}` both non-null
3. `GET /api/me` → `{email, role, is_authenticated}` with real user email

### Tier 2: KAI Integration

4. `POST /api/chat` with message body → `{stream_id}` returned
5. `GET /api/chat/{stream_id}/poll?cursor=0` → `{events, cursor, done}` with `text-delta` events
6. Stream completes: `done: true` and `[DONE]` event received
7. Tool approval: `POST /api/chat/{chatId}/approve/{approvalId}` → new `{stream_id}`
8. Buffer cleanup: completed streams removed from memory after final poll

### Tier 3: Frontend Behavior

9. Chat sheet opens on button click, closes on X
10. Chat expands to fullscreen, collapses back to sidebar
11. Conversation persists in localStorage after page refresh
12. `chatId` (KAI conversation ID) preserved across sessions
13. Tables in responses render as interactive KaiTableChart
14. Suggestion chips appear at end of response and are clickable
15. Internal markdown links navigate via Next.js router (no full reload)
16. KAI is accessed via ChatButton in Header (opens as sidebar sheet)

### Tier 4: My Dashboards

17. My Dashboards page loads at `/custom`
18. Pin button in KaiTableChart saves chart to dashboard
19. Charts are draggable and resizable on the grid
20. Chart builder sidebar opens and can create new charts

### Tier 5: Edge Cases

21. Abort: stop button cancels poll, removes empty assistant message
22. Multiple conversations: new chat resets state correctly
23. 5-minute response cache: identical query returns cached response
24. Supervisord auto-restart: kill process, verify it restarts

---

## 13. Anti-Patterns & Pitfalls

### Backend — NEVER Do These

| NEVER | ALWAYS | Why |
|-------|--------|-----|
| `BackgroundTasks.add_task()` for KAI streams | `asyncio.create_task()` | BackgroundTasks runs after response; stream must start immediately |
| `aiter_lines()` for SSE parsing | `aiter_bytes()` + split on `b"\n\n"` | SSE events are delimited by double newlines, not single lines |
| Forget to strip `/v2/storage` from `KBC_URL` | `kbc_url.split("/v2/")[0]` | Service discovery URL would be malformed |
| Omit `/api/chat` from KAI endpoint | `{kai_url}/api/chat` | Discovered URL is the service root; you MUST append the path |
| Share httpx client across streams | Each stream gets its own client | Concurrent reads would corrupt |
| Skip `finally` in stream consumer | Always close `resp` and `client` | Resource leak on errors |

### Frontend — NEVER Do These

| NEVER | ALWAYS | Why |
|-------|--------|-----|
| Direct SSE (`EventSource`) | Polling proxy pattern | Keboola edge proxy kills connections at 20-30s |
| Inject system context on every message | First message only | Tokens are expensive; KAI maintains context |
| `JSON.parse()` polled events directly | Parse `data:` prefix first | Events are raw SSE strings with `data:` lines |
| Route directly to `/assistant` | Use ChatButton in Header | `/assistant` route no longer exists — KAI opens as a sidebar sheet |
| Store tool markers in localStorage | Strip via `stripToolMarkers()` | `\u200B[tool:...]` markers would show in loaded conversations |

### Deployment — NEVER Do These

| NEVER | ALWAYS | Why |
|-------|--------|-----|
| `npm run build` at container startup | Pre-build, commit `.next/standalone/` | Saves 30-60s startup time; no Node build tools needed in container |
| Omit `output: 'standalone'` in next.config.ts | Always include it | Standalone output is required for the server.js deployment |
| Server-level `if ($request_method = POST)` in Nginx | Exact match `location = /` | Server-level if intercepts ALL POSTs including `/api/chat` |
| `chunked_transfer_encoding off` alone | Also add `gzip off` + `tcp_nodelay on` | All three are needed to prevent SSE buffering |
| Wrong Nginx location order | `= /` > `/api/chat` > `/api/` > `/` | More specific prefixes must come first |

---

## 14. Design Decisions

| Decision | Rationale |
|----------|-----------|
| Polling instead of SSE | Keboola edge proxy ~20-30s timeout kills long SSE connections |
| In-memory event buffer | Decouples KAI's long stream from short frontend polls |
| System context on first message only | Reduces token usage; KAI maintains conversation context |
| 5-min response cache | Avoids re-running expensive KAI queries for identical questions |
| Sheet/drawer (not floating widget) | Better UX for data apps; sidebar + fullscreen modes |
| No kai-client package dependency | Custom polling architecture needs full control |
| `KAI_TOKEN` → `KBC_TOKEN` fallback | Supports dedicated KAI token or reuse of general Storage token |
| Dynamic KAI URL discovery | KAI URL varies by Keboola stack; discovered at runtime |
| localStorage conversations | Simple, no backend state; max 50 with auto-prune |
| `next_actions` code block | Structured extraction of follow-up suggestions from KAI |
| Pin-to-dashboard (client-side) | No server state needed; instant, works offline |
| Multi-dashboard with chart builder | Users can create custom analytics views beyond KAI suggestions |
