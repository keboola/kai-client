/**
 * KAI Client -- Chart Utilities
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 *
 * Required consumer-app files (not in kai-nextjs template):
 * - @/lib/constants — COLORS.chart array for chart palette
 */

import { COLORS } from '@/lib/constants'

// -- Chart colors & types ----

export const C = [...COLORS.chart, '#f97316', '#06b6d4', '#ec4899', '#1e3a8a']
export const TYPES = ['bar', 'line', 'area', 'pie', 'horizontal-bar', 'stacked-bar']
export type ChartType = (typeof TYPES)[number]

export function parseNumber(s: string): number | null {
  const cleaned = s.replace(/[$,%\u20ac\u00a3\u00a5]/g, '').replace(/,/g, '').trim()
  const n = Number(cleaned)
  return isNaN(n) ? null : n
}

// -- ECharts option builder ----

export function buildOption(headers: string[], rows: string[][], chartType: ChartType, fs: boolean): object | null {
  const numericCols = headers.slice(1).map((_, i) => rows.every((r) => parseNumber(r[i + 1] ?? '') !== null))
  const labels = rows.map((r) => r[0])
  const series = headers.slice(1)
    .map((name, i) => numericCols[i] ? { name, values: rows.map((r) => parseNumber(r[i + 1] ?? '') ?? 0) } : null)
    .filter((s): s is { name: string; values: number[] } => s !== null)
  if (series.length === 0) return null

  const f = fs ? 13 : 10
  const g = fs ? { left: 80, right: 32, top: 40, bottom: 56 } : { left: 48, right: 8, top: 12, bottom: 28 }
  if (series.length > 1) g.bottom += 20

  if (chartType === 'pie') {
    return {
      tooltip: { trigger: 'item' as const, formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0, textStyle: { fontSize: f } },
      color: C,
      series: [{
        type: 'pie' as const, radius: ['32%', '62%'], center: ['50%', '45%'],
        data: labels.map((name, i) => ({ name, value: series[0]?.values[i] ?? 0 })),
        label: { fontSize: f }, itemStyle: { borderRadius: 5, borderColor: '#fff', borderWidth: 2 },
      }],
    }
  }

  const isH = chartType === 'horizontal-bar'
  const isLine = chartType === 'line' || chartType === 'area'
  const isStacked = chartType === 'stacked-bar'
  const catData = isH ? [...labels].reverse() : labels
  const catAxis = { type: 'category' as const, data: catData, axisLabel: { fontSize: f, rotate: !isH && labels.length > 5 ? 25 : 0 } }
  const valAxis = { type: 'value' as const, scale: false, axisLabel: { fontSize: f }, splitLine: { lineStyle: { color: 'rgba(0,33,81,0.06)' } } }

  return {
    tooltip: { trigger: 'axis' as const },
    legend: series.length > 1 ? { bottom: 0, textStyle: { fontSize: f } } : undefined,
    color: C, grid: g,
    xAxis: isH ? valAxis : catAxis, yAxis: isH ? catAxis : valAxis,
    series: series.map((s, i) => ({
      name: s.name, type: (isLine ? 'line' : 'bar') as 'line' | 'bar',
      data: isH ? [...s.values].reverse() : s.values,
      stack: isStacked ? 'total' : undefined, smooth: isLine,
      itemStyle: { borderRadius: !isLine ? (isH ? [0, 4, 4, 0] : [4, 4, 0, 0]) : undefined, color: C[i % C.length] },
      areaStyle: chartType === 'area' ? { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: C[i % C.length] + '25' }, { offset: 1, color: C[i % C.length] + '00' }] } } : undefined,
    })),
  }
}
