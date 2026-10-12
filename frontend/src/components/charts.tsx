// Shared chart settings so every chart reads as one system.
import type { ReactNode } from 'react'
import { ResponsiveContainer } from 'recharts'
import { fmtCompact } from '../lib/format'

export const AXIS = { tickLine: false, axisLine: { stroke: 'var(--axis)' }, tick: { fontSize: 12 } } as const
export const GRID = { vertical: false, strokeWidth: 1 } as const
export const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0]
export const HBAR_RADIUS: [number, number, number, number] = [0, 4, 4, 0]
export const yCompact = (v: number) => fmtCompact(v)

/** Height includes the x-axis band so labels never trigger a nested scroll. */
export function ChartBox({ height = 280, children }: { height?: number; children: ReactNode }) {
  return <div style={{ width: '100%', height }}><ResponsiveContainer>{children as React.ReactElement}</ResponsiveContainer></div>
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {items.map(i => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          <span className="inline-block h-[3px] w-4 rounded" style={{ background: i.dashed ? `repeating-linear-gradient(90deg, ${i.color} 0 4px, transparent 4px 7px)` : i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  )
}
