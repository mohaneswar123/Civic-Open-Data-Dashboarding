import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Tooltip, XAxis, YAxis } from 'recharts'
import { ChevronDown, Lock } from 'lucide-react'
import { Badge, Card, ChartCard, DataTable, Gate, PageHeader } from '../components/ui'
import { AXIS, ChartBox, GRID, HBAR_RADIUS } from '../components/charts'
import { useApi } from '../lib/hooks'
import { hasRole, useAuth } from '../lib/auth'
import { fmt } from '../lib/format'

interface CardData { model: string; available: boolean; title: string; task: string; target: string; split: Record<string, string | number>; selected: string; limitations: string[]; trained_at: string }

export default function Models() {
  const cards = useApi<CardData[]>('/api/models')
  const { user } = useAuth()
  const detailed = hasRole(user, 'policy')
  return (
    <div>
      <PageHeader title="Model transparency" subtitle="What each model predicts, how it was tested, and its known limitations. Every model is compared against a simple baseline on data from years (or records) it never saw." />
      <Gate state={cards}>{d => (
        <div className="space-y-4">
          {d.filter(c => c.available).map(c => <ModelCard key={c.model} c={c} detailed={detailed} />)}
        </div>
      )}</Gate>
    </div>
  )
}

function ModelCard({ c, detailed }: { c: CardData; detailed: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink">{c.title}</h2>
          <p className="mt-1 text-xs text-ink-2"><b className="text-ink">Predicts:</b> {c.target} · <b className="text-ink">Task:</b> {c.task}</p>
          <p className="mt-1 text-xs text-ink-2"><b className="text-ink">Tested on:</b> {String(c.split.test ?? c.split.type)} ({String(c.split.test_rows)} rows), trained on {String(c.split.train ?? 'held-in data')} · <b className="text-ink">Selected:</b> {c.selected.replace(/_/g, ' ')}</p>
        </div>
        <Badge>{c.model}</Badge>
      </div>
      <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-ink-2">{c.limitations.map(l => <li key={l}>{l}</li>)}</ul>
      {detailed ? (
        <button onClick={() => setOpen(!open)} className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-accent">
          <ChevronDown size={14} className={open ? 'rotate-180 transition' : 'transition'} /> {open ? 'Hide' : 'Show'} full evaluation report
        </button>
      ) : (
        <Link to="/login" className="mt-3 inline-flex items-center gap-1 text-xs text-muted"><Lock size={12} /> Full evaluation (baselines, condition-wise errors) for policy makers</Link>
      )}
      {open && <Report name={c.model} />}
    </Card>
  )
}

type Metrics = Record<string, number | number[] | null | Record<string, number>>
interface ReportData {
  results: Record<string, Metrics> | Record<string, Record<string, Metrics>>
  selected: string
  feature_importance: { feature: string; importance: number }[] | Record<string, { feature: string; importance: number }[]>
  by_condition?: unknown
  conclusion?: string
  interval?: Record<string, number | string>
  rainfall_contribution?: { conclusion: string }
  calibration?: { bin: string; mean_pred: number; observed: number; n: number }[]
  by_horizon?: Record<string, unknown>[]
  future_years?: Record<string, unknown>
}

const METRIC_KEYS = ['r2', 'mae', 'rmse', 'wape_pct', 'median_ape_pct', 'roc_auc', 'pr_auc', 'f1', 'precision', 'recall', 'accuracy', 'brier']

function ResultsTable({ results, selected }: { results: Record<string, Metrics>; selected: string }) {
  const keys = METRIC_KEYS.filter(k => Object.values(results).some(r => typeof r[k] === 'number'))
  const rows = Object.entries(results).map(([name, m]) => ({ model: name === selected ? `${name} ★` : name, ...Object.fromEntries(keys.map(k => [k, m[k] as number])) }))
  return <DataTable rows={rows} columns={[{ key: 'model', label: 'Model' }, ...keys.map(k => ({ key: k, label: k.toUpperCase().replace('_PCT', ' %'), format: (v: unknown) => fmt(v as number, 3) }))]} />
}

