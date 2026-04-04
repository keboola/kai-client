'use client'

/**
 * KAI Client -- Dashboard Storage
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useState, useEffect } from 'react'
import type { AnyDashboardChart, DashboardChart } from './chart-config-storage'

export type { AnyDashboardChart, DashboardChart } from './chart-config-storage'

// -- Types ----

export interface PinnedChart {
  id: string
  title: string
  headers: string[]
  rows: string[][]
  chartType: string
  pinnedAt: string
  sourceQuestion: string
  type?: 'static'
  // Layout position/size in pixels
  x: number
  y: number
  w: number
  h: number
}

export interface Dashboard {
  id: string
  name: string
  charts: AnyDashboardChart[]
  createdAt: string
  updatedAt: string
}

// -- Constants ----

const STORAGE_KEY = 'kai-dashboards' // CUSTOMIZE: localStorage key for dashboards
const ACTIVE_KEY = 'kai-active-dashboard' // CUSTOMIZE: localStorage key for active dashboard ID
const SEEDED_KEY = 'kai-dashboard-seeded' // CUSTOMIZE: localStorage key for seeded flag
const CHANGE_EVENT = 'kai-dashboards-changed'
const MAX_CHARTS = 20
const MAX_DASHBOARDS = 10

// -- Internal ----

function readAll(): Dashboard[] {
  if (typeof window === 'undefined') return []
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed: unknown = JSON.parse(stored)
      if (Array.isArray(parsed)) return parsed as Dashboard[]
    }
  } catch { /* corrupt */ }
  return []
}

function writeAll(dashboards: Dashboard[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(dashboards))
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT))
}

function getOrCreateDefault(): Dashboard[] {
  if (typeof window === 'undefined') return []
  const all = readAll()
  if (all.length === 0) {
    const def: Dashboard = {
      id: crypto.randomUUID(),
      name: 'My Dashboard',
      charts: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    writeAll([def])
    localStorage.setItem(ACTIVE_KEY, def.id)
    return [def]
  }
  return all
}

// -- Dashboard CRUD ----

export function getActiveDashboardId(): string {
  if (typeof window === 'undefined') return ''
  const all = getOrCreateDefault()
  if (all.length === 0) return ''
  const stored = localStorage.getItem(ACTIVE_KEY)
  if (stored && all.some((d) => d.id === stored)) return stored
  return all[0].id
}

export function setActiveDashboardId(id: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(ACTIVE_KEY, id)
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT))
}

export function createDashboard(name: string): string {
  const all = getOrCreateDefault()
  if (all.length >= MAX_DASHBOARDS) return all[0].id
  const db: Dashboard = {
    id: crypto.randomUUID(),
    name,
    charts: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }
  all.push(db)
  writeAll(all)
  setActiveDashboardId(db.id)
  return db.id
}

export function renameDashboard(id: string, name: string): void {
  const all = getOrCreateDefault()
  const db = all.find((d) => d.id === id)
  if (db) {
    db.name = name
    db.updatedAt = new Date().toISOString()
    writeAll(all)
  }
}

