'use client'

/**
 * KAI Client — ChatHeader
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { Sparkles, Plus, X, Maximize2, Minimize2 } from 'lucide-react'
import { useKaiChat } from '@/lib/kai-context'
import { cn } from '@/lib/utils'
import ChatHistoryDropdown from './ChatHistoryDropdown'

// ─── Types ────────────────────────────────────────────────────────────────────

interface ChatHeaderProps {
  isFullscreen: boolean
}

// ─── Sub-component: icon button ────────────────────────────────────────────────

function IconButton({
  onClick,
  title,
  children,
  className,
  'data-testid': testId,
}: {
  onClick: () => void
  title: string
  children: React.ReactNode
  className?: string
  'data-testid'?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      data-testid={testId}
      className={cn(
        'p-1.5 rounded-md text-gray-400',
        'hover:text-brand-secondary hover:bg-gray-100',
        'transition-colors duration-150',
        className,
      )}
    >
      {children}
    </button>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ChatHeader({ isFullscreen }: ChatHeaderProps) {
  const { expand, collapse, closeChat, startNewConversation, layoutMode } = useKaiChat()
  const isSidebar = layoutMode === 'sidebar'

  return (
    <div className="flex items-center gap-2 w-full px-3 py-2">
      {/* Brand icon */}
      <Sparkles
        size={18}
        className="text-brand-primary shrink-0"
        aria-hidden="true"
      />

      {/* Chat history dropdown */}
      <ChatHistoryDropdown interactive={isSidebar} />

      {/* Right-side button group */}
      <div className="ml-auto flex items-center gap-0.5">
        {/* New chat */}
        <IconButton
          onClick={startNewConversation}
          title="New chat (Shift + A)"
          data-testid="chat-new-button"
        >
          <Plus size={16} />
        </IconButton>

        {/* Expand / Collapse */}
        {isSidebar ? (
          <IconButton
            onClick={expand}
            title="Expand chat"
            data-testid="chat-expand-button"
          >
            <Maximize2 size={16} />
          </IconButton>
        ) : (
          <IconButton
            onClick={collapse}
            title="Collapse chat"
            data-testid="chat-collapse-button"
          >
            <Minimize2 size={16} />
          </IconButton>
        )}

        {/* Close */}
        <IconButton
          onClick={closeChat}
          title="Close chat"
          data-testid="chat-close-button"
        >
          <X size={16} />
        </IconButton>
      </div>
    </div>
  )
}
