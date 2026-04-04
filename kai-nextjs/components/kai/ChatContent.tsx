'use client'

/**
 * KAI Client — ChatContent
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useKaiChat } from '@/lib/kai-context'
import type { KaiMessage } from '@/lib/kai-context'
import MessageBubble, { stripNextActions } from './MessageBubble'
import MessageActions from './MessageActions'
import ThinkingIndicator from './ThinkingIndicator'
import NextActionButtons from './NextActionButtons'
import ToolApprovalCard from './ToolApprovalCard'

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Returns true when the last assistant message is still streaming with no
 * content yet — i.e., KAI is "thinking" before first token.
 */
function isAgentThinking(messages: KaiMessage[], isStreaming: boolean): boolean {
  if (!isStreaming) return false
  const last = messages[messages.length - 1]
  return last?.role === 'assistant' && !last.content
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ChatContent() {
  const { messages, isStreaming, toolCalls, handleApproval, sendMessage } = useKaiChat()

  const thinking = isAgentThinking(messages, isStreaming)

  return (
    <>
      {messages.map((message, index, arr) => {
        const isLast = index === arr.length - 1
        const isAssistant = message.role === 'assistant'
        const showActions = isAssistant && !message.streaming

        // Tool calls are passed to MessageBubble for inline rendering
        const messageToolCalls = isLast && isAssistant ? toolCalls : []

        const { suggestions } = stripNextActions(message.content)
        const showNextActions = isAssistant && isLast && !message.streaming && suggestions.length > 0

        return (
          <div key={message.id} className="group">
            {/* Tool approval card (above message — modal-like prompt) */}
            {message.toolApproval && (
              <div className="px-4 py-2">
                <ToolApprovalCard
                  toolName={message.toolApproval.toolName}
                  onApprove={() => handleApproval(true, message.toolApproval!.approvalId)}
                  onDecline={() => handleApproval(false, message.toolApproval!.approvalId)}
                />
              </div>
            )}

            {/* Message bubble (tool calls rendered inline via markers) */}
            {message.content && (
              <div className="px-4 py-2">
                <MessageBubble
                  role={message.role}
                  content={message.content}
                  streaming={message.streaming}
                  toolCalls={messageToolCalls}
                />
              </div>
            )}

            {/* Actions + next suggestions below last assistant message */}
            {showActions && (
              <div className="px-4">
                <MessageActions content={message.content} />
              </div>
            )}

            {showNextActions && (
              <div className="px-4 pb-2">
                <NextActionButtons
                  suggestions={suggestions}
                  onSelect={(text: string) => void sendMessage(text)}
                  disabled={isStreaming}
                />
              </div>
            )}
          </div>
        )
      })}

      {/* Thinking indicator — streaming with no content yet */}
      {thinking && (
        <div className="px-4">
          <ThinkingIndicator />
        </div>
      )}
    </>
  )
}
