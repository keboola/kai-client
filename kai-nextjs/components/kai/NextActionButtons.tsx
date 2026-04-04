'use client'

/**
 * KAI Client — NextActionButtons
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useRouter } from 'next/navigation'
import { useKaiChat } from '@/lib/kai-context'
import { cn } from '@/lib/utils'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Strip markdown link/bold/code syntax for clean button display */
function cleanSuggestionText(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')  // [Link](/path) → Link
    .replace(/\*\*([^*]+)\*\*/g, '$1')         // **bold** → bold
    .replace(/`([^`]+)`/g, '$1')               // `code` → code
    .trim()
}

/** Extract first internal link path and its display text from markdown */
function extractInternalLink(text: string): { path: string; label: string } | null {
  const match = text.match(/\[([^\]]+)\]\((\/[^)]*)\)/)
  return match ? { path: match[2], label: match[1] } : null
}

/**
 * Render suggestion text with page names highlighted as styled spans.
 * Returns React nodes with page names visually distinct.
 */
function renderSuggestionText(text: string): React.ReactNode {
  const clean = cleanSuggestionText(text)
  // CUSTOMIZE: Replace with your app's page/section names
  const pageNames: string[] = []
  const pattern = new RegExp(`(${pageNames.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g')

  const parts = clean.split(pattern)
  return parts.map((part, i) =>
    pageNames.includes(part)
      ? <span key={i} className="font-semibold text-brand-primary">{part}</span>
      : part
  )
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface NextActionButtonsProps {
  /** Already-parsed suggestion strings (from stripNextActions) */
  suggestions: string[]
  onSelect: (text: string) => void
  disabled?: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function NextActionButtons({
  suggestions,
  onSelect,
  disabled = false,
}: NextActionButtonsProps) {
  const router = useRouter()
  const { collapse } = useKaiChat()

  if (suggestions.length === 0) return null

  const handleClick = (action: string) => {
    if (disabled) return
    const link = extractInternalLink(action)
    // Always send the cleaned message to KAI
    onSelect(cleanSuggestionText(action))
    // If there's a navigation link, also navigate and collapse
    if (link) {
      router.push(link.path)
      collapse()
    }
  }

  return (
    <div className="mt-5 flex flex-col gap-2 pb-2">
      {/* Separator */}
      <div className="border-t border-border mx-2" />

      {/* Label */}
      <div className="px-2 text-xs uppercase text-gray-400 tracking-wide">
        What&apos;s next?
      </div>

      {/* Pill chips */}
      <div className="flex flex-col gap-1">
        {suggestions.map((action, index) => {
          const link = extractInternalLink(action)
          return (
            <button
              key={`${action}-${index}`}
              type="button"
              onClick={() => handleClick(action)}
              disabled={disabled}
              className={cn(
                'text-left px-3 py-2 rounded-lg border border-border',
                'text-xs text-brand-secondary bg-white',
                'hover:border-brand-primary/40 hover:bg-brand-primary/5 hover:text-brand-primary',
                'transition-all duration-150',
                'disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-white disabled:hover:border-border disabled:hover:text-brand-secondary',
                link && 'flex items-center gap-1.5',
              )}
            >
              <span className="flex-1">{renderSuggestionText(action)}</span>
              {link && <span className="text-brand-primary/50 ml-auto shrink-0">&rarr;</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
