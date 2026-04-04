'use client'

/**
 * KAI Client — InlineTaskGroup
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useState } from 'react'
import { Loader2, CheckCircle2, XCircle, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ToolCallState } from '@/lib/kai-context'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getHeaderLabel({
  toolCalls,
  hasProcessing,
  isExpanded,
}: {
  toolCalls: ToolCallState[]
  hasProcessing: boolean
  isExpanded: boolean
}): string {
  const count = toolCalls.length
  const stepLabel = count === 1 ? 'step' : 'steps'

  if (hasProcessing) {
    return `Running ${count} ${stepLabel}…`
  }
  if (isExpanded) {
    return `${count} ${stepLabel} completed`
  }
  return `${count} ${stepLabel}`
}

// ─── Sub-component: per-task row ──────────────────────────────────────────────

function TaskRow({ toolCall }: { toolCall: ToolCallState }) {
  const { state, toolName, toolCallId } = toolCall

  return (
    <div className="flex items-center gap-2 text-xs text-gray-500">
      {state === 'processing' ? (
        <Loader2 size={12} className="text-brand-primary animate-spin shrink-0" />
      ) : state === 'done' ? (
        <CheckCircle2 size={12} className="text-positive shrink-0" />
      ) : (
        <XCircle size={12} className="text-negative shrink-0" />
      )}
      <span
        className={cn(
          'font-mono text-xs italic',
          state === 'error' ? 'text-negative' : 'text-gray-600',
        )}
      >
        {toolName ?? toolCallId}
      </span>
    </div>
  )
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface InlineTaskGroupProps {
  toolCalls: ToolCallState[]
  isProcessing: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function InlineTaskGroup({ toolCalls, isProcessing }: InlineTaskGroupProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (!toolCalls.length) return null

  const hasProcessing = isProcessing || toolCalls.some(tc => tc.state === 'processing')
  const hasAllErrors = !hasProcessing && toolCalls.every(tc => tc.state === 'error')

  const headerText = getHeaderLabel({ toolCalls, hasProcessing, isExpanded })

  return (
    <div data-testid="inline-task-group" className="flex flex-col gap-4">
      {/* Toggle button */}
      <button
        type="button"
        aria-expanded={isExpanded}
        onClick={() => setIsExpanded(v => !v)}
        className={cn(
          'flex w-fit items-center gap-3 text-left text-sm font-medium italic transition-colors',
          'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2',
          hasAllErrors
            ? 'text-red-500 focus-visible:outline-red-500 hover:text-red-600'
            : 'text-blue-600 focus-visible:outline-blue-500 hover:text-blue-700',
        )}
      >
        <div className="flex items-center gap-2">
          {hasProcessing ? (
            <Loader2 size={16} className="animate-spin" />
          ) : hasAllErrors ? (
            <XCircle size={16} />
          ) : (
            <CheckCircle2 size={16} />
          )}
          <span>{headerText}</span>
        </div>

        <ChevronDown
          size={12}
          className={cn('transition-transform duration-200', isExpanded && 'rotate-180')}
        />
      </button>

      {/* Expanded rows */}
      {isExpanded && (
        <div className="flex flex-col gap-3 pl-5 border-l-2 border-border">
          {toolCalls.map(tc => (
            <TaskRow key={tc.toolCallId} toolCall={tc} />
          ))}
        </div>
      )}
    </div>
  )
}
