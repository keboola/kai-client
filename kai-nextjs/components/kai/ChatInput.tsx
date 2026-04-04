'use client'

/**
 * KAI Client — ChatInput
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useRef, useEffect } from 'react'
import { Send, Square, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

// ─── Types ────────────────────────────────────────────────────────────────────

type InputStatus = 'ready' | 'submitted' | 'streaming'

interface ChatInputProps {
  value: string
  onValueChange: (value: string) => void
  onSend: (text: string) => void
  onStop: () => void
  status: InputStatus
  disabled?: boolean
  placeholder?: string
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ChatInput({
  value,
  onValueChange,
  onSend,
  onStop,
  status,
  disabled = false,
  placeholder = 'Send a message...',
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-focus on mount
  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const isReady = status === 'ready'
  const isSubmitted = status === 'submitted'
  const isStreaming = status === 'streaming'

  const canSend = isReady && value.trim().length > 0 && !disabled

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (canSend) {
        onSend(value.trim())
      }
    }
  }

  const handleActionClick = () => {
    if (isReady && canSend) {
      onSend(value.trim())
    } else if (isStreaming) {
      onStop()
    }
    // submitted: no-op (can't stop)
  }

  return (
    <div
      className={cn(
        'flex flex-col gap-2 rounded-xl border border-border bg-white',
        'shadow-sm transition-shadow duration-150',
        'focus-within:border-brand-primary/50 focus-within:shadow-md',
      )}
    >
      {/* Textarea */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={e => onValueChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled || isSubmitted}
        rows={2}
        className={cn(
          'kai-textarea w-full px-4 pt-3 pb-1',
          'text-sm text-brand-secondary placeholder:text-gray-400',
          'bg-transparent outline-none resize-none',
          'leading-relaxed',
        )}
      />

      {/* Bottom row: action button */}
      <div className="flex items-center justify-end px-3 pb-2">
        <button
          type="button"
          onClick={handleActionClick}
          disabled={isReady ? !canSend : isSubmitted}
          aria-label={
            isStreaming ? 'Stop generating' : isSubmitted ? 'Sending…' : 'Send message'
          }
          className={cn(
            'flex items-center justify-center w-8 h-8 rounded-lg',
            'transition-all duration-150',
            // Ready + can send
            canSend && isReady && 'bg-brand-primary text-white hover:bg-brand-primary/90',
            // Ready but empty
            isReady && !canSend && 'bg-gray-100 text-gray-300 cursor-not-allowed',
            // Submitted — spinner, disabled
            isSubmitted && 'bg-gray-100 text-gray-400 cursor-not-allowed',
            // Streaming — stop button
            isStreaming && 'bg-brand-primary text-white hover:bg-brand-primary/90',
          )}
        >
          {isSubmitted ? (
            <Loader2 size={16} className="animate-spin" />
          ) : isStreaming ? (
            <Square size={14} />
          ) : (
            <Send size={14} />
          )}
        </button>
      </div>
    </div>
  )
}
