'use client'

/**
 * KAI Client — ToolCallGroup
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useState } from 'react'
import { Wrench, ChevronDown, ChevronUp, Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ToolCall {
  toolCallId: string
  toolName?: string
  state: 'processing' | 'done' | 'error'
}

interface ToolCallGroupProps {
  toolCalls: ToolCall[]
}

function ToolStateIcon({ state }: { state: ToolCall['state'] }) {
  if (state === 'processing') {
    return <Loader2 size={12} className="text-brand-primary animate-spin" />
  }
  if (state === 'done') {
    return <CheckCircle2 size={12} className="text-positive" />
  }
  return <XCircle size={12} className="text-negative" />
}

export default function ToolCallGroup({ toolCalls }: ToolCallGroupProps) {
  const [isOpen, setIsOpen] = useState(false)

  if (!toolCalls.length) return null

  return (
    <div className="text-xs">
      <button
        onClick={() => setIsOpen(v => !v)}
        className="flex items-center gap-2 text-xs text-gray-500 hover:text-brand-secondary transition-colors"
      >
        <Wrench size={12} />
        <span>{toolCalls.length} {toolCalls.length === 1 ? 'step' : 'steps'}</span>
        {isOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {isOpen && (
        <div className="mt-1 space-y-1 pl-4 border-l-2 border-border">
          {toolCalls.map((tc) => (
            <div
              key={tc.toolCallId}
              className={cn(
                'flex items-center gap-2 text-xs',
                tc.state === 'error' ? 'text-negative' : 'text-gray-500',
              )}
            >
              <ToolStateIcon state={tc.state} />
              <span className="font-mono">{tc.toolName ?? tc.toolCallId}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
