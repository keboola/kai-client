'use client'

/**
 * KAI Client — Chat Context Provider
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import {
  createContext,
  useContext,
  useState,
  useRef,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react'
import { ChatStorage, type Conversation } from './chat-storage'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface KaiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  toolApproval?: { approvalId: string; toolCallId: string; toolName?: string }
}

export interface ToolCallState {
  toolCallId: string
  toolName?: string
  toolArgs?: string
  state: 'processing' | 'done' | 'error'
}

interface ResponseCache {
  text: string
  timestamp: number
}

// ─── Tool call markers (inline interleaving) ────────────────────────────────
// Zero-width-space delimited markers injected into accumulatedText so
// MessageBubble can split content and render inline tool call chips.

export const TOOL_CALL_MARKER_RE = /\u200B\[tool:([^\]]+)\]\u200B/g
export function makeToolCallMarker(id: string): string {
  return `\u200B[tool:${id}]\u200B`
}
/** Strip tool call markers from text (for storage / cache) */
export function stripToolMarkers(text: string): string {
  return text.replace(/\u200B\[tool:[^\]]+\]\u200B/g, '')
}

export type LayoutMode = 'sidebar' | 'fullscreen'

interface KaiChatContextValue {
  // Chat state
  messages: KaiMessage[]
  isStreaming: boolean
  conversationId: string
  conversations: Conversation[]
  toolCalls: ToolCallState[]
  // Platform info (for Keboola table links)
  connectionUrl: string
  projectId: string
  // Sheet/layout state
  isOpen: boolean
  layoutMode: LayoutMode
  toggleChat: () => void
  openChat: () => void
  closeChat: () => void
  expand: () => void
  collapse: () => void
  // Chat actions
  sendMessage: (text: string, bypassCache?: boolean) => Promise<void>
  handleApproval: (approved: boolean, approvalId: string) => Promise<void>
  abortStreaming: () => void
  startNewConversation: () => void
  loadConversation: (id: string) => void
  deleteConversation: (id: string) => void
}

const KaiChatContext = createContext<KaiChatContextValue | null>(null)

export function useKaiChat() {
  const ctx = useContext(KaiChatContext)
  if (!ctx) throw new Error('useKaiChat must be used within KaiChatProvider')
  return ctx
}

// ─── System context builder ───────────────────────────────────────────────────

// CUSTOMIZE: Replace with your app's page descriptions — map each route to a human-readable summary of what's on the page
const PAGE_DESCRIPTIONS: Record<string, string> = {}

function buildSystemContext(pathname: string): string {
  const currentPage = PAGE_DESCRIPTIONS[pathname] ?? ''
  // CUSTOMIZE: Replace the return value below with your app-specific system context.
  // Include: app name, page descriptions, data table schemas, KPI formulas.
  return `You are KAI, the AI assistant embedded in this Keboola data app.

The user is currently viewing: ${currentPage || pathname || 'the app'}

Help the user explore their data by answering questions, creating visualizations, and providing insights.
When showing data, prefer markdown tables. Always be concise and data-driven.`
}

// ─── SSE event parser ────────────────────────────────────────────────────────
//
// CRITICAL: Polled events are RAW SSE text strings buffered by the backend,
// including "data:" prefixes. Each event string may contain multiple lines.
// We must split on \n, find "data:" lines, strip the prefix, and JSON.parse.
//

function parseSSEEvent(raw: string): { type: string; [key: string]: any } | null {
  const lines = raw.split('\n')
  for (const line of lines) {
    if (line.startsWith('data:')) {
      const jsonStr = line.slice(5).trim()
      if (!jsonStr || jsonStr === '[DONE]') return { type: '[DONE]' }
      try {
        return JSON.parse(jsonStr)
      } catch {
        // Not valid JSON — might be a partial or non-JSON data line
        return null
      }
    }
  }
  return null
}

// ─── Polling client ───────────────────────────────────────────────────────────
//
// Polls GET /api/chat/{streamId}/poll?cursor=N for buffered SSE events.
// Adaptive interval: 500ms when events received, 1500ms when idle.
//

interface SSECallbacks {
  onDelta: (text: string) => void
  onToolApproval: (approvalId: string, toolCallId: string, toolName?: string) => void
  onToolCall: (toolCallId: string, state: string, toolName?: string, toolArgs?: string) => void
}

