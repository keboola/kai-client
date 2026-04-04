'use client'

/**
 * KAI Client -- SortableFieldChip
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, X } from 'lucide-react'
import type { WellField } from './DraggableField'

interface Props {
  field: WellField
  wellName: string
  onRemove: () => void
}

export default function SortableFieldChip({ field, wellName, onRemove }: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: `well::${wellName}::${field.column}`,
    data: { field, origin: wellName },
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    padding: '4px 6px 4px 4px',
    borderRadius: 5,
    fontSize: 11,
    fontWeight: 600,
    background: '#eff6ff',
    color: '#097cf7',
    border: '1px solid #bfdbfe',
    cursor: 'grab',
    userSelect: 'none' as const,
  }

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <GripVertical size={11} style={{ opacity: 0.4, flexShrink: 0 }} />
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{field.label}</span>
      <button
        onClick={(e) => { e.stopPropagation(); onRemove() }}
        onPointerDown={(e) => e.stopPropagation()}
        style={{ flexShrink: 0, cursor: 'pointer', color: '#64748b', padding: 1, display: 'flex', lineHeight: 0 }}
      >
        <X size={11} />
      </button>
    </div>
  )
}
