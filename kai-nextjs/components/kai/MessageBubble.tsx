'use client'

/**
 * KAI Client — MessageBubble
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useState, useRef, useCallback } from 'react'
import Link from 'next/link'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Copy, Check, Loader2, CheckCircle2, XCircle, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { TOOL_CALL_MARKER_RE, useKaiChat } from '@/lib/kai-context'
import type { ToolCallState } from '@/lib/kai-context'
import KaiTableChart from './KaiTableChart'

// ─── Utility: strip next_actions / suggestions blocks ────────────────────────

export function stripNextActions(text: string): { cleanContent: string; suggestions: string[] } {
  const suggestions: string[] = []
  const cleanContent = text
    .replace(
      /```(?:next_actions|suggestions?|follow[-.]?up)?\s*\n([\s\S]*?)```/g,
      (_match, block: string) => {
        const lines = block
          .split('\n')
          .map((l: string) => l.replace(/^[-*•]\s*/, '').trim())
          .filter(Boolean)
        suggestions.push(...lines)
        return ''
      },
    )
    .trim()
  return { cleanContent, suggestions }
}

// ─── Content splitting: interleave text + tool call chips ────────────────────

type ContentPart = { type: 'text'; content: string } | { type: 'tool-call'; toolCallId: string }

function splitContentIntoParts(content: string): ContentPart[] {
  const parts: ContentPart[] = []
  let lastIndex = 0
  const re = new RegExp(TOOL_CALL_MARKER_RE.source, 'g')
  let match: RegExpExecArray | null
  while ((match = re.exec(content)) !== null) {
    const text = content.slice(lastIndex, match.index)
    if (text.trim()) parts.push({ type: 'text', content: text })
    parts.push({ type: 'tool-call', toolCallId: match[1] })
    lastIndex = match.index + match[0].length
  }
  const remaining = content.slice(lastIndex)
  if (remaining.trim()) parts.push({ type: 'text', content: remaining })
  return parts
}

// ─── Tool call arg formatting helpers ────────────────────────────────────────

// CUSTOMIZE: Add or remove entries to match the tool argument names used by your KAI agent
const ARG_LABELS: Record<string, string> = {
  patterns: 'Patterns',
  item_types: 'Types',
  justification: 'Reason',
  table_id: 'Table',
  query: 'Query',
  sql: 'SQL',
  limit: 'Limit',
  bucket_id: 'Bucket',
  component_id: 'Component',
  config_id: 'Config',
  config_name: 'Config',
  name: 'Name',
  description: 'Description',
  flow_id: 'Flow',
  columns: 'Columns',
  where_column: 'Filter Column',
  where_values: 'Filter Values',
  order_by: 'Order By',
}

// CUSTOMIZE: Map your app's short table names to full Keboola Storage table IDs
/** Known table short names → full Keboola table IDs */
const TABLE_ID_MAP: Record<string, string> = {}

// CUSTOMIZE: Map your app's short bucket names to full Keboola Storage bucket IDs
/** Known bucket short names → full Keboola bucket IDs */
const BUCKET_ID_MAP: Record<string, string> = {}

