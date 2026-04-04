'use client'

/**
 * KAI Client — Chat
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useEffect } from 'react'
import { useKaiChat } from '@/lib/kai-context'
import { SheetChatContent } from './SheetChatContent'

/**
 * Chat Sheet — right-side drawer, matching Keboola platform Chat.tsx.
 *
 * Two layout modes:
 * - sidebar: fixed-width panel on the right (420px)
 * - fullscreen: takes full viewport width, body scroll locked
 */
export function Chat() {
  const { isOpen, layoutMode, closeChat } = useKaiChat()
  const isFullscreen = layoutMode === 'fullscreen'

  // Lock body scroll in fullscreen mode
  useEffect(() => {
    if (!isFullscreen || !isOpen) return
    document.body.style.overflow = 'hidden'
    document.documentElement.style.setProperty('scrollbar-gutter', 'stable')
    return () => {
      document.body.style.overflow = ''
      document.documentElement.style.removeProperty('scrollbar-gutter')
    }
  }, [isFullscreen, isOpen])

  if (!isOpen) return null

  return (
    <>
      {/* Overlay (fullscreen only) */}
      {isFullscreen && (
        <div
          className="kai-sheet-overlay"
          data-state="open"
          onClick={closeChat}
        />
      )}

      {/* Sheet panel */}
      <div
        className="kai-sheet flex flex-col"
        data-state="open"
        data-layout={layoutMode}
      >
        <SheetChatContent />
      </div>
    </>
  )
}
