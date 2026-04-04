'use client'

/**
 * KAI Client — ToolApprovalCard
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ToolApprovalCardProps {
  toolName?: string
  onApprove: () => void
  onDecline: () => void
}

export default function ToolApprovalCard({ toolName, onApprove, onDecline }: ToolApprovalCardProps) {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/50 overflow-hidden">
      <header className="px-4 py-3 flex items-center gap-2 bg-amber-50 border-b border-amber-200">
        <AlertTriangle size={16} className="text-amber-600" />
        <span className="text-sm font-semibold text-amber-900">Action Required</span>
      </header>
      <div className="px-4 py-3">
        <p className="text-sm text-brand-secondary mb-3">
          KAI wants to use:{' '}
          <code className="bg-amber-100 px-1.5 py-0.5 rounded text-xs font-mono text-amber-900">
            {toolName ?? 'unknown'}
          </code>
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={onApprove}
            className={cn(
              'bg-positive text-white px-3 py-1.5 rounded-lg text-xs font-semibold',
              'hover:opacity-90 transition-opacity',
            )}
          >
            Approve
          </button>
          <button
            onClick={onDecline}
            className={cn(
              'bg-white border border-border text-brand-secondary px-3 py-1.5 rounded-lg text-xs font-semibold',
              'hover:bg-gray-50 transition-colors',
            )}
          >
            Decline
          </button>
        </div>
      </div>
    </div>
  )
}
