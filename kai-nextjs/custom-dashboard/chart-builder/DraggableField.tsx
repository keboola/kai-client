'use client'

/**
 * KAI Client -- DraggableField
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useDraggable } from '@dnd-kit/core'
import { Calendar, Hash } from 'lucide-react'

export interface WellField {
  column: string
  label: string
  role: 'dimension' | 'measure'
}

interface Props {
  field: WellField
  isUsed: boolean
  onClick: () => void
}

export default function DraggableField({ field, isUsed, onClick }: Props) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `source::${field.column}`,
    data: { field, origin: 'source' },
  })

  const Icon = field.role === 'dimension' ? Calendar : Hash

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '5px 8px',
        borderRadius: 6,
        fontSize: 12,
        fontWeight: 500,
        cursor: 'grab',
        userSelect: 'none',
        opacity: isDragging ? 0.35 : 1,
        background: isUsed ? '#eff6ff' : '#f8fafc',
        color: isUsed ? '#097cf7' : '#002151',
        border: `1px solid ${isUsed ? '#bfdbfe' : '#e2e8f0'}`,
        transition: 'all 120ms',
      }}
    >
      <Icon size={12} style={{ flexShrink: 0, opacity: 0.6 }} />
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{field.label}</span>
      {isUsed && (
        <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#097cf7', flexShrink: 0 }} />
      )}
    </div>
  )
}