/** Check if a string is a full Keboola table ID */
function isFullTableId(v: string): boolean {
  return /^(in|out)\.c-[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+$/.test(v)
}

/** Check if a string is a full Keboola bucket ID */
function isFullBucketId(v: string): boolean {
  return /^(in|out)\.c-[a-zA-Z0-9_-]+$/.test(v)
}

/** Resolve a value to a full Keboola table ID if possible */
function resolveTableId(v: string): string | null {
  if (isFullTableId(v)) return v
  const lower = v.toLowerCase().replace(/[- ]/g, '_')
  if (TABLE_ID_MAP[lower]) return TABLE_ID_MAP[lower]
  // Check if any table ID ends with this value
  for (const [short, full] of Object.entries(TABLE_ID_MAP)) {
    if (short === lower || full.endsWith(`.${lower}`)) return full
  }
  return null
}

/** Resolve a value to a full Keboola bucket ID if possible */
function resolveBucketId(v: string): string | null {
  if (isFullBucketId(v)) return v
  const lower = v.toLowerCase().replace(/[- ]/g, '_')
  if (BUCKET_ID_MAP[lower]) return BUCKET_ID_MAP[lower]
  return null
}

/** Build a Keboola Storage URL for a table */
function keboolaTableUrl(tableId: string, connUrl: string, projId: string): string {
  return `${connUrl}/admin/projects/${projId}/storage/tables/${encodeURIComponent(tableId)}`
}

/** Build a Keboola Storage URL for a bucket */
function keboolaBucketUrl(bucketId: string, connUrl: string, projId: string): string {
  return `${connUrl}/admin/projects/${projId}/storage/buckets/${encodeURIComponent(bucketId)}`
}

/** Render a single string value, auto-linking any Keboola references */
function ArgValueSpan({ value, connectionUrl, projectId }: { value: string; connectionUrl: string; projectId: string }) {
  const canLink = Boolean(connectionUrl && projectId)

  // Check if the whole value is a table reference
  const tableId = canLink ? resolveTableId(value) : null
  if (tableId) {
    return (
      <a href={keboolaTableUrl(tableId, connectionUrl, projectId)} target="_blank" rel="noopener noreferrer"
        className="text-brand-primary underline hover:text-brand-secondary">
        {value}
      </a>
    )
  }

  // Check if it's a bucket reference
  const bucketId = canLink ? resolveBucketId(value) : null
  if (bucketId) {
    return (
      <a href={keboolaBucketUrl(bucketId, connectionUrl, projectId)} target="_blank" rel="noopener noreferrer"
        className="text-brand-primary underline hover:text-brand-secondary">
        {value}
      </a>
    )
  }

  // Plain text (truncate if long)
  const display = value.length > 120 ? value.slice(0, 120) + '...' : value
  return <span className="text-gray-600">{display}</span>
}

function ToolArgRow({
  label,
  value,
  connectionUrl,
  projectId,
}: {
  label: string
  value: unknown
  connectionUrl: string
  projectId: string
}) {
  return (
    <div className="flex gap-2 leading-relaxed">
      <span className="text-gray-400 shrink-0 w-20 text-right">{label}</span>
      <span className="break-all">
        {Array.isArray(value) ? (
          value.map((item, i) => (
            <span key={i}>
              {i > 0 && <span className="text-gray-300">, </span>}
              <ArgValueSpan value={String(item)} connectionUrl={connectionUrl} projectId={projectId} />
            </span>
          ))
        ) : typeof value === 'string' ? (
          <ArgValueSpan value={value} connectionUrl={connectionUrl} projectId={projectId} />
        ) : typeof value === 'boolean' ? (
          <span className="text-gray-600">{value ? 'Yes' : 'No'}</span>
        ) : (
          <span className="text-gray-600">{String(value)}</span>
        )}
      </span>
    </div>
  )
}

function InlineToolCallChip({ toolCallId, toolCalls }: { toolCallId: string; toolCalls: ToolCallState[] }) {
  const [expanded, setExpanded] = useState(false)
  const { connectionUrl, projectId } = useKaiChat()
  const tc = toolCalls.find(t => t.toolCallId === toolCallId)
  const state = tc?.state ?? 'done'
  const name = tc?.toolName ?? 'Processing'
  const args = tc?.toolArgs

  // Friendly label for the tool name
  const label = name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())

  const statusLabel = state === 'processing' ? 'Running' : state === 'done' ? 'Completed' : 'Failed'

  // Parse args JSON
  let parsedArgs: Record<string, unknown> | null = null
  if (args) {
    try { parsedArgs = JSON.parse(args) } catch { /* not valid JSON */ }
  }

  return (
    <div className="my-1.5 rounded-lg border border-border/60 bg-surface/50 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className={cn(
          'flex w-full items-center gap-2 px-3 py-1.5 text-xs transition-colors',
          'hover:bg-surface',
        )}
      >
        {state === 'processing' ? (
          <Loader2 size={12} className="text-brand-primary animate-spin shrink-0" />
        ) : state === 'done' ? (
          <CheckCircle2 size={12} className="text-positive shrink-0" />
        ) : (
          <XCircle size={12} className="text-negative shrink-0" />
        )}
        <span className={cn(
          'font-medium',
          state === 'processing' ? 'text-brand-primary' : state === 'done' ? 'text-positive' : 'text-negative',
        )}>
          {statusLabel}
        </span>
        <span className="text-gray-500">{label}</span>
        <ChevronDown
          size={10}
          className={cn(
            'ml-auto text-gray-400 transition-transform duration-200 shrink-0',
            expanded && 'rotate-180',
          )}
        />
      </button>
      {expanded && (
        <div className="px-3 py-2 border-t border-border/40 text-xs space-y-1.5">
          <ToolArgRow label="Tool" value={name} connectionUrl={connectionUrl} projectId={projectId} />
          {parsedArgs ? (
            Object.entries(parsedArgs).map(([key, value]) => (
              <ToolArgRow
                key={key}
                label={ARG_LABELS[key] ?? key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                value={value}
                connectionUrl={connectionUrl}
                projectId={projectId}
              />
            ))
          ) : args ? (
            <ToolArgRow label="Args" value={args} connectionUrl={connectionUrl} projectId={projectId} />
          ) : null}
        </div>
      )}
    </div>
  )
}

// ─── Inline code-block copy button ───────────────────────────────────────────

function CodeBlockCopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard not available
    }
  }

  return (
    <button
      onClick={handleCopy}
      className={cn(
        'opacity-0 group-hover:opacity-100 absolute top-2 right-2',
        'p-1.5 rounded-md text-gray-400 bg-white/80 hover:text-brand-secondary hover:bg-white',
        'transition-all duration-150',
      )}
      aria-label="Copy code"
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
    </button>
  )
}

// ─── Markdown component overrides ─────────────────────────────────────────────

