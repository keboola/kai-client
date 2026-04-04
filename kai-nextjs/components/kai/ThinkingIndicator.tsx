'use client'

/**
 * KAI Client — ThinkingIndicator
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { Sparkles } from 'lucide-react'

export default function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <div className="w-7 h-7 rounded-full bg-brand-primary/10 flex items-center justify-center shrink-0">
        <Sparkles size={14} className="text-brand-primary" />
      </div>
      <div className="flex items-center gap-1.5 px-3 py-2">
        <span className="kai-dot w-2 h-2 rounded-full bg-brand-primary/40" />
        <span className="kai-dot w-2 h-2 rounded-full bg-brand-primary/40" />
        <span className="kai-dot w-2 h-2 rounded-full bg-brand-primary/40" />
      </div>
    </div>
  )
}
