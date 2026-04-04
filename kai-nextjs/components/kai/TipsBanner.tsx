'use client'

/**
 * KAI Client — TipsBanner
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useRef, useState, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Sparkles } from 'lucide-react'

// CUSTOMIZE: Replace these tips with domain-specific hints relevant to your app
const TIPS = [
  'KAI can query your data tables directly — ask about specific columns or metrics.',
  "Try asking for comparisons: 'How does X compare to Y?'",
  'You can ask KAI to create charts or tables from your data.',
  'Ask follow-up questions to drill deeper into any result.',
]

interface TipsBannerProps {
  isStreaming: boolean
}

export default function TipsBanner({ isStreaming }: TipsBannerProps) {
  const wasStreamingRef = useRef(false)
  const [tip, setTip] = useState(() => TIPS[Math.floor(Math.random() * TIPS.length)])

  useEffect(() => {
    // Shuffle tip only when a new streaming session starts
    if (isStreaming && !wasStreamingRef.current) {
      const next = TIPS[Math.floor(Math.random() * TIPS.length)]
      setTip(next)
    }
    wasStreamingRef.current = isStreaming
  }, [isStreaming])

  return (
    <AnimatePresence>
      {isStreaming && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.3 }}
          className="overflow-hidden"
        >
          <div className="px-4 py-2 bg-brand-primary/5 border-b border-brand-primary/10">
            <div className="flex items-center gap-2 text-xs text-brand-primary/70">
              <Sparkles size={12} />
              <span>{tip}</span>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
