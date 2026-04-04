# KAI Next.js Integration — Quick Setup

Verbatim component files for integrating KAI (Keboola AI Assistant) into Next.js data apps.
See `../KAI_IMPLEMENTATION_GUIDE.md` for full architecture documentation.

## Prerequisites

- **Next.js 15** + **React 19** + **Tailwind CSS 4**
- **FastAPI** backend with Keboola data loader
- **keboola-config/** (Nginx + Supervisord) for deployment

## 1. Install Dependencies

```bash
cd frontend
npm install @tanstack/react-query react-markdown remark-gfm framer-motion \
  echarts echarts-for-react lucide-react clsx tailwind-merge \
  react-draggable react-resizable @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities \
  html2canvas-pro
```

## 2. Copy Files

Copy from this directory into your app, preserving structure:

| Source | Destination | Notes |
|--------|-------------|-------|
| `lib/*.ts(x)` | `frontend/lib/` | Core state, storage, utilities |
| `components/kai/*.tsx` | `frontend/components/kai/` | All chat UI components |
| `custom-dashboard/*.tsx` | `frontend/app/(dashboard)/custom/` | My Dashboards page |
| `custom-dashboard/chart-builder/*.tsx` | `frontend/app/(dashboard)/custom/chart-builder/` | DnD field components |
| `css/kai-sheet.css` | Append to `frontend/app/globals.css` | KAI sheet styles |
| `backend/kai-proxy.py` | Merge into `backend/main.py` | KAI proxy endpoints |

## 3. Provider Setup

Wrap your app in `KaiChatProvider`:

```tsx
// frontend/app/providers.tsx
'use client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { KaiChatProvider } from '@/lib/kai-context'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5 * 60 * 1000, gcTime: 60 * 60 * 1000, retry: 1 } },
})

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <KaiChatProvider>{children}</KaiChatProvider>
    </QueryClientProvider>
  )
}
```

## 4. Header Integration

Add `ChatButton` to your header and render `Chat` in your layout:

```tsx
// In your Header component:
import { ChatButton } from '@/components/kai/ChatButton'
// Add <ChatButton /> to the right side of your header

// In your layout or providers:
import { Chat } from '@/components/kai/Chat'
// Render <Chat /> alongside your page content (it's a fixed-position sheet)
```

## 5. NavTabs

Add these tabs:

```tsx
{ label: 'My Dashboards', href: '/custom' }    // Always present, before AI
{ label: 'AI Assistant', href: '/assistant' }   // Last tab
```

## 6. Assistant Page

Create `frontend/app/(dashboard)/assistant/page.tsx`:

```tsx
'use client'
import { useLayoutEffect } from 'react'
import { useKaiChat } from '@/lib/kai-context'

export default function AssistantPage() {
  const { openChat, expand } = useKaiChat()
  useLayoutEffect(() => { openChat(); expand() }, [openChat, expand])
  return <div className="flex items-center justify-center h-64 text-gray-400 text-sm">KAI Assistant is open.</div>
}
```

## 7. Backend Integration

Add KAI proxy endpoints to your `backend/main.py`:
1. Copy functions from `backend/kai-proxy.py` into main.py
2. Register endpoints: `POST /api/chat`, `GET /api/chat/{stream_id}/poll`, `POST /api/chat/{chat_id}/{action}/{approval_id}`
3. Add `/api/data-schema` and `/api/query-data` for My Dashboards chart builder

## 8. Customization Checklist

Only modify lines marked `// CUSTOMIZE:`:

- [ ] `lib/kai-context.tsx` → `buildSystemContext()` — Your app's page descriptions, KPIs, data schemas
- [ ] `components/kai/ChatWelcome.tsx` → Starter prompt buttons
- [ ] `components/kai/TipsBanner.tsx` → Streaming tips array
- [ ] `components/kai/NextActionButtons.tsx` → Page name highlights
- [ ] `components/kai/MessageBubble.tsx` → ARG_LABELS + table ID mappings
- [ ] `custom-dashboard/ChartBuilderSidebar.tsx` → DataSource type, SOURCE_LABELS, SOURCE_BADGE_COLORS
- [ ] `lib/dashboard-storage.ts` → Storage key prefixes (optional)

## 9. Nginx Configuration

Ensure your `keboola-config/nginx/sites/default.conf` has the `/api/chat` location with:
```nginx
proxy_buffering off; proxy_cache off; proxy_read_timeout 600s;
gzip off; tcp_nodelay on; add_header X-Accel-Buffering no;
```

This MUST come BEFORE the general `/api/` location block.
