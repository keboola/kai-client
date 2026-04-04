/**
 * KAI Client — useGroupedConversations
 * Source: keboola/kai-client/kai-nextjs/
 * Shared hook for ChatHistoryDropdown + ChatHistoryPanel.
 */

import { useState, useMemo } from 'react'
import { useKaiChat } from './kai-context'
import type { Conversation } from './chat-storage'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ConversationGroup {
  label: string
  conversations: Conversation[]
}

// ─── Date grouping ────────────────────────────────────────────────────────────

function getDateGroup(ts: number): 'Today' | 'Yesterday' | 'Earlier' {
  const startOfToday = new Date().setHours(0, 0, 0, 0)
  const startOfYesterday = startOfToday - 86_400_000
  if (ts >= startOfToday) return 'Today'
  if (ts >= startOfYesterday) return 'Yesterday'
  return 'Earlier'
}

function groupConversations(conversations: Conversation[]): ConversationGroup[] {
  const groups: ConversationGroup[] = [
    { label: 'Today', conversations: [] },
    { label: 'Yesterday', conversations: [] },
    { label: 'Earlier', conversations: [] },
  ]
  for (const conv of conversations) {
    const label = getDateGroup(conv.updatedAt)
    groups.find(g => g.label === label)!.conversations.push(conv)
  }
  return groups.filter(g => g.conversations.length > 0)
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useGroupedConversations() {
  const { conversations, conversationId, loadConversation, deleteConversation, startNewConversation } = useKaiChat()
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return conversations
    return conversations.filter(c => c.title.toLowerCase().includes(q))
  }, [conversations, search])

  const groups = useMemo(() => groupConversations(filtered), [filtered])

  return {
    groups,
    search,
    setSearch,
    activeId: conversationId,
    onLoad: loadConversation,
    onDelete: deleteConversation,
    onNew: startNewConversation,
    /** All (unfiltered) conversations — useful for counts and current-chat lookup. */
    conversations,
  }
}
