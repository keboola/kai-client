'use client'

/**
 * KAI Client — ChatMessage
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { KaiMessage } from '@/lib/kai-context'
import MessageBubble, { stripNextActions } from './MessageBubble'
import MessageActions from './MessageActions'
import SuggestedPrompts from './SuggestedPrompts'
import ToolApprovalCard from './ToolApprovalCard'
import ToolCallGroup from './ToolCallGroup'

interface ToolCall {
  toolCallId: string
  toolName?: string
  state: 'processing' | 'done' | 'error'
}

interface ChatMessageProps {
  message: KaiMessage
  isLast?: boolean
  onSuggestionClick?: (text: string) => void
  onApprove?: (approvalId: string) => void
  onReject?: (approvalId: string) => void
  toolCalls?: ToolCall[]
}

export default function ChatMessage({
  message,
  isLast = false,
  onSuggestionClick,
  onApprove,
  onReject,
  toolCalls,
}: ChatMessageProps) {
  const isAssistant = message.role === 'assistant'
  const isUser = message.role === 'user'
  const { suggestions } = stripNextActions(message.content)

  return (
    <div
      className={cn(
        'flex gap-3',
        isUser ? 'flex-row-reverse' : '',
        'group',
      )}
    >
      {/* Sparkles avatar — assistant only */}
      {isAssistant && (
        <div className="w-7 h-7 rounded-full bg-brand-primary/10 flex items-center justify-center shrink-0">
          <Sparkles size={14} className="text-brand-primary" />
        </div>
      )}

      {/* Message body */}
      <div
        className={cn(
          'flex-1 flex flex-col gap-2',
          isUser ? 'items-end' : '',
        )}
      >
        {/* Bubble / prose */}
        <MessageBubble
          role={message.role}
          content={message.content}
          streaming={message.streaming}
        />

        {/* Tool steps */}
        {isAssistant && toolCalls && toolCalls.length > 0 && (
          <ToolCallGroup toolCalls={toolCalls} />
        )}

        {/* Tool approval card */}
        {message.toolApproval && onApprove && onReject && (
          <ToolApprovalCard
            toolName={message.toolApproval.toolName}
            onApprove={() => onApprove(message.toolApproval!.approvalId)}
            onDecline={() => onReject(message.toolApproval!.approvalId)}
          />
        )}

        {/* Suggested prompts — last assistant message, not streaming, has suggestions */}
        {isAssistant && isLast && suggestions.length > 0 && !message.streaming && onSuggestionClick && (
          <SuggestedPrompts suggestions={suggestions} onSelect={onSuggestionClick} />
        )}

        {/* Hover-revealed message actions */}
        {isAssistant && !message.streaming && (
          <MessageActions content={message.content} />
        )}
      </div>
    </div>
  )
}
