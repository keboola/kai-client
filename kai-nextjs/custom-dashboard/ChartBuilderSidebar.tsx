'use client'

/**
 * KAI Client -- ChartBuilderSidebar
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 *
 * Required consumer-app files (not in kai-nextjs template):
 * - @/lib/api — useDataSchema, useQueryData hooks
 * - @/lib/constants — COLORS.brandPrimary and COLORS.chart for chart palette
 * - @/lib/chart-utils — buildOption, TYPES, ChartType
 * - @/lib/chart-config-storage — saveConfig, updateConfig, deleteConfig, useChartLibrary, getLibrary, ChartConfig, DataSource, Period
 * - @/lib/dashboard-storage — addDynamicChart
 */

import { useState, useMemo, useEffect } from 'react'
import { motion } from 'framer-motion'
import ReactECharts from 'echarts-for-react'
import { DndContext, DragOverlay, PointerSensor, KeyboardSensor, useSensor, useSensors, closestCenter } from '@dnd-kit/core'
import type { DragStartEvent, DragEndEvent, DragOverEvent } from '@dnd-kit/core'
import { sortableKeyboardCoordinates, arrayMove } from '@dnd-kit/sortable'
import { X, Loader2, Plus, Pencil, Trash2, BarChart2 } from 'lucide-react'

import { useDataSchema, useQueryData } from '@/lib/api'
import { buildOption, TYPES } from '@/lib/chart-utils'
import type { ChartType } from '@/lib/chart-utils'
import { saveConfig, updateConfig, deleteConfig, useChartLibrary, getLibrary } from '@/lib/chart-config-storage'
import type { ChartConfig, DataSource, Period } from '@/lib/chart-config-storage'
import { addDynamicChart } from '@/lib/dashboard-storage'
import { COLORS } from '@/lib/constants'
import DraggableField from './chart-builder/DraggableField'
import type { WellField } from './chart-builder/DraggableField'
import FieldWell from './chart-builder/FieldWell'

// -- Constants ----

// CUSTOMIZE: DataSource type definition (in chart-config-storage.ts)
export type DataSource_Ref = DataSource

const SOURCE_LABELS: Record<string, string> = {} // CUSTOMIZE: Map data source keys to display labels
const SOURCE_BADGE_COLORS: Record<string, string> = {} // CUSTOMIZE: Map data source keys to badge colors

const PERIOD_OPTIONS: { value: Period | 'all'; label: string }[] = [
  { value: 'all', label: 'All time' },
  { value: 'L3M', label: 'Last 3 months' },
  { value: 'L6M', label: 'Last 6 months' },
  { value: 'YTD', label: 'Year to date' },
  { value: '12M', label: 'Last 12 months' },
]

// -- Props ----

export type SidebarMode = 'new' | 'edit' | 'library'

interface Props {
  mode: SidebarMode
  editingConfigId: string | null
  activeId: string
  onClose: () => void
  onSwitchMode: (mode: SidebarMode) => void
  onEditConfig: (configId: string) => void
}

// -- Component ----

