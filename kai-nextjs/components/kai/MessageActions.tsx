'use client'

/**
 * KAI Client — MessageActions
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useState } from 'react'
import { Copy, Check, ThumbsUp, ThumbsDown } from 'lucide-react'
import { cn } from '@/lib/utils'

interface MessageActionsProps {
  content: string
}

export default function MessageActions({ content }: MessageActionsProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard not available
    }
  }

  const btnClass = cn(
    'p-1 rounded-md text-gray-400',
    'hover:text-brand-secondary hover:bg-gray-100',
    'transition-colors',
  )

  return (
    <div className="flex items-center gap-1 mt-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
      <button onClick={handleCopy} className={btnClass} aria-label="Copy message">
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
      <button className={btnClass} aria-label="Thumbs up">
        <ThumbsUp size={14} />
      </button>
      <button className={btnClass} aria-label="Thumbs down">
        <ThumbsDown size={14} />
      </button>
    </div>
  )
}
