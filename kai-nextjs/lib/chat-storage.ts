/**
 * KAI Client — Conversation Storage
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

/*
 * CONVERSATION STORAGE — localStorage-based, max 50 conversations.
 * Auto-prunes oldest when limit exceeded.
 */

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

export interface Conversation {
  id: string
  chatId: string  // KAI conversation ID — MUST be persisted for context continuity
  title: string
  messages: ChatMessage[]
  createdAt: number
  updatedAt: number
}

const STORAGE_KEY = 'kai-conversations' // CUSTOMIZE: localStorage key prefix for your app
const MAX_CONVERSATIONS = 50

function load(): Conversation[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function save(conversations: Conversation[]) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations))
  } catch {
    // quota exceeded — prune and retry
    const pruned = conversations.slice(-Math.floor(MAX_CONVERSATIONS / 2))
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pruned))
  }
}

function deriveTitle(messages: ChatMessage[]): string {
  const first = messages.find(m => m.role === 'user')
  if (!first) return 'New conversation'
  const text = first.content.replace(/```[\s\S]*?```/g, '').trim()
  return text.length > 60 ? text.slice(0, 57) + '...' : text
}

export const ChatStorage = {
  list(): Conversation[] {
    return load().sort((a, b) => b.updatedAt - a.updatedAt)
  },

  get(id: string): Conversation | undefined {
    return load().find(c => c.id === id)
  },

  create(id: string, chatId?: string): Conversation {
    const conv: Conversation = {
      id,
      chatId: chatId ?? id,
      title: 'New conversation',
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    }
    const all = load()
    const pruned = all.length >= MAX_CONVERSATIONS
      ? all.sort((a, b) => a.updatedAt - b.updatedAt).slice(all.length - MAX_CONVERSATIONS + 1)
      : all
    save([...pruned, conv])
    return conv
  },

  upsert(conv: Conversation) {
    const all = load()
    const idx = all.findIndex(c => c.id === conv.id)
    const updated = { ...conv, title: deriveTitle(conv.messages), updatedAt: Date.now() }
    if (idx >= 0) {
      all[idx] = updated
    } else {
      all.push(updated)
    }
    const pruned = all.length > MAX_CONVERSATIONS
      ? all.sort((a, b) => a.updatedAt - b.updatedAt).slice(all.length - MAX_CONVERSATIONS)
      : all
    save(pruned)
  },

  addMessage(id: string, message: ChatMessage, chatId?: string) {
    const conv = this.get(id) ?? this.create(id, chatId)
    const existingIdx = conv.messages.findIndex(m => m.id === message.id)
    if (existingIdx >= 0) {
      conv.messages[existingIdx] = message // update existing (e.g. finalize content)
    } else {
      conv.messages.push(message)
    }
    this.upsert(conv)
  },

  delete(id: string) {
    save(load().filter(c => c.id !== id))
  },

  clear() {
    if (typeof window !== 'undefined') localStorage.removeItem(STORAGE_KEY)
  },
}