export function deleteDashboard(id: string): void {
  let all = readAll().filter((d) => d.id !== id)
  if (all.length === 0) {
    all = [
      {
        id: crypto.randomUUID(),
        name: 'My Dashboard',
        charts: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
    ]
  }
  writeAll(all)
  if (getActiveDashboardId() === id) setActiveDashboardId(all[0].id)
}

// -- Chart CRUD ----

export function pinChart(
  chart: Omit<PinnedChart, 'id' | 'pinnedAt' | 'x' | 'y' | 'w' | 'h'>,
  dashboardId?: string,
): void {
  const all = getOrCreateDefault()
  const dbId = dashboardId ?? getActiveDashboardId()
  const db = all.find((d) => d.id === dbId)
  if (!db) return
  if (db.charts.length >= MAX_CHARTS) return

  const maxY = db.charts.reduce((max, c) => Math.max(max, c.y + c.h), 0)
  db.charts.push({
    ...chart,
    id: crypto.randomUUID(),
    pinnedAt: new Date().toISOString(),
    x: 0,
    y: maxY,
    w: 600,
    h: 300,
  })
  db.updatedAt = new Date().toISOString()
  writeAll(all)
}

export function unpinChart(chartId: string): void {
  const all = getOrCreateDefault()
  for (const db of all) {
    const idx = db.charts.findIndex((c) => c.id === chartId)
    if (idx >= 0) {
      db.charts.splice(idx, 1)
      db.updatedAt = new Date().toISOString()
      writeAll(all)
      return
    }
  }
}

export function addDynamicChart(configId: string, dashboardId?: string): void {
  const all = getOrCreateDefault()
  const dbId = dashboardId || getActiveDashboardId()
  const db = all.find((d) => d.id === dbId)
  if (!db) return
  if (db.charts.length >= MAX_CHARTS) return
  const maxY = db.charts.reduce((max, c) => Math.max(max, c.y + c.h), 0)
  const chart: DashboardChart = {
    id: crypto.randomUUID(),
    type: 'dynamic',
    configId,
    x: 0,
    y: maxY,
    w: 600,
    h: 300,
    pinnedAt: new Date().toISOString(),
  }
  db.charts.push(chart)
  db.updatedAt = new Date().toISOString()
  writeAll(all)
}

export function updateChartTitle(chartId: string, title: string): void {
  const all = getOrCreateDefault()
  for (const db of all) {
    const chart = db.charts.find((c) => c.id === chartId)
    if (chart && 'title' in chart) {
      (chart as PinnedChart).title = title
      db.updatedAt = new Date().toISOString()
      writeAll(all)
      return
    }
  }
}

export function isPinned(headers: string[], rows: string[][]): boolean {
  const all = readAll()
  const key = JSON.stringify({ headers, rows })
  for (const db of all) {
    for (const chart of db.charts) {
      if ('headers' in chart && 'rows' in chart) {
        const c = chart as PinnedChart
        // Quick check: skip if row/column count differs (avoids expensive stringify)
        if (c.rows.length !== rows.length || c.headers.length !== headers.length) continue
        if (JSON.stringify({ headers: c.headers, rows: c.rows }) === key) return true
      }
    }
  }
  return false
}

export function findPinnedChartId(headers: string[], rows: string[][]): string | null {
  const all = readAll()
  const key = JSON.stringify({ headers, rows })
  for (const db of all) {
    for (const chart of db.charts) {
      if ('headers' in chart && 'rows' in chart) {
        const c = chart as PinnedChart
        // Quick check: skip if row/column count differs (avoids expensive stringify)
        if (c.rows.length !== rows.length || c.headers.length !== headers.length) continue
        if (JSON.stringify({ headers: c.headers, rows: c.rows }) === key) return c.id
      }
    }
  }
  return null
}

export function unpinByHeadersRows(headers: string[], rows: string[][]): void {
  const chartId = findPinnedChartId(headers, rows)
  if (chartId) unpinChart(chartId)
}

export function updateChartType(chartId: string, chartType: string): void {
  const all = getOrCreateDefault()
  for (const db of all) {
    const chart = db.charts.find((c) => c.id === chartId)
    if (chart && 'chartType' in chart) {
      (chart as PinnedChart).chartType = chartType
      db.updatedAt = new Date().toISOString()
      writeAll(all)
      return
    }
  }
}

export function updateAllLayouts(
  dashboardId: string,
  layouts: Array<{ i: string; x: number; y: number; w: number; h: number }>,
): void {
  const all = getOrCreateDefault()
  const db = all.find((d) => d.id === dashboardId)
  if (!db) return
  for (const l of layouts) {
    const chart = db.charts.find((c) => c.id === l.i)
    if (chart) {
      chart.x = l.x
      chart.y = l.y
      chart.w = l.w
      chart.h = l.h
    }
  }
  db.updatedAt = new Date().toISOString()
  writeAll(all)
}

// -- Seeding ----

export function isDashboardSeeded(): boolean {
  if (typeof window === 'undefined') return false
  return localStorage.getItem(SEEDED_KEY) === '1'
}

export function markDashboardSeeded(): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(SEEDED_KEY, '1')
}

export function seedDemoCharts(charts: Omit<PinnedChart, 'pinnedAt'>[]): void {
  const all = getOrCreateDefault()
  const dbId = getActiveDashboardId()
  const db = all.find((d) => d.id === dbId) ?? all[0]
  if (!db) return

  db.charts = charts.map((c) => ({
    ...c,
    pinnedAt: new Date().toISOString(),
  }))
  db.updatedAt = new Date().toISOString()
  writeAll(all)
  markDashboardSeeded()
}

// -- React Hooks ----

export function useDashboards(): Dashboard[] {
  const [dbs, setDbs] = useState<Dashboard[]>([])
  useEffect(() => {
    setDbs(getOrCreateDefault())
    const handler = () => setDbs(getOrCreateDefault())
    window.addEventListener(CHANGE_EVENT, handler)
    window.addEventListener('storage', handler)
    return () => {
      window.removeEventListener(CHANGE_EVENT, handler)
      window.removeEventListener('storage', handler)
    }
  }, [])
  return dbs
}

export function usePinnedCharts(): PinnedChart[] {
  const dbs = useDashboards()
  const activeId = typeof window !== 'undefined' ? localStorage.getItem(ACTIVE_KEY) : null
  const db = dbs.find((d) => d.id === activeId) ?? dbs[0]
  return (db?.charts ?? []).filter((c): c is PinnedChart => !('configId' in c))
}