async function pollKaiStream(
  streamId: string,
  signal: AbortSignal,
  callbacks: SSECallbacks,
) {
  let cursor = 0
  let done = false
  const toolNames = new Map<string, string>()

  while (!done && !signal.aborted) {
    try {
      const res = await fetch(`/api/chat/${streamId}/poll?cursor=${cursor}`, { signal })
      if (!res.ok) break
      const json = await res.json()

      const rawEvents: string[] = json.events ?? []
      for (const rawEvent of rawEvents) {
        if (signal.aborted) break

        const parsed = parseSSEEvent(rawEvent)
        if (!parsed) continue

        const type = parsed.type

        if (type === '[DONE]') {
          done = true
          break
        }

        switch (type) {
          case 'text-delta':
            if (parsed.delta) callbacks.onDelta(parsed.delta)
            break
          case 'tool-input-start':
          case 'tool-input-available': {
            if (parsed.toolName && parsed.toolCallId) {
              toolNames.set(parsed.toolCallId, parsed.toolName)
            }
            // Capture any args/input the event carries
            const args = parsed.args ?? parsed.input ?? parsed.arguments
            const argsStr = args ? (typeof args === 'string' ? args : JSON.stringify(args)) : undefined
            callbacks.onToolCall(parsed.toolCallId, type, parsed.toolName, argsStr)
            break
          }
          case 'tool-output-available':
          case 'tool-call':
            callbacks.onToolCall(parsed.toolCallId, parsed.state ?? type, toolNames.get(parsed.toolCallId))
            break
          case 'tool-approval-request':
            callbacks.onToolApproval(
              parsed.approvalId,
              parsed.toolCallId,
              toolNames.get(parsed.toolCallId) ?? parsed.toolName,
            )
            break
        }
      }

      cursor = json.cursor ?? cursor + rawEvents.length
      if (json.done) done = true

      if (!done && !signal.aborted) {
        await new Promise(r => setTimeout(r, rawEvents.length > 0 ? 500 : 1500))
      }
    } catch (err: any) {
      if (err?.name === 'AbortError') break
      break
    }
  }
}

// ─── Provider ─────────────────────────────────────────────────────────────────

