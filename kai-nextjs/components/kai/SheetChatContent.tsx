'use client'

/**
 * KAI Client — SheetChatContent
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useState } from 'react'
import { useKaiChat } from '@/lib/kai-context'
import { cn } from '@/lib/utils'
import ChatHeader from './ChatHeader'
import ChatMessageList from './ChatMessageList'
import ChatWelcome from './ChatWelcome'
import ChatInput from './ChatInput'
import TipsBanner from './TipsBanner'
import ChatHistoryPanel from './ChatHistoryPanel'

// ─── Component ────────────────────────────────────────────────────────────────

export function SheetChatContent() {
  const {
    messages,
    isStreaming,
    layoutMode,
    sendMessage,
    abortStreaming,
    startNewConversation,
  } = useKaiChat()

  const [prompt, setPrompt] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)

  const isFullscreen = layoutMode === 'fullscreen'
  const shouldShowWelcome = messages.length === 0
  const isProcessing = isStreaming

  // Status for ChatInput
  const status = isProcessing ? 'streaming' : 'ready'

  const handleSend = (text: string) => {
    void sendMessage(text)
    setPrompt('')
  }

  return (
    <div className={cn(isFullscreen ? 'flex h-full flex-col' : 'contents')}>
      {/* Sheet.Header → h-12, border-b */}
      <div className="h-12 flex items-center border-b border-neutral-100">
        <ChatHeader isFullscreen={isFullscreen} />
      </div>

      {/* Main layout */}
      <div className={cn(isFullscreen ? 'flex flex-1 overflow-hidden' : 'contents')}>
        {/* Left sidebar in fullscreen */}
        {isFullscreen && (
          <ChatHistoryPanel
            isOpen={historyOpen}
            onClose={() => setHistoryOpen(false)}
          />
        )}

        {/* Center content */}
        <div className={cn(isFullscreen ? 'flex flex-1 flex-col overflow-hidden' : 'contents')}>
          {shouldShowWelcome ? (
            /* Welcome screen */
            <div className="flex-1 flex items-center justify-center overflow-y-auto p-6">
              <ChatWelcome
                onSend={handleSend}
                prompt={prompt}
                onPromptChange={setPrompt}
              />
            </div>
          ) : (
            <>
              {/* Sheet.Body → flex-1, overflow-hidden */}
              <div className="flex-1 overflow-hidden px-0">
                <ChatMessageList
                  isFullscreen={isFullscreen}
                  isProcessing={isProcessing}
                />
              </div>

              {/* Sheet.Footer */}
              <div className={cn('pt-2', isFullscreen && 'mx-auto w-full max-w-[828px]')}>
                <TipsBanner isStreaming={isStreaming} />
                <div className="px-3 pb-3">
                  <ChatInput
                    value={prompt}
                    onValueChange={setPrompt}
                    onSend={handleSend}
                    onStop={abortStreaming}
                    status={status}
                    disabled={false}
                    placeholder="Ask KAI anything about your data..."
                  />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