export default function ChartBuilderSidebar({ mode, editingConfigId, activeId, onClose, onSwitchMode, onEditConfig }: Props) {
  const { data: schema } = useDataSchema()
  const configs = useChartLibrary()

  // -- Draft state --
  const [source, setSource] = useState<DataSource>('' as DataSource) // CUSTOMIZE: Set default source
  const [axisField, setAxisField] = useState<WellField | null>(null)
  const [valuesFields, setValuesFields] = useState<WellField[]>([])
  const [period, setPeriod] = useState<Period | null>('L6M')
  const [chartType, setChartType] = useState<ChartType>('bar')
  const [name, setName] = useState('')
  const [saved, setSaved] = useState(false)

  // -- DnD state --
  const [activeDragField, setActiveDragField] = useState<WellField | null>(null)
  const [, setHoveredWell] = useState<string | null>(null)

  // -- Sensors --
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  // -- Populate draft from editing config --
  useEffect(() => {
    if (mode === 'edit' && editingConfigId) {
      const config = getLibrary().configs.find((c) => c.id === editingConfigId)
      if (config) {
        setSource(config.source)
        setPeriod(config.period)
        setChartType(config.chartType)
        setName(config.name)
        const src = schema?.sources.find((s) => s.id === config.source)
        if (src) {
          const dim = src.dimensions.find((d) => d.column === config.dimension)
          setAxisField(dim ? { column: dim.column, label: dim.label, role: 'dimension' } : null)
          const wellFields: WellField[] = []
          for (const m of config.measures) {
            const measure = src.measures.find((ms) => ms.column === m)
            if (measure) wellFields.push({ column: measure.column, label: measure.label, role: 'measure' })
          }
          setValuesFields(wellFields)
        }
      }
    } else if (mode === 'new') {
      setAxisField(null)
      setValuesFields([])
      setPeriod('L6M')
      setChartType('bar')
      setName('')
      setSaved(false)
      autoPopulateAxis(source)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, editingConfigId, schema])

  // -- Source schema --
  const sourceSchema = schema?.sources.find((s) => s.id === source)
  const supportsPeriod = sourceSchema?.supports_period ?? false

  // -- Auto-populate axis when source has single dimension --
  function autoPopulateAxis(src: DataSource) {
    const srcSchema = schema?.sources.find((s) => s.id === src)
    if (srcSchema && srcSchema.dimensions.length === 1) {
      const d = srcSchema.dimensions[0]
      setAxisField({ column: d.column, label: d.label, role: 'dimension' })
    }
  }

  // -- Build fields list --
  const fields: WellField[] = useMemo(() => {
    if (!sourceSchema) return []
    const dims: WellField[] = sourceSchema.dimensions.map((d) => ({ column: d.column, label: d.label, role: 'dimension' }))
    const measures: WellField[] = sourceSchema.measures.map((m) => ({ column: m.column, label: m.label, role: 'measure' }))
    return [...dims, ...measures]
  }, [sourceSchema])

  const usedColumns = new Set([axisField?.column, ...valuesFields.map((f) => f.column)].filter(Boolean))

  // -- Source change --
  const handleSourceChange = (newSource: DataSource) => {
    setSource(newSource)
    setAxisField(null)
    setValuesFields([])
    if (!schema?.sources.find((s) => s.id === newSource)?.supports_period) {
      setPeriod(null)
    }
    autoPopulateAxis(newSource)
  }

  // -- Click-to-add --
  const handleFieldClick = (field: WellField) => {
    if (field.role === 'dimension') {
      setAxisField(field)
    } else {
      setValuesFields((prev) => (prev.some((f) => f.column === field.column) ? prev : [...prev, field]))
    }
  }

  // -- DnD handlers --
  function handleDragStart(event: DragStartEvent) {
    const data = event.active.data.current as { field: WellField } | undefined
    setActiveDragField(data?.field ?? null)
  }

  function handleDragOver(event: DragOverEvent) {
    const { over } = event
    if (!over) { setHoveredWell(null); return }
    const overId = String(over.id)
    if (overId.startsWith('well::axis')) setHoveredWell('axis')
    else if (overId.startsWith('well::values')) setHoveredWell('values')
    else setHoveredWell(null)
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveDragField(null)
    setHoveredWell(null)
    const { active, over } = event
    if (!over) return
    const activeData = active.data.current as { field: WellField; origin: string } | undefined
    if (!activeData) return
    const overId = String(over.id)

    if (activeData.origin === 'source' && overId.startsWith('well::axis')) {
      if (activeData.field.role === 'dimension') setAxisField(activeData.field)
      return
    }
    if (activeData.origin === 'source' && (overId.startsWith('well::values'))) {
      if (activeData.field.role === 'measure') {
        setValuesFields((prev) => (prev.some((f) => f.column === activeData.field.column) ? prev : [...prev, activeData.field]))
      }
      return
    }
    if (activeData.origin === 'values' && overId.startsWith('well::values::')) {
      const oldIndex = valuesFields.findIndex((f) => `well::values::${f.column}` === String(active.id))
      const newIndex = valuesFields.findIndex((f) => `well::values::${f.column}` === overId)
      if (oldIndex !== -1 && newIndex !== -1 && oldIndex !== newIndex) {
        setValuesFields((prev) => arrayMove(prev, oldIndex, newIndex))
      }
    }
  }

  // -- Live preview --
  const previewConfig = useMemo((): ChartConfig | null => {
    if (!source || !axisField || valuesFields.length === 0) return null
    return {
      id: '__preview__',
      name: 'preview',
      source,
      dimension: axisField.column,
      measures: valuesFields.map((f) => f.column),
      period: supportsPeriod ? period : null,
      chartType,
      createdAt: '',
      updatedAt: '',
    }
  }, [source, axisField, valuesFields, period, chartType, supportsPeriod])

  const { data: queryData, isFetching } = useQueryData(previewConfig)
  const previewOption = useMemo(() => {
    if (!queryData) return null
    return buildOption(queryData.headers, queryData.rows, chartType, false)
  }, [queryData, chartType])

  // -- Auto-generate name --
  useEffect(() => {
    if (mode === 'new' && !name && axisField && valuesFields.length > 0) {
      const measureNames = valuesFields.slice(0, 2).map((f) => f.label).join(', ')
      setName(`${measureNames} by ${axisField.label}`)
    }
  }, [axisField, valuesFields, mode, name])

  // -- Save --
  const canSave = axisField !== null && valuesFields.length > 0 && name.trim() !== ''

  const handleSave = () => {
    if (!canSave || !axisField) return
    const payload = {
      name: name.trim(),
      source,
      dimension: axisField.column,
      measures: valuesFields.map((f) => f.column),
      period: supportsPeriod ? period : null,
      chartType,
    }
    if (mode === 'edit' && editingConfigId) {
      updateConfig(editingConfigId, payload)
    } else {
      const config = saveConfig(payload)
      addDynamicChart(config.id, activeId)
    }
    setSaved(true)
    setTimeout(onClose, 400)
  }

  // -- Library actions --
  const handleLibraryAdd = (configId: string) => {
    addDynamicChart(configId, activeId)
  }

  const handleLibraryEdit = (configId: string) => {
    onEditConfig(configId)
  }

  const isBuilder = mode === 'new' || mode === 'edit'

  return (
    <motion.aside
      initial={{ x: 340 }}
      animate={{ x: 0 }}
      exit={{ x: 340 }}
      transition={{ type: 'spring', stiffness: 320, damping: 30 }}
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        width: 320,
        zIndex: 50,
        background: '#fff',
        borderLeft: '1px solid #e2e8f0',
        boxShadow: '-4px 0 20px rgba(0,0,0,0.08)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{ padding: '14px 16px', borderBottom: '1px solid #e2e8f0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: '#002151', margin: 0 }}>
            {mode === 'edit' ? 'Edit Chart' : mode === 'library' ? 'Chart Library' : 'Build Chart'}
          </h3>
          <button onClick={onClose} style={{ color: '#94a3b8', cursor: 'pointer', padding: 2 }}><X size={16} /></button>
        </div>
        {/* Tab toggle */}
        <div style={{ display: 'flex', gap: 4, background: '#f1f5f9', borderRadius: 6, padding: 2 }}>
          <button
            onClick={() => onSwitchMode(mode === 'edit' ? 'edit' : 'new')}
            style={{
              flex: 1, padding: '5px 0', borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: 'pointer', border: 'none',
              background: isBuilder ? '#fff' : 'transparent',
              color: isBuilder ? '#002151' : '#64748b',
              boxShadow: isBuilder ? '0 1px 2px rgba(0,0,0,0.08)' : 'none',
              transition: 'all 150ms',
            }}
          >
            Builder
          </button>
          <button
            onClick={() => onSwitchMode('library')}
            style={{
              flex: 1, padding: '5px 0', borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: 'pointer', border: 'none',
              background: mode === 'library' ? '#fff' : 'transparent',
              color: mode === 'library' ? '#002151' : '#64748b',
              boxShadow: mode === 'library' ? '0 1px 2px rgba(0,0,0,0.08)' : 'none',
              transition: 'all 150ms',
            }}
          >
            Library ({configs.length})
          </button>
        </div>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {mode === 'library' ? (
          /* -- Library Tab -- */
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {configs.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 16px', color: '#94a3b8' }}>
                <BarChart2 size={32} style={{ opacity: 0.3, margin: '0 auto 8px' }} />
                <p style={{ fontSize: 12, fontWeight: 600, color: '#64748b', marginBottom: 2 }}>No saved charts</p>
                <p style={{ fontSize: 11 }}>Use the Builder tab to create one</p>
              </div>
            ) : (
              configs.map((config) => (
                <div
                  key={config.id}
                  style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: '10px 12px', background: '#fff' }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 6, marginBottom: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: '#002151', flex: 1 }}>{config.name}</span>
                    <span style={{
                      fontSize: 9, fontWeight: 700, padding: '2px 5px', borderRadius: 3, whiteSpace: 'nowrap', flexShrink: 0,
                      background: SOURCE_BADGE_COLORS[config.source] + '18',
                      color: SOURCE_BADGE_COLORS[config.source],
                    }}>
                      {SOURCE_LABELS[config.source].split(' ')[0]}
                    </span>
                  </div>
                  <div style={{ fontSize: 10, color: '#64748b', marginBottom: 8, lineHeight: 1.5 }}>
                    {config.chartType.replace('-', ' ')} · {config.measures.slice(0, 2).join(', ')}
                    {config.measures.length > 2 && ` +${config.measures.length - 2}`}
                    {config.period && ` · ${config.period}`}
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button
                      onClick={() => handleLibraryAdd(config.id)}
                      style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: '5px 8px', borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: 'pointer', background: COLORS.brandPrimary, color: '#fff', border: 'none' }}
                    >
                      <Plus size={12} /> Add
                    </button>
                    <button
                      onClick={() => handleLibraryEdit(config.id)}
                      style={{ padding: '5px 7px', borderRadius: 5, cursor: 'pointer', background: '#f1f5f9', color: '#64748b', border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center' }}
                    >
                      <Pencil size={12} />
                    </button>
                    <button
                      onClick={() => deleteConfig(config.id)}
                      style={{ padding: '5px 7px', borderRadius: 5, cursor: 'pointer', background: '#fff1f1', color: '#dc2626', border: '1px solid #fecaca', display: 'flex', alignItems: 'center' }}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        ) : (
          /* -- Builder Tab -- */
          <DndContext
            id="field-wells-dnd"
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDragEnd={handleDragEnd}
          >
            {/* Source selector */}
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                Data Source
              </div>
              <select
                value={source}
                onChange={(e) => handleSourceChange(e.target.value as DataSource)}
                style={{ width: '100%', padding: '6px 8px', borderRadius: 6, border: '1px solid #e2e8f0', fontSize: 12, color: '#002151', background: '#fff', cursor: 'pointer', fontFamily: 'inherit' }}
              >
                {(Object.keys(SOURCE_LABELS) as DataSource[]).map((s) => (
                  <option key={s} value={s}>{SOURCE_LABELS[s]}</option>
                ))}
              </select>
            </div>

            {/* Fields list */}
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                Fields
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                {fields.map((f) => (
                  <DraggableField
                    key={f.column}
                    field={f}
                    isUsed={usedColumns.has(f.column)}
                    onClick={() => handleFieldClick(f)}
                  />
                ))}
              </div>
            </div>

            {/* Wells */}
            <FieldWell
              wellName="axis"
              label="Axis (X)"
              items={axisField ? [axisField] : []}
              onRemove={() => setAxisField(null)}
              acceptsRole="dimension"
              placeholder="Drag a dimension here"
            />
            <FieldWell
              wellName="values"
              label="Values (Y)"
              items={valuesFields}
              onRemove={(col) => setValuesFields((prev) => prev.filter((f) => f.column !== col))}
              acceptsRole="measure"
              placeholder="Drag measures here"
            />

            {/* Drag overlay */}
            <DragOverlay style={{ zIndex: 55 }}>
              {activeDragField ? (
                <div style={{
                  padding: '5px 10px', borderRadius: 5, fontSize: 11, fontWeight: 600,
                  background: '#097cf7', color: '#fff', boxShadow: '0 4px 12px rgba(9,124,247,0.3)',
                  whiteSpace: 'nowrap',
                }}>
                  {activeDragField.label}
                </div>
              ) : null}
            </DragOverlay>
          </DndContext>
        )}

        {/* Chart type (builder only) */}
        {isBuilder && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
              Chart Type
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {TYPES.map((t) => (
                <button
                  key={t}
                  onClick={() => setChartType(t as ChartType)}
                  style={{
                    padding: '4px 9px', borderRadius: 5, fontSize: 10, fontWeight: 600, cursor: 'pointer',
                    background: chartType === t ? COLORS.brandPrimary : '#f8fafc',
                    color: chartType === t ? '#fff' : '#64748b',
                    border: `1px solid ${chartType === t ? COLORS.brandPrimary : '#e2e8f0'}`,
                    transition: 'all 120ms',
                  }}
                >
                  {t.replace('-', ' ')}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Period (builder only, when supported) */}
        {isBuilder && supportsPeriod && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
              Period
            </div>
            <select
              value={period ?? 'all'}
              onChange={(e) => setPeriod(e.target.value === 'all' ? null : (e.target.value as Period))}
              style={{ width: '100%', padding: '6px 8px', borderRadius: 6, border: '1px solid #e2e8f0', fontSize: 12, color: '#002151', background: '#fff', cursor: 'pointer', fontFamily: 'inherit' }}
            >
              {PERIOD_OPTIONS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
        )}

        {/* Mini preview (builder only) */}
        {isBuilder && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
              Preview
            </div>
            <div style={{ height: 180, border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden', background: '#fafbfc', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {isFetching && !queryData ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#94a3b8', fontSize: 11 }}>
                  <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Loading...
                </div>
              ) : previewOption ? (
                <ReactECharts option={previewOption} style={{ width: '100%', height: '100%' }} opts={{ renderer: 'canvas' }} />
              ) : (
                <span style={{ color: '#94a3b8', fontSize: 11 }}>
                  {axisField && valuesFields.length > 0 ? 'No data' : 'Add fields to see preview'}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Name input (builder only) */}
        {isBuilder && (
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
              Chart Name
            </div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && canSave) handleSave() }}
              placeholder="e.g. Revenue by Month"
              style={{ width: '100%', padding: '7px 10px', borderRadius: 6, border: '1px solid #e2e8f0', fontSize: 12, color: '#002151', background: '#fff', fontFamily: 'inherit', boxSizing: 'border-box', outline: 'none' }}
            />
          </div>
        )}
      </div>

      {/* Footer (builder only) */}
      {isBuilder && (
        <div style={{ padding: '12px 16px', borderTop: '1px solid #e2e8f0', display: 'flex', gap: 8, flexShrink: 0 }}>
          <button
            onClick={onClose}
            style={{ flex: 1, padding: '7px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: '#f8fafc', color: '#64748b', border: '1px solid #e2e8f0' }}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!canSave || saved}
            style={{
              flex: 1, padding: '7px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: canSave ? 'pointer' : 'not-allowed', border: 'none',
              background: saved ? '#16a34a' : canSave ? COLORS.brandPrimary : '#e2e8f0',
              color: canSave || saved ? '#fff' : '#94a3b8',
              transition: 'all 150ms',
            }}
          >
            {saved ? 'Saved!' : mode === 'edit' ? 'Update' : 'Save & Add'}
          </button>
        </div>
      )}
    </motion.aside>
  )
}
