'use client'

/**
 * KAI Client — ChatButton
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { Sparkles } from 'lucide-react'
import { useKaiChat } from '@/lib/kai-context'
import { cn } from '@/lib/utils'

/**
 * KAI toggle button — placed in the app Header.
 * Matches Keboola ChatButton.tsx (hasSidebarNavigation variant).
 *
 * Pressed: opens the KAI Sheet
 * Icon: sparkles (Font Awesome fa-sparkles → lucide Sparkles)
 */
export function ChatButton() {
  const { isOpen, toggleChat } = useKaiChat()

  return (
    <button
      onClick={toggleChat}
      className={cn(
        'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-150',
        isOpen
          ? 'bg-brand-primary/10 text-brand-primary'
          : 'text-gray-500 hover:bg-gray-100 hover:text-brand-secondary',
      )}
      title="Open Kai by pressing A"
    >
      <Sparkles size={16} className={cn(isOpen && 'text-brand-primary')} />
      <span>Kai</span>
    </button>
  )
}