function Report({ name }: { name: string }) {
  const s = useApi<ReportData>(`/api/models/${name}`)
  return (
    <div className="mt-4 space-y-4 border-t border-line pt-4">
      <Gate state={s}>{r => {
        const nested = name === 'weather_nextday'
        const imp = Array.isArray(r.feature_importance) ? { model: r.feature_importance } : r.feature_importance
        return (
          <>
            {nested
              ? Object.entries(r.results as Record<string, Record<string, Metrics>>).map(([k, v]) => (
                <div key={k}><h4 className="mb-2 text-xs font-semibold text-ink uppercase">{k}: baselines vs model (test 2022–2024)</h4><ResultsTable results={v} selected={r.selected} /></div>))
              : <div><h4 className="mb-2 text-xs font-semibold text-ink uppercase">Baselines vs candidates (held-out test)</h4><ResultsTable results={r.results as Record<string, Metrics>} selected={r.selected} /></div>}
            {r.conclusion && <p className="text-xs text-ink-2"><b className="text-ink">Conclusion:</b> {r.conclusion}</p>}
            {r.rainfall_contribution && <p className="text-xs text-ink-2"><b className="text-ink">Rainfall ablation:</b> {r.rainfall_contribution.conclusion}.</p>}
            {r.interval && <p className="text-xs text-ink-2"><b className="text-ink">Uncertainty interval:</b> nominal {fmt(Number(r.interval.nominal) * 100, 0)}%, achieved {fmt(Number(r.interval.empirical_coverage) * 100, 1)}% on test ({String(r.interval.type)}).</p>}
            <div className="grid gap-4 lg:grid-cols-2">
              {Object.entries(imp).map(([k, rows]) => (
                <ChartCard key={k} title={`Feature importance${k !== 'model' ? `: ${k}` : ''}`} rows={rows}>
                  <ChartBox height={Math.max(180, rows.slice(0, 10).length * 24)}>
                    <BarChart data={rows.slice(0, 10)} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={3}>
                      <CartesianGrid {...GRID} horizontal={false} vertical />
                      <XAxis type="number" {...AXIS} tickFormatter={v => `${Math.round(v * 100)}%`} />
                      <YAxis type="category" dataKey="feature" {...AXIS} width={150} interval={0} />
                      <Tooltip formatter={(v: number) => [`${fmt(100 * v, 1)}%`, 'Share of gain']} />
                      <Bar dataKey="importance" fill="var(--s1)" radius={HBAR_RADIUS} />
                    </BarChart>
                  </ChartBox>
                </ChartCard>
              ))}
              {r.calibration && (
                <ChartCard title="Calibration: predicted vs observed rate" subtitle="Bars should match the predicted bin" rows={r.calibration}>
                  <ChartBox height={220}>
                    <BarChart data={r.calibration} margin={{ top: 8, right: 8 }} barCategoryGap={3}>
                      <CartesianGrid {...GRID} /><XAxis dataKey="bin" {...AXIS} /><YAxis {...AXIS} width={40} domain={[0, 1]} />
                      <Tooltip formatter={(v: number, n) => [fmt(v, 3), n]} />
                      <Bar dataKey="observed" radius={[4, 4, 0, 0]}>{r.calibration.map(c => <Cell key={c.bin} fill="var(--s1)" />)}</Bar>
                    </BarChart>
                  </ChartBox>
                </ChartCard>
              )}
            </div>
            {r.by_horizon && (
              <div>
                <h4 className="mb-2 text-xs font-semibold text-ink uppercase">Accuracy by forecast horizon (how far ahead)</h4>
                <DataTable rows={r.by_horizon} columns={Object.keys(r.by_horizon[0] ?? {}).map(k => ({ key: k, label: k, format: (v: unknown) => typeof v === 'number' && !Number.isInteger(v) ? fmt(v, 3) : String(v ?? '—') }))} maxHeight={280} />
              </div>
            )}
            {r.future_years && <p className="text-xs text-ink-2"><b className="text-ink">Future years:</b> {String(r.future_years.method)}; {String(r.future_years.served_model)}.</p>}
            {Array.isArray(r.by_condition) && (
              <div>
                <h4 className="mb-2 text-xs font-semibold text-ink uppercase">Condition-wise results (a model can be good on average and bad for a group)</h4>
                <DataTable rows={r.by_condition as Record<string, unknown>[]} columns={Object.keys((r.by_condition as Record<string, unknown>[])[0] ?? {}).map(k => ({ key: k, label: k }))} maxHeight={280} />
              </div>
            )}
            {r.by_condition && !Array.isArray(r.by_condition) && Object.entries(r.by_condition as Record<string, Record<string, unknown>[]>).map(([k, rows]) => (
              <div key={k}>
                <h4 className="mb-2 text-xs font-semibold text-ink uppercase">Condition-wise: {k.replace('_', ' ')}</h4>
                <DataTable rows={rows} columns={Object.keys(rows[0] ?? {}).map(c => ({ key: c, label: c }))} maxHeight={260} />
              </div>
            ))}
          </>
        )
      }}</Gate>
    </div>
  )
}
