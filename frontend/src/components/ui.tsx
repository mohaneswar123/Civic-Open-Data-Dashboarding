import { useState, type ReactNode } from 'react'
import { AlertTriangle, Download, Info, Loader2, Table2, BarChart3, Lock } from 'lucide-react'
import { downloadCsv } from '../lib/format'

export const SERIES = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)', 'var(--s6)', 'var(--s7)', 'var(--s8)']

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-ink-2">{subtitle}</p>}
      </div>
      {children}
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-surface p-5 ${className}`}>{children}</div>
}

/** Honesty panel: how to read the chart, what is excluded, what it does NOT show. */
export function Notes({ notes }: { notes?: string[] }) {
  if (!notes?.length) return null
  return (
    <details className="group mt-3 rounded-lg bg-surface-2 px-3 py-2 text-xs text-ink-2">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 font-medium text-ink-2 select-none">
        <Info size={14} /> How to read this honestly <span className="text-muted group-open:hidden">({notes.length})</span>
      </summary>
      <ul className="mt-2 list-disc space-y-1 pl-5">{notes.map(n => <li key={n}>{n}</li>)}</ul>
    </details>
  )
}

interface ChartCardProps {
  title: string
  subtitle?: ReactNode
  rows?: object[]
  columns?: { key: string; label: string; format?: (v: unknown) => string }[]
  notes?: string[]
  children: ReactNode
  className?: string
  action?: ReactNode
}

/** Every chart has a table-view twin and a CSV export, so no value is reachable only by hover. */
export function ChartCard({ title, subtitle, rows, columns, notes, children, className = '', action }: ChartCardProps) {
  const [table, setTable] = useState(false)
  const cols = columns ?? (rows?.length ? Object.keys(rows[0] as Record<string, unknown>).map(k => ({ key: k, label: k })) : [])
  return (
    <Card className={className}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {action}
          {rows && rows.length > 0 && (
            <>
              <IconButton label={table ? 'Show chart' : 'Show table'} onClick={() => setTable(!table)}>
                {table ? <BarChart3 size={15} /> : <Table2 size={15} />}
              </IconButton>
              <IconButton label="Download CSV" onClick={() => downloadCsv(`${title.replace(/\W+/g, '_')}.csv`, rows as Record<string, unknown>[])}>
                <Download size={15} />
              </IconButton>
            </>
          )}
        </div>
      </div>
      {table && rows ? <DataTable rows={rows} columns={cols} maxHeight={320} /> : children}
      <Notes notes={notes} />
    </Card>
  )
}

export function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" title={label} aria-label={label} onClick={onClick}
      className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-ink focus-visible:outline-2 focus-visible:outline-accent">
      {children}
    </button>
  )
}

export function DataTable({ rows, columns, maxHeight = 420 }: {
  rows: object[]; columns: { key: string; label: string; format?: (v: unknown) => string }[]; maxHeight?: number
}) {
  const data = rows as Record<string, unknown>[]
  const show = (v: unknown) => v == null ? '—' : typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString('en-IN') : v.toLocaleString('en-IN', { maximumFractionDigits: 3 })) : typeof v === 'boolean' ? (v ? 'yes' : 'no') : String(v)
  return (
    <div className="overflow-auto rounded-lg border border-line" style={{ maxHeight }}>
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-surface-2 text-ink-2">
          <tr>{columns.map(c => <th key={c.key} className="px-3 py-2 font-medium whitespace-nowrap">{c.label}</th>)}</tr>
        </thead>
        <tbody className="tabular">
          {data.map((r, i) => (
            <tr key={i} className="border-t border-line text-ink">
              {columns.map(c => <td key={c.key} className="px-3 py-1.5 whitespace-nowrap">{c.format ? c.format(r[c.key]) : show(r[c.key])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function StatTile({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <Card className="!p-4">
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink">{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-2">{hint}</div>}
    </Card>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="flex items-center gap-2 p-6 text-sm text-muted"><Loader2 className="animate-spin" size={16} /> {label}</div>
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-[color:var(--critical)]/40 bg-[color:var(--critical)]/8 p-3 text-sm text-ink">
      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-critical" /> <span>{message}</span>
    </div>
  )
}

export function Warning({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-[color:var(--warning)]/50 bg-[color:var(--warning)]/10 p-3 text-xs text-ink">
      <AlertTriangle size={14} className="mt-0.5 shrink-0" style={{ color: 'var(--serious)' }} /> <span>{children}</span>
    </div>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div role="tablist" className="mb-6 flex flex-wrap gap-1 border-b border-line">
      {tabs.map(t => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${value === t.id ? 'border-accent text-ink' : 'border-transparent text-muted hover:text-ink'}`}>
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-2">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-muted">{hint}</span>}
    </label>
  )
}

const inputCls = 'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent/20'

export function Select({ value, onChange, options, className = '' }: {
  value: string; onChange: (v: string) => void; options: (string | { value: string; label: string })[]; className?: string
}) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} className={`${inputCls} ${className}`}>
      {options.map(o => typeof o === 'string'
        ? <option key={o} value={o}>{o}</option>
        : <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputCls} ${props.className ?? ''}`} />
}

export function Button({ children, variant = 'primary', ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' }) {
  const cls = variant === 'primary'
    ? 'bg-accent text-accent-ink hover:opacity-90'
    : 'border border-line text-ink hover:bg-surface-2'
  return <button {...props} className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition disabled:opacity-50 ${cls} ${props.className ?? ''}`}>{children}</button>
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'good' | 'warning' | 'critical' | 'accent' }) {
  const map = {
    neutral: 'bg-surface-2 text-ink-2',
    good: 'bg-[color:var(--good)]/12 text-good',
    warning: 'bg-[color:var(--warning)]/18 text-ink',
    critical: 'bg-[color:var(--critical)]/12 text-critical',
    accent: 'bg-accent/12 text-accent',
  }
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${map[tone]}`}>{children}</span>
}

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="mb-5 flex flex-wrap items-end gap-3 rounded-xl border border-line bg-surface p-3">{children}</div>
}

export function Locked({ role }: { role: string }) {
  return (
    <Card className="flex items-center gap-3 text-sm text-ink-2">
      <Lock size={16} /> Sign in as <b className="text-ink">{role}</b> to see this section.
    </Card>
  )
}

export function Gate<T>({ state, children }: { state: { data: T | null; error: string | null; loading: boolean }; children: (d: T) => ReactNode }) {
  if (state.error && !state.data) return <ErrorBox message={state.error} />
  if (!state.data) return <Loading />
  return <div className={state.loading ? 'opacity-60 transition-opacity' : 'transition-opacity'}>{children(state.data)}</div>
}
