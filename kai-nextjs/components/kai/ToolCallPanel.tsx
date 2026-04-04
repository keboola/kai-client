'use client'

/**
 * KAI Client — ToolCallPanel
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useState } from 'react'
import { Loader2, CheckCircle2, XCircle, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ToolCallState } from '@/lib/kai-context'

// ─── Status variant mapping ───────────────────────────────────────────────────

type StatusVariant = 'processing' | 'warning' | 'success' | 'error'

function getVariant(state: ToolCallState['state'], needsConfirmation?: boolean): StatusVariant {
  if (needsConfirmation) return 'warning'
  if (state === 'processing') return 'processing'
  if (state === 'done') return 'success'
  return 'error'
}

const headerVariantClasses: Record<StatusVariant, string> = {
  processing: 'bg-blue-600',       // secondary-600
  warning:    'bg-amber-500',       // warning-550
  success:    'bg-green-700',       // primary-700 (green)
  error:      'bg-red-500',         // error-500
}

function StatusIcon({ variant, spin }: { variant: StatusVariant; spin?: boolean }) {
  if (variant === 'processing') {
    return <Loader2 size={14} className={cn('text-white', spin && 'animate-spin')} />
  }
  if (variant === 'warning') {
    return <AlertTriangle size={14} className="text-white" />
  }
  if (variant === 'error') {
    return <XCircle size={14} className="text-white" />
  }
  return <CheckCircle2 size={14} className="text-white" />
}

function getStatusText(state: ToolCallState['state'], toolName?: string): string {
  const name = toolName ?? 'Tool'
  if (state === 'processing') return `Running ${name}…`
  if (state === 'done') return `${name} completed`
  return `${name} failed`
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface ToolCallPanelProps {
  toolCall: ToolCallState
  needsConfirmation?: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ToolCallPanel({ toolCall, needsConfirmation = false }: ToolCallPanelProps) {
  const { state, toolName } = toolCall
  const variant = getVariant(state, needsConfirmation)

  // Only allow collapse once done or errored
  const isCollapsible = variant === 'success' || variant === 'error'
  const [isCollapsed, setIsCollapsed] = useState(true)

  const statusText = getStatusText(state, toolName)
  const isSpinning = variant === 'processing' || variant === 'warning'

  return (
    <div
      data-testid="tool-call-panel"
      className="flex flex-col overflow-hidden rounded-[10px] border border-neutral-200 bg-white text-xs"
    >
      {/* Header */}
      <div
        role={isCollapsible ? 'button' : undefined}
        tabIndex={isCollapsible ? 0 : undefined}
        aria-expanded={isCollapsible ? !isCollapsed : undefined}
        onClick={isCollapsible ? () => setIsCollapsed(p => !p) : undefined}
        onKeyDown={
          isCollapsible
            ? e => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  setIsCollapsed(p => !p)
                }
              }
            : undefined
        }
        className={cn(
          'flex items-center justify-between gap-2 px-2 py-1',
          headerVariantClasses[variant],
          isCollapsible && 'cursor-pointer',
        )}
      >
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <StatusIcon variant={variant} spin={isSpinning} />
          <span
            data-testid="tool-status-text"
            className="truncate pr-0.5 text-xs font-medium italic text-white"
          >
            {statusText}
          </span>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {needsConfirmation && (
            <div className="flex items-center gap-1">
              <span className="text-xs font-medium text-white">Confirmation required</span>
              <AlertTriangle size={12} className="text-white" />
            </div>
          )}
          {isCollapsible && (
            isCollapsed
              ? <ChevronDown size={12} className="text-white shrink-0" />
              : <ChevronUp size={12} className="text-white shrink-0" />
          )}
        </div>
      </div>

      {/* Collapsible body — only shown when expanded */}
      {isCollapsible && (
        <div
          className={cn(
            'grid transition-[grid-template-rows] duration-300 ease-out',
            isCollapsed ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]',
          )}
        >
          <div className="overflow-hidden">
            <div className="px-3 py-2 text-xs text-gray-500 font-mono">
              {toolName ?? toolCall.toolCallId}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
