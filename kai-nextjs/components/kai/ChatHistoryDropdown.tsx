'use client'

/**
 * KAI Client — ChatHistoryDropdown
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useState, useRef, useEffect } from 'react'
import { ChevronUp, ChevronDown, Search, Plus } from 'lucide-react'
import { useGroupedConversations } from '@/lib/use-grouped-conversations'
import { cn } from '@/lib/utils'

// ─── Types ────────────────────────────────────────────────────────────────────

interface ChatHistoryDropdownProps {
  interactive?: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ChatHistoryDropdown({ interactive = true }: ChatHistoryDropdownProps) {
  const { groups, search, setSearch, activeId, onLoad, onNew, conversations } = useGroupedConversations()
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Find current chat title
  const currentChat = conversations.find(c => c.id === activeId)
  const isNewChat = !currentChat || currentChat.messages.length === 0
  const currentTitle = isNewChat ? 'New chat' : (currentChat?.title ?? 'Loading chat…')

  // Groups already exclude activeId? No — filter it out for the dropdown list
  const dropdownGroups = groups.map(g => ({
    ...g,
    conversations: g.conversations.filter(c => c.id !== activeId),
  })).filter(g => g.conversations.length > 0)

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return
    function handleOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [isOpen, setSearch])

  // Non-interactive mode: just show title
  if (!interactive) {
    return (
      <span className="text-sm font-medium text-brand-secondary truncate max-w-[160px]">
        {currentTitle}
      </span>
    )
  }

  const handleOpenChange = (next: boolean) => {
    setIsOpen(next)
    if (!next) setSearch('')
  }

  const handleSelect = (id: string | null) => {
    if (id === null) {
      onNew()
    } else if (id !== activeId) {
      onLoad(id)
    }
    setIsOpen(false)
    setSearch('')
  }

  const hasResults = dropdownGroups.length > 0
  const emptyMessage =
    search && !hasResults ? 'No chats found' : conversations.length <= 1 ? 'No other chats' : ''

  return (
    <div ref={containerRef} className="relative min-w-0">
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => handleOpenChange(!isOpen)}
        className={cn(
          'flex items-center gap-1 px-2 py-1 rounded-lg text-sm font-medium',
          'text-brand-secondary hover:bg-gray-100 transition-colors duration-150',
          'max-w-[180px] min-w-0',
        )}
      >
        <span className="truncate">{currentTitle}</span>
        {isOpen ? (
          <ChevronUp size={14} className="shrink-0 text-gray-400" />
        ) : (
          <ChevronDown size={14} className="shrink-0 text-gray-400" />
        )}
      </button>

      {/* Dropdown popover */}
      {isOpen && (
        <div
          className={cn(
            'absolute left-0 top-full mt-1 z-50',
            'w-64 bg-white border border-border rounded-xl shadow-lg',
            'flex flex-col overflow-hidden',
          )}
        >
          {/* Search input */}
          <div className="p-2 border-b border-border">
            <div className="flex items-center gap-2 bg-surface border border-border rounded-lg px-2 py-1.5">
              <Search size={12} className="text-gray-400 shrink-0" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search chats..."
                autoFocus
                className="text-xs bg-transparent flex-1 outline-none text-brand-secondary placeholder:text-gray-400"
              />
            </div>
          </div>

          {/* Scrollable list */}
          <div className="max-h-72 overflow-y-auto py-1">
            {!hasResults && (
              <p className="text-xs text-gray-400 text-center py-4 px-3">
                {emptyMessage || 'No chats found'}
              </p>
            )}

            {dropdownGroups.map(group => (
              <div key={group.label}>
                <div className="px-3 pt-2 pb-1">
                  <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                    {group.label}
                  </span>
                </div>
                {group.conversations.map(chat => (
                  <button
                    key={chat.id}
                    type="button"
                    onClick={() => handleSelect(chat.id)}
                    className={cn(
                      'w-full flex items-center px-3 py-1.5 text-left text-xs',
                      'text-brand-secondary hover:bg-surface transition-colors duration-100',
                    )}
                  >
                    <span className="truncate">{chat.title}</span>
                  </button>
                ))}
              </div>
            ))}
          </div>

          {/* Separator */}
          <div className="border-t border-border" />

          {/* New chat button */}
          <button
            type="button"
            onClick={() => handleSelect(null)}
            className={cn(
              'flex items-center gap-2 px-3 py-2 text-xs font-medium',
              'text-brand-primary hover:bg-surface transition-colors duration-100',
            )}
          >
            <Plus size={14} />
            New chat
          </button>
        </div>
      )}
    </div>
  )
}