export function KaiChatProvider({ children }: { children: ReactNode }) {
  const [conversationId, setConversationId] = useState<string>(() => crypto.randomUUID())
  const [messages, setMessages] = useState<KaiMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversations, setConversations] = useState<Conversation[]>(() => ChatStorage.list())

  // Platform info (for Keboola table links in tool call chips)
  const [connectionUrl, setConnectionUrl] = useState('')
  const [projectId, setProjectId] = useState('')
  useEffect(() => {
    fetch('/api/platform').then(r => r.json()).then(data => {
      setConnectionUrl(data.connection_url ?? '')
      setProjectId(data.project_id ?? '')
    }).catch(() => {})
  }, [])

  // Sheet/layout state
  const [isOpen, setIsOpen] = useState(false)
  const [layoutMode, setLayoutMode] = useState<LayoutMode>(() => {
    if (typeof window === 'undefined') return 'sidebar'
    return (localStorage.getItem('kai-layout-mode') as LayoutMode) || 'sidebar'
  })

  const toggleChat = useCallback(() => setIsOpen(prev => !prev), [])
  const openChat = useCallback(() => setIsOpen(true), [])
  const closeChat = useCallback(() => {
    setIsOpen(false)
    // Always reset to sidebar on close — fullscreen is only for explicit expand
    setLayoutMode('sidebar')
    localStorage.setItem('kai-layout-mode', 'sidebar')
  }, [])
  const expand = useCallback(() => {
    setLayoutMode('fullscreen')
    localStorage.setItem('kai-layout-mode', 'fullscreen')
  }, [])
  const collapse = useCallback(() => {
    setLayoutMode('sidebar')
    localStorage.setItem('kai-layout-mode', 'sidebar')
  }, [])
  const [toolCalls, setToolCalls] = useState<ToolCallState[]>([])

  const abortRef = useRef<AbortController | null>(null)
  const responseCache = useRef<Map<string, ResponseCache>>(new Map())
  const isFirstMessage = useRef(true)
  const chatIdRef = useRef<string>(conversationId)

  const refreshConversations = useCallback(() => {
    setConversations(ChatStorage.list())
  }, [])

  const addMessage = useCallback((msg: KaiMessage) => {
    setMessages(prev => [...prev, msg])
    ChatStorage.addMessage(chatIdRef.current, {
      id: msg.id,
      role: msg.role,
      content: msg.content,
      timestamp: Date.now(),
    }, chatIdRef.current)
  }, [])

  const updateLastAssistant = useCallback((updater: (prev: string) => string) => {
    setMessages(prev => {
      const copy = [...prev]
      const last = copy[copy.length - 1]
      if (last?.role === 'assistant') {
        copy[copy.length - 1] = { ...last, content: updater(last.content) }
      }
      return copy
    })
  }, [])

  // Helper: start a KAI stream and poll it, accumulating text
  const streamAndPoll = useCallback(async (
    postUrl: string,
    body: Record<string, unknown>,
    signal: AbortSignal,
  ): Promise<string> => {
    const initRes = await fetch(postUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    if (!initRes.ok) throw new Error(`Chat request failed: ${initRes.status}`)
    const { stream_id } = await initRes.json()

    let accumulatedText = ''
    let displayedLength = 0
    let revealTimer: ReturnType<typeof setInterval> | null = null

    const startReveal = () => {
      if (revealTimer !== null) return
      revealTimer = setInterval(() => {
        if (displayedLength >= accumulatedText.length) {
          if (revealTimer !== null) { clearInterval(revealTimer); revealTimer = null }
          return
        }
        const backlog = accumulatedText.length - displayedLength
        const step = Math.max(2, Math.ceil(backlog * 0.15))
        let newLen = Math.min(displayedLength + step, accumulatedText.length)
        // Snap past any partially-revealed tool call marker
        const searchFrom = newLen - 20 > 0 ? newLen - 20 : 0
        const markerStart = accumulatedText.lastIndexOf('\u200B[tool:', searchFrom)
        if (markerStart >= 0 && markerStart < newLen) {
          const markerEnd = accumulatedText.indexOf(']\u200B', markerStart)
          if (markerEnd >= 0 && newLen < markerEnd + 2) {
            newLen = Math.min(markerEnd + 2, accumulatedText.length)
          }
        }
        displayedLength = newLen
        updateLastAssistant(() => accumulatedText.slice(0, displayedLength))
      }, 30)
    }

    await pollKaiStream(stream_id, signal, {
      onDelta: (delta) => {
        accumulatedText += delta
        startReveal()
      },
      onToolApproval: (approvalId, toolCallId, toolName) => {
        setMessages(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last?.role === 'assistant') {
            copy[copy.length - 1] = { ...last, toolApproval: { approvalId, toolCallId, toolName } }
          }
          return copy
        })
      },
      onToolCall: (toolCallId, state, toolName, toolArgs) => {
        // Inject marker into text stream when tool call first appears
        if (state === 'tool-input-start' || state === 'tool-input-available') {
          const marker = makeToolCallMarker(toolCallId)
          if (!accumulatedText.includes(marker)) {
            accumulatedText += marker
            startReveal()
          }
        }
        setToolCalls(prev => {
          const derivedState: ToolCallState['state'] =
            state.includes('output') || state === 'done' ? 'done'
            : state === 'error' ? 'error'
            : 'processing'
          const idx = prev.findIndex(tc => tc.toolCallId === toolCallId)
          if (idx >= 0) {
            const updated = [...prev]
            updated[idx] = {
              ...updated[idx],
              state: derivedState,
              toolName: toolName ?? updated[idx].toolName,
              toolArgs: toolArgs ?? updated[idx].toolArgs,
            }
            return updated
          }
          return [...prev, { toolCallId, toolName, toolArgs, state: derivedState }]
        })
      },
    })

    // Flush remaining buffered text
    if (revealTimer !== null) clearInterval(revealTimer)
    if (displayedLength < accumulatedText.length) {
      updateLastAssistant(() => accumulatedText)
    }

    return accumulatedText
  }, [updateLastAssistant])

  const sendMessage = useCallback(async (text: string, bypassCache = false) => {
    if (isStreaming) return

    const cacheKey = text.toLowerCase().trim()
    if (!bypassCache) {
      const cached = responseCache.current.get(cacheKey)
      if (cached && Date.now() - cached.timestamp < 5 * 60 * 1000) {
        const userMsg: KaiMessage = { id: crypto.randomUUID(), role: 'user', content: text }
        const assistantMsg: KaiMessage = { id: crypto.randomUUID(), role: 'assistant', content: cached.text }
        addMessage(userMsg)
        addMessage(assistantMsg)
        refreshConversations()
        return
      }
    }

    // Inject system context on first message, page context on every message
    const pathname = typeof window !== 'undefined' ? window.location.pathname : '/'
    let fullText: string
    if (isFirstMessage.current) {
      fullText = `${buildSystemContext(pathname)}\n\n${text}`
      isFirstMessage.current = false
    } else {
      fullText = `[Current page: ${pathname}]\n\n${text}`
    }

    setToolCalls([])
    const userMsg: KaiMessage = { id: crypto.randomUUID(), role: 'user', content: text }
    addMessage(userMsg)

    const assistantMsgId = crypto.randomUUID()
    const assistantMsg: KaiMessage = { id: assistantMsgId, role: 'assistant', content: '', streaming: true }
    setMessages(prev => [...prev, assistantMsg])

    abortRef.current = new AbortController()
    setIsStreaming(true)

    try {
      const accumulatedText = await streamAndPoll(
        '/api/chat',
        {
          id: chatIdRef.current,
          message: {
            id: crypto.randomUUID(),
            role: 'user',
            parts: [{ type: 'text', text: fullText }],
          },
          selectedChatModel: 'chat-model',
          selectedVisibilityType: 'private',
        },
        abortRef.current.signal,
      )

      // Finalize
      const storageContent = stripToolMarkers(accumulatedText)
      setMessages(prev => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last?.role === 'assistant') {
          copy[copy.length - 1] = { ...last, content: accumulatedText, streaming: false }
          ChatStorage.addMessage(chatIdRef.current, {
            id: last.id,
            role: 'assistant',
            content: storageContent,
            timestamp: Date.now(),
          }, chatIdRef.current)
        }
        return copy
      })

      if (accumulatedText) {
        responseCache.current.set(cacheKey, { text: accumulatedText, timestamp: Date.now() })
      }
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        updateLastAssistant(() => 'Sorry, something went wrong. Please try again.')
      }
    } finally {
      setIsStreaming(false)
      abortRef.current = null
      refreshConversations()
    }
  }, [isStreaming, addMessage, updateLastAssistant, refreshConversations, streamAndPoll])

  const handleApproval = useCallback(async (approved: boolean, approvalId: string) => {
    const toolApprovalMsg = messages.find(m => m.toolApproval?.approvalId === approvalId)
    if (!toolApprovalMsg?.toolApproval) return

    // Clear the approval UI immediately
    setMessages(prev =>
      prev.map(m =>
        m.id === toolApprovalMsg.id ? { ...m, toolApproval: undefined } : m
      )
    )

    // Add a new streaming assistant message for the approval response
    const assistantMsgId = crypto.randomUUID()
    setMessages(prev => [...prev, { id: assistantMsgId, role: 'assistant', content: '', streaming: true }])

    abortRef.current = new AbortController()
    setIsStreaming(true)

    try {
      const action = approved ? 'approve' : 'reject'
      // POST to the approval endpoint — it returns a NEW stream_id
      // that we MUST poll to get KAI's response after tool execution
      const accumulatedText = await streamAndPoll(
        `/api/chat/${chatIdRef.current}/${action}/${approvalId}`,
        { approved, ...(!approved ? { reason: 'User denied' } : {}) },
        abortRef.current.signal,
      )

      // Finalize the assistant message
      const storageContent = stripToolMarkers(accumulatedText)
      setMessages(prev => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last?.role === 'assistant') {
          copy[copy.length - 1] = { ...last, content: accumulatedText, streaming: false }
          ChatStorage.addMessage(chatIdRef.current, {
            id: last.id,
            role: 'assistant',
            content: storageContent,
            timestamp: Date.now(),
          }, chatIdRef.current)
        }
        return copy
      })
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        updateLastAssistant(() => 'Sorry, tool approval failed. Please try again.')
      }
    } finally {
      setIsStreaming(false)
      abortRef.current = null
      refreshConversations()
    }
  }, [messages, updateLastAssistant, refreshConversations, streamAndPoll])

  const abortStreaming = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsStreaming(false)
    // Remove empty assistant message if no content was accumulated
    setMessages(prev => {
      const last = prev[prev.length - 1]
      if (last?.role === 'assistant' && !last.content) {
        return prev.slice(0, -1)
      }
      return prev.map(m => m.streaming ? { ...m, streaming: false } : m)
    })
  }, [])

  const startNewConversation = useCallback(() => {
    const id = crypto.randomUUID()
    chatIdRef.current = id
    setConversationId(id)
    setMessages([])
    setToolCalls([])
    isFirstMessage.current = true
    refreshConversations()
  }, [refreshConversations])

  const loadConversation = useCallback((id: string) => {
    const conv = ChatStorage.get(id)
    if (!conv) return
    // Restore chatId from the persisted conversation — critical for KAI context continuity
    chatIdRef.current = conv.chatId ?? id
    setConversationId(id)
    setMessages(
      conv.messages.map(m => ({
        id: m.id,
        role: m.role,
        content: m.content,
      }))
    )
    isFirstMessage.current = false
  }, [])

  const deleteConversation = useCallback((id: string) => {
    ChatStorage.delete(id)
    if (id === chatIdRef.current) startNewConversation()
    else refreshConversations()
  }, [startNewConversation, refreshConversations])

  return (
    <KaiChatContext.Provider
      value={{
        messages,
        isStreaming,
        conversationId,
        conversations,
        toolCalls,
        connectionUrl,
        projectId,
        isOpen,
        layoutMode,
        toggleChat,
        openChat,
        closeChat,
        expand,
        collapse,
        sendMessage,
        handleApproval,
        abortStreaming,
        startNewConversation,
        loadConversation,
        deleteConversation,
      }}
    >
      {children}
    </KaiChatContext.Provider>
  )
}
