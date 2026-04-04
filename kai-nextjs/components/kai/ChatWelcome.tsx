'use client'

/**
 * KAI Client — ChatWelcome
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { BarChart2, Users, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'
import ChatInput from './ChatInput'

// ─── Starter prompts ──────────────────────────────────────────────────────────

// CUSTOMIZE: Replace these starter prompts with queries relevant to your app's domain
const STARTER_PROMPTS = [
  {
    label: 'Key metrics',
    prompt: 'Show me key metrics.',
    icon: BarChart2,
  },
  {
    label: 'Trends',
    prompt: 'What trends do you see?',
    icon: Clock,
  },
  {
    label: 'Summarize data',
    prompt: 'Summarize my data.',
    icon: Users,
  },
]

// ─── Types ────────────────────────────────────────────────────────────────────

interface ChatWelcomeProps {
  onSend: (text: string) => void
  prompt?: string
  onPromptChange?: (value: string) => void
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ChatWelcome({ onSend, prompt = '', onPromptChange }: ChatWelcomeProps) {
  const handlePromptClick = (text: string) => {
    onSend(text)
  }

  return (
    <div className="flex flex-col items-center gap-10 text-center max-w-[600px] w-full">
      {/* Heading */}
      <div className="flex flex-col items-center gap-2">
        <h1 className="text-2xl font-bold text-brand-secondary">
          Welcome to Kai! 🎉
        </h1>
        <p className="text-sm text-gray-500 max-w-[420px]">
          Your AI assistant for data exploration. Ask anything about your data.
        </p>
      </div>

      {/* Input */}
      <div className="w-full">
        <ChatInput
          value={prompt}
          onValueChange={onPromptChange ?? (() => {})}
          onSend={onSend}
          onStop={() => {}}
          status="ready"
          placeholder="Ask a question about your data..."
        />
      </div>

      {/* Starter prompts */}
      <div className="flex items-center justify-center gap-3 flex-wrap">
        {STARTER_PROMPTS.map(({ label, prompt: p, icon: Icon }) => (
          <button
            key={label}
            type="button"
            onClick={() => handlePromptClick(p)}
            className={cn(
              'flex items-center gap-2 px-4 py-2.5 rounded-xl border border-border',
              'bg-white text-sm text-brand-secondary font-medium',
              'hover:border-brand-primary/40 hover:bg-brand-primary/5 hover:text-brand-primary',
              'transition-all duration-150 shadow-sm',
            )}
          >
            <Icon size={15} className="text-brand-primary shrink-0" />
            <span>{label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
