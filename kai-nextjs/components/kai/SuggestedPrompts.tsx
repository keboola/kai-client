'use client'

/**
 * KAI Client — SuggestedPrompts
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { cn } from '@/lib/utils'

// ─── Legacy shim — used by ChatMessage.tsx ────────────────────────────────────
// New code should use NextActionButtons instead.

interface SuggestedPromptsProps {
  suggestions: string[]
  onSelect: (text: string) => void
  disabled?: boolean
}

export default function SuggestedPrompts({
  suggestions,
  onSelect,
  disabled = false,
}: SuggestedPromptsProps) {
  if (suggestions.length === 0) return null

  return (
    <div className="mt-4 flex flex-col gap-2 pb-2">
      <div className="border-t border-border mx-2" />
      <div className="px-2 text-xs uppercase text-gray-400 tracking-wide">
        What&apos;s next?
      </div>
      <div className="flex flex-col gap-1">
        {suggestions.map((action, index) => (
          <button
            key={`${action}-${index}`}
            type="button"
            onClick={() => !disabled && onSelect(action)}
            disabled={disabled}
            className={cn(
              'text-left px-3 py-2 rounded-lg border border-border',
              'text-xs text-brand-secondary bg-white',
              'hover:border-brand-primary/40 hover:bg-brand-primary/5 hover:text-brand-primary',
              'transition-all duration-150',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          >
            {action}
          </button>
        ))}
      </div>
    </div>
  )
}
