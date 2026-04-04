'use client'

/**
 * KAI Client — ChatMessageList
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import ChatContent from './ChatContent'

// ─── Types ────────────────────────────────────────────────────────────────────

interface ChatMessageListProps {
  isFullscreen: boolean
  isProcessing: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ChatMessageList({ isFullscreen, isProcessing }: ChatMessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const isUserScrolledUp = useRef(false)

  // Track whether the user has scrolled away from the bottom
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return

    const handleScroll = () => {
      const threshold = 80
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
      isUserScrolledUp.current = !atBottom
    }

    el.addEventListener('scroll', handleScroll, { passive: true })
    return () => el.removeEventListener('scroll', handleScroll)
  }, [])

  // Auto-scroll to bottom when new messages arrive or during streaming
  useEffect(() => {
    if (!isUserScrolledUp.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  })

  return (
    <div className="h-full flex flex-col">
      <div
        ref={scrollRef}
        className={cn(
          'flex-1 overflow-y-auto',
          isFullscreen && 'mx-auto w-full max-w-[828px]',
        )}
      >
        {/* Message content */}
        <div className="flex flex-col py-4 gap-1">
          <ChatContent />
        </div>

        {/* Scroll anchor */}
        <div ref={bottomRef} aria-hidden="true" />
      </div>
    </div>
  )
}
