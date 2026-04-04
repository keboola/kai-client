'use client'

/**
 * KAI Client -- FieldWell
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import SortableFieldChip from './SortableFieldChip'
import type { WellField } from './DraggableField'

interface Props {
  wellName: string
  label: string
  items: WellField[]
  onRemove: (column: string) => void
  acceptsRole: 'dimension' | 'measure'
  placeholder?: string
}

export default function FieldWell({ wellName, label, items, onRemove, acceptsRole, placeholder }: Props) {
  const { setNodeRef, isOver } = useDroppable({
    id: `well::${wellName}`,
    data: { accepts: acceptsRole },
  })

  const sortableIds = items.map((f) => `well::${wellName}::${f.column}`)

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
        {label}
      </div>
      <div
        ref={setNodeRef}
        style={{
          minHeight: 36,
          padding: items.length > 0 ? '4px 4px' : '0 8px',
          borderRadius: 7,
          border: `1.5px dashed ${isOver ? '#097cf7' : '#d1d5db'}`,
          background: isOver ? '#eff6ff' : '#fafbfc',
          display: 'flex',
          flexDirection: 'column',
          gap: 3,
          transition: 'all 120ms',
        }}
      >
        <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
          {items.map((f) => (
            <SortableFieldChip key={f.column} field={f} wellName={wellName} onRemove={() => onRemove(f.column)} />
          ))}
        </SortableContext>
        {items.length === 0 && (
          <div style={{ padding: '8px 0', textAlign: 'center', fontSize: 11, color: '#94a3b8', fontStyle: 'italic' }}>
            {placeholder ?? `Drop ${acceptsRole}s here`}
          </div>
        )}
      </div>
    </div>
  )
}
