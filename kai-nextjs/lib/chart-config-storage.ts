'use client'

/**
 * KAI Client -- Chart Config Storage
 * Source: keboola/kai-client/kai-nextjs/
 * Copy verbatim. Only modify lines marked // CUSTOMIZE:
 */

import { useState, useEffect } from 'react'
import type { ChartType } from './chart-utils'

export type DataSource = string // CUSTOMIZE: Replace with your app's table short names as a union type
export type Period = 'L3M' | 'L6M' | 'YTD' | '12M'

export interface ChartConfig {
  id: string
  name: string
  source: DataSource
  dimension: string
  measures: string[]
  period: Period | null
  chartType: ChartType
  createdAt: string
  updatedAt: string
}

export interface DashboardChart {
  id: string
  type: 'dynamic'
  configId: string
  x: number
  y: number
  w: number
  h: number
  pinnedAt: string
}

export type AnyDashboardChart = import('./dashboard-storage').PinnedChart | DashboardChart

export interface ChartLibrary {
  configs: ChartConfig[]
}

// -- Constants ----

const LIBRARY_KEY = 'kai-chart-library'
const CHANGE_EVENT = 'kai-chart-library-changed'
const MAX_CONFIGS = 50

// -- Internal ----

function readLibrary(): ChartLibrary {
  if (typeof window === 'undefined') return { configs: [] }
  try {
    const stored = localStorage.getItem(LIBRARY_KEY)
    if (stored) {
      const parsed: unknown = JSON.parse(stored)
      if (parsed && typeof parsed === 'object' && 'configs' in parsed) {
        return parsed as ChartLibrary
      }
    }
  } catch { /* corrupt */ }
  return { configs: [] }
}

function writeLibrary(library: ChartLibrary): void {
  localStorage.setItem(LIBRARY_KEY, JSON.stringify(library))
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT))
}

// -- Public API ----

export function getLibrary(): ChartLibrary {
  return readLibrary()
}

export function saveConfig(
  config: Omit<ChartConfig, 'id' | 'createdAt' | 'updatedAt'>,
): ChartConfig {
  const library = readLibrary()
  if (library.configs.length >= MAX_CONFIGS) {
    library.configs.shift()
  }
  const now = new Date().toISOString()
  const newConfig: ChartConfig = {
    ...config,
    id: crypto.randomUUID(),
    createdAt: now,
    updatedAt: now,
  }
  library.configs.push(newConfig)
  writeLibrary(library)
  return newConfig
}

export function updateConfig(
  id: string,
  updates: Partial<Omit<ChartConfig, 'id' | 'createdAt'>>,
): void {
  const library = readLibrary()
  const config = library.configs.find((c) => c.id === id)
  if (!config) return
  Object.assign(config, updates, { updatedAt: new Date().toISOString() })
  writeLibrary(library)
}

export function deleteConfig(id: string): void {
  const library = readLibrary()
  library.configs = library.configs.filter((c) => c.id !== id)
  writeLibrary(library)
}

// -- React Hook ----

export function useChartLibrary(): ChartConfig[] {
  const [configs, setConfigs] = useState<ChartConfig[]>([])
  useEffect(() => {
    setConfigs(readLibrary().configs)
    const handler = () => setConfigs(readLibrary().configs)
    window.addEventListener(CHANGE_EVENT, handler)
    window.addEventListener('storage', handler)
    return () => {
      window.removeEventListener(CHANGE_EVENT, handler)
      window.removeEventListener('storage', handler)
    }
  }, [])
  return configs
}