const markdownComponents: React.ComponentProps<typeof ReactMarkdown>['components'] = {
  code({ className, children, ...props }) {
    // react-markdown v9: inline detection via absence of className (language-*)
    const isBlock = Boolean(className)
    if (!isBlock) {
      return (
        <code
          className="bg-surface px-1.5 py-0.5 rounded text-xs font-mono"
          {...props}
        >
          {children}
        </code>
      )
    }
    // Block code — just render children; <pre> wrapper handles the container
    return <>{children}</>
  },

  pre({ children }) {
    // Extract raw text from the nested code element for copy button
    const extractText = (node: React.ReactNode): string => {
      if (typeof node === 'string') return node
      if (Array.isArray(node)) return node.map(extractText).join('')
      if (node && typeof node === 'object' && 'props' in (node as any)) {
        return extractText((node as any).props?.children)
      }
      return ''
    }
    const codeText = extractText(children)

    return (
      <div className="relative group">
        <pre className="bg-surface rounded-xl p-4 overflow-x-auto text-xs font-mono max-h-[50svh] overflow-y-auto">
          {children}
        </pre>
        <CodeBlockCopyButton code={codeText} />
      </div>
    )
  },

  p({ children }) {
    return <p className="whitespace-pre-line">{children}</p>
  },

  a({ href, children }) {
    const isInternal = href?.startsWith('/')
    if (isInternal && href) {
      return (
        <Link href={href} className="text-brand-primary underline hover:text-brand-secondary">
          {children}
        </Link>
      )
    }
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-brand-primary underline hover:text-brand-secondary"
      >
        {children}
      </a>
    )
  },

  // Tables are intercepted at the top level and rendered as KaiTableChart.
  // We collect headers and rows from the DOM structure.
  table({ children }) {
    return <KaiTableCollector>{children}</KaiTableCollector>
  },
}

/**
 * Collects thead/tbody children from markdown table and renders KaiTableChart.
 * Falls back to plain HTML table if parsing fails.
 */
function KaiTableCollector({ children }: { children: React.ReactNode }) {
  const headers = useRef<string[]>([])
  const rows = useRef<string[][]>([])
  const collected = useRef(false)

  // Extract text from React nodes
  const extractText = useCallback((node: React.ReactNode): string => {
    if (typeof node === 'string') return node
    if (typeof node === 'number') return String(node)
    if (Array.isArray(node)) return node.map(extractText).join('')
    if (node && typeof node === 'object' && 'props' in (node as any)) {
      return extractText((node as any).props?.children)
    }
    return ''
  }, [])

  // Walk children to find thead > tr > th and tbody > tr > td
  const processChildren = useCallback((nodes: React.ReactNode) => {
    const arr = Array.isArray(nodes) ? nodes : [nodes]
    for (const child of arr) {
      if (!child || typeof child !== 'object' || !('props' in (child as any))) continue
      const el = child as any
      const type = el.type
      if (type === 'thead' || type === 'tbody') {
        processChildren(el.props?.children)
      } else if (type === 'tr') {
        const cells: string[] = []
        const trChildren = Array.isArray(el.props?.children) ? el.props.children : [el.props?.children]
        let isTh = false
        for (const cell of trChildren) {
          if (!cell || typeof cell !== 'object') continue
          const cellEl = cell as any
          if (cellEl.type === 'th') isTh = true
          cells.push(extractText(cellEl.props?.children))
        }
        if (isTh) {
          headers.current = cells
        } else {
          rows.current.push(cells)
        }
      }
    }
  }, [extractText])

  if (!collected.current) {
    headers.current = []
    rows.current = []
    processChildren(children)
    collected.current = true
  }

  if (headers.current.length > 0 && rows.current.length > 0) {
    return <KaiTableChart headers={headers.current} rows={rows.current} />
  }

  // Fallback: plain table
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse">{children}</table>
    </div>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  toolCalls?: ToolCallState[]
}

export default function MessageBubble({ role, content, streaming = false, toolCalls = [] }: MessageBubbleProps) {
  const { cleanContent } = stripNextActions(content)

  if (role === 'user') {
    return (
      <div className="max-w-[80%] ml-auto">
        <div className="bg-brand-secondary text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
          <p className="whitespace-pre-wrap">{content}</p>
        </div>
      </div>
    )
  }

  const parts = splitContentIntoParts(cleanContent)

  return (
    <div className="max-w-[90%] text-sm">
      <div className="kai-prose prose prose-sm max-w-none">
        {parts.map((part, i) =>
          part.type === 'text' ? (
            <ReactMarkdown key={i} remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {part.content}
            </ReactMarkdown>
          ) : (
            <InlineToolCallChip key={part.toolCallId} toolCallId={part.toolCallId} toolCalls={toolCalls} />
          )
        )}
      </div>
      {streaming && content && (
        <span className="inline-block w-1.5 h-4 bg-brand-primary ml-0.5 animate-pulse rounded-sm" />
      )}
    </div>
  )
}
