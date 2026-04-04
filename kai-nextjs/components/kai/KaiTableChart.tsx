'use client'

/**
 * KAI Client — KaiTableChart
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 *
 * Renders a markdown table returned by KAI with:
 *  - Sortable column headers (click to sort asc → desc → clear)
 *  - Chart toggle (table / bar / line)
 *  - Pin to My Dashboards button
 *  - CSV export
 *
 * Required consumer-app files (not in kai-nextjs template):
 * - @/lib/constants — COLORS.chart array for chart palette
 * - @/lib/dashboard-storage — pinChart, isPinned, unpinByHeadersRows
 * - @/lib/utils — cn() className helper
 */

import { useState, useCallback, useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import {
  Download,
  BarChart2,
  LineChart,
  Pin,
  Table,
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { COLORS } from '@/lib/constants'
import { pinChart, isPinned, unpinByHeadersRows } from '@/lib/dashboard-storage'

// ─── Types ────────────────────────────────────────────────────────────────────

interface KaiTableChartProps {
  headers: string[]
  rows: string[][]
}

type SortDir = 'asc' | 'desc' | null
type ChartMode = 'table' | 'bar' | 'line'

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Try to parse a cell value as a number for sorting/charting */
function parseNum(v: string): number | null {
  const cleaned = v.replace(/[$,%]/g, '').trim()
  const n = Number(cleaned)
  return isNaN(n) ? null : n
}

/** Check if the majority (>60%) of values in a column are numeric */
function isNumericColumn(rows: string[][], colIdx: number): boolean {
  const vals = rows.map(r => r[colIdx] ?? '')
  const numericCount = vals.filter(v => parseNum(v) !== null).length
  return numericCount > vals.length * 0.6
}

/** Get the first non-numeric column index (for chart labels) */
function firstStringCol(headers: string[], rows: string[][]): number {
  for (let i = 0; i < headers.length; i++) {
    if (!isNumericColumn(rows, i)) return i
  }
  return 0
}

/** Export rows+headers as CSV download */
function downloadCsv(headers: string[], rows: string[][]) {
  const lines = [
    headers.map(h => JSON.stringify(h)).join(','),
    ...rows.map(r => r.map(c => JSON.stringify(c ?? '')).join(',')),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'kai-table.csv'
  a.click()
  URL.revokeObjectURL(url)
}

// ─── Sort Icon ────────────────────────────────────────────────────────────────

function SortIcon({ dir }: { dir: SortDir }) {
  if (dir === 'asc') return <ChevronUp size={12} className="text-brand-primary" />
  if (dir === 'desc') return <ChevronDown size={12} className="text-brand-primary" />
  return <ChevronsUpDown size={12} className="text-gray-400 opacity-60" />
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function KaiTableChart({ headers, rows }: KaiTableChartProps) {
  const [sortCol, setSortCol] = useState<number | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>(null)
  const [mode, setMode] = useState<ChartMode>('table')
  const [pinned, setPinned] = useState(() => isPinned(headers, rows))

  // ── Sorting ────────────────────────────────────────────────────────────────

  const handleSort = useCallback(
    (colIdx: number) => {
      if (sortCol !== colIdx) {
        setSortCol(colIdx)
        setSortDir('asc')
      } else if (sortDir === 'asc') {
        setSortDir('desc')
      } else if (sortDir === 'desc') {
        setSortCol(null)
        setSortDir(null)
      } else {
        setSortDir('asc')
      }
    },
    [sortCol, sortDir]
  )

  const sortedRows = useMemo(() => {
    if (sortCol === null || sortDir === null) return rows
    return [...rows].sort((a, b) => {
      const av = a[sortCol] ?? ''
      const bv = b[sortCol] ?? ''
      const an = parseNum(av)
      const bn = parseNum(bv)
      let cmp: number
      if (an !== null && bn !== null) {
        cmp = an - bn
      } else {
        cmp = av.localeCompare(bv)
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [rows, sortCol, sortDir])

  // ── Chart data ─────────────────────────────────────────────────────────────

  const labelColIdx = useMemo(() => firstStringCol(headers, rows), [headers, rows])

  const numericCols = useMemo(
    () =>
      headers
        .map((h, i) => ({ header: h, idx: i }))
        .filter(({ idx }) => idx !== labelColIdx && isNumericColumn(rows, idx)),
    [headers, rows, labelColIdx]
  )

  const chartLabels = useMemo(
    () => sortedRows.map(r => r[labelColIdx] ?? ''),
    [sortedRows, labelColIdx]
  )

  const chartOption = useMemo(() => {
    const series = numericCols.map(({ header, idx }, si) => ({
      name: header,
      type: mode === 'bar' ? ('bar' as const) : ('line' as const),
      smooth: mode === 'line',
      data: sortedRows.map(r => {
        const n = parseNum(r[idx] ?? '')
        return n ?? 0
      }),
      itemStyle: { color: COLORS.chart[si % COLORS.chart.length] },
      lineStyle: mode === 'line' ? { width: 2 } : undefined,
      areaStyle:
        mode === 'line'
          ? { color: { type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: `${COLORS.chart[si % COLORS.chart.length]}33` }, { offset: 1, color: 'transparent' }] } }
          : undefined,
    }))

    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' as const, confine: true },
      legend:
        series.length > 1
          ? { bottom: 0, textStyle: { fontSize: 11 }, icon: 'circle', itemWidth: 8, itemHeight: 8 }
          : { show: false },
      grid: { top: 12, right: 16, bottom: series.length > 1 ? 40 : 28, left: 50, containLabel: false },
      xAxis: {
        type: 'category' as const,
        data: chartLabels,
        axisLabel: { fontSize: 10, rotate: chartLabels.length > 8 ? 30 : 0 },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value' as const,
        scale: false,
        min: 0,
        axisLabel: { fontSize: 10 },
      },
      series,
    }
  }, [mode, numericCols, sortedRows, chartLabels])

  const canChart = numericCols.length > 0 && sortedRows.length > 0

  // ── Pin handler ────────────────────────────────────────────────────────────

  const handlePin = useCallback(() => {
    if (pinned) {
      unpinByHeadersRows(headers, rows)
      setPinned(false)
    } else {
      pinChart({
        title: `KAI Table (${headers.join(', ')})`,
        headers,
        rows,
        chartType: mode === 'table' ? 'bar' : mode,
        sourceQuestion: '',
        type: 'static',
      })
      setPinned(true)
    }
  }, [pinned, headers, rows, mode])

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="my-3 rounded-xl border border-border overflow-hidden bg-surface">
      {/* Toolbar */}
      <div className="flex items-center gap-1.5 px-3 py-2 border-b border-border bg-surface">
        <span className="text-xs text-gray-400 mr-auto">
          {rows.length} row{rows.length !== 1 ? 's' : ''} · {headers.length} col{headers.length !== 1 ? 's' : ''}
        </span>

        {canChart && (
          <>
            <button
              className={cn(
                'p-1.5 rounded-md transition-colors text-xs',
                mode === 'table' ? 'bg-brand-primary/10 text-brand-primary' : 'text-gray-400 hover:text-brand-secondary hover:bg-gray-100'
              )}
              onClick={() => setMode('table')}
              aria-label="Table view"
            >
              <Table size={13} />
            </button>
            <button
              className={cn(
                'p-1.5 rounded-md transition-colors',
                mode === 'bar' ? 'bg-brand-primary/10 text-brand-primary' : 'text-gray-400 hover:text-brand-secondary hover:bg-gray-100'
              )}
              onClick={() => setMode('bar')}
              aria-label="Bar chart"
            >
              <BarChart2 size={13} />
            </button>
            <button
              className={cn(
                'p-1.5 rounded-md transition-colors',
                mode === 'line' ? 'bg-brand-primary/10 text-brand-primary' : 'text-gray-400 hover:text-brand-secondary hover:bg-gray-100'
              )}
              onClick={() => setMode('line')}
              aria-label="Line chart"
            >
              <LineChart size={13} />
            </button>
          </>
        )}

        <button
          className={cn(
            'p-1.5 rounded-md transition-colors',
            pinned ? 'text-brand-primary bg-brand-primary/10' : 'text-gray-400 hover:text-brand-secondary hover:bg-gray-100'
          )}
          onClick={handlePin}
          aria-label="Pin to dashboard"
          title={pinned ? 'Unpin from dashboard' : 'Pin to My Dashboards'}
        >
          <Pin size={13} />
        </button>

        <button
          className="p-1.5 rounded-md transition-colors text-gray-400 hover:text-brand-secondary hover:bg-gray-100"
          onClick={() => downloadCsv(headers, rows)}
          aria-label="Download CSV"
          title="Export CSV"
        >
          <Download size={13} />
        </button>
      </div>

      {/* Content */}
      {mode === 'table' ? (
        <div className="overflow-x-auto max-h-[340px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-surface z-10">
              <tr>
                {headers.map((h, i) => (
                  <th
                    key={i}
                    className="text-left px-3 py-2 text-brand-secondary/60 font-medium cursor-pointer select-none hover:text-brand-secondary whitespace-nowrap border-b border-border"
                    onClick={() => handleSort(i)}
                  >
                    <span className="flex items-center gap-1">
                      {h}
                      <SortIcon dir={sortCol === i ? sortDir : null} />
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row, ri) => (
                <tr
                  key={ri}
                  className="border-b border-border/50 hover:bg-brand-primary/5 transition-colors"
                >
                  {row.map((cell, ci) => (
                    <td key={ci} className="px-3 py-2 text-brand-secondary/80 whitespace-nowrap">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="p-3">
          <ReactECharts
            option={chartOption}
            style={{ height: 240 }}
            opts={{ renderer: 'svg' }}
          />
        </div>
      )}
    </div>
  )
}
