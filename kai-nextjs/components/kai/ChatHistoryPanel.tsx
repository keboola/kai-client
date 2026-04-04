'use client'

/**
 * KAI Client — ChatHistoryPanel
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { Search, Plus, MessageSquare, Trash2 } from 'lucide-react'
import { useGroupedConversations } from '@/lib/use-grouped-conversations'
import { cn } from '@/lib/utils'

// ─── Types ────────────────────────────────────────────────────────────────────

interface ChatHistoryPanelProps {
  isOpen?: boolean
  onClose?: () => void
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ChatHistoryPanel({ isOpen = true, onClose }: ChatHistoryPanelProps) {
  const { groups, search, setSearch, activeId, onLoad, onDelete, onNew, conversations } = useGroupedConversations()

  const handleNewChat = () => {
    onNew()
    onClose?.()
  }

  const handleSelect = (id: string) => {
    onLoad(id)
    onClose?.()
  }

  const hasResults = groups.length > 0 || conversations.length === 0

  return (
    <div
      className={cn(
        'flex flex-col h-full bg-surface border-r border-border shrink-0',
        'transition-[width] duration-300 ease-out overflow-hidden',
        isOpen ? 'w-64' : 'w-0',
      )}
      aria-hidden={!isOpen}
    >
      <div className="w-64 flex flex-col h-full">
        {/* New conversation button */}
        <div className="px-3 py-3 border-b border-border">
          <button
            onClick={handleNewChat}
            type="button"
            className={cn(
              'w-full flex items-center gap-2 px-3 py-2 rounded-lg',
              'bg-brand-primary/8 text-brand-primary text-xs font-medium',
              'hover:bg-brand-primary/12 transition-colors duration-150',
            )}
          >
            <Plus size={14} />
            New conversation
          </button>
        </div>

        {/* Search */}
        <div className="px-3 py-2 border-b border-border">
          <div className="flex items-center gap-2 bg-white border border-border rounded-lg px-2 py-1.5">
            <Search size={12} className="text-gray-400 shrink-0" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search chats..."
              className="text-xs bg-transparent flex-1 outline-none text-brand-secondary placeholder:text-gray-400"
            />
          </div>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto py-1">
          {!hasResults ? (
            <p className="text-xs text-gray-400 text-center py-8 px-3">
              {search ? 'No results found.' : 'No conversations yet.'}
            </p>
          ) : (
            groups.map(({ label, conversations: items }) => (
              <div key={label}>
                {/* Group label */}
                <div className="px-4 pt-3 pb-1">
                  <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                    {label}
                  </span>
                </div>

                {/* Items */}
                {items.map(conv => {
                  const isActive = conv.id === activeId
                  return (
                    <div
                      key={conv.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => handleSelect(conv.id)}
                      onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && handleSelect(conv.id)}
                      className={cn(
                        'group flex items-center gap-2 px-3 py-2 cursor-pointer rounded-md mx-1',
                        'transition-colors duration-150',
                        isActive
                          ? 'bg-brand-primary/8 text-brand-primary'
                          : 'hover:bg-white text-brand-secondary/70',
                      )}
                    >
                      <MessageSquare size={12} className="shrink-0" />
                      <span className="flex-1 text-xs truncate">{conv.title}</span>
                      <button
                        type="button"
                        onClick={e => {
                          e.stopPropagation()
                          onDelete(conv.id)
                        }}
                        className="opacity-0 group-hover:opacity-100 p-1 rounded text-gray-400 hover:text-negative transition-all duration-150 shrink-0"
                        title="Delete conversation"
                        aria-label="Delete conversation"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  )
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
