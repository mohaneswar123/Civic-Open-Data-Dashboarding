import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, ErrorBar, Line, LineChart, ReferenceLine, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import { CheckCircle2, CircleMinus } from 'lucide-react'
import {
  Badge, Card, ChartCard, DataTable, Field, FilterBar, Gate, Notes, PageHeader, Select, StatTile, Tabs, Warning,
} from '../components/ui'
import { AXIS, BAR_RADIUS, ChartBox, GRID, HBAR_RADIUS, Legend, yCompact } from '../components/charts'
import { useApi, useLocalState } from '../lib/hooks'
import { fmt, fmtInt, fmtP, fmtPct, fmtSigned } from '../lib/format'

type Tab = 'yield' | 'relationship' | 'rainfall' | 'suicides' | 'diabetes' | 'weather'
const TABS: { id: Tab; label: string }[] = [
  { id: 'yield', label: 'Crop yield disparity' }, { id: 'relationship', label: 'Crop ↔ rainfall relationship' },
  { id: 'rainfall', label: 'Rainfall variability' }, { id: 'suicides', label: 'Suicides deep-dive' },
  { id: 'diabetes', label: 'Diabetes risk factors' }, { id: 'weather', label: 'Weather extremes' },
]

export default function Advanced() {
  const [tab, setTab] = useLocalState<Tab>('civic.adv.tab', 'yield')
  return (
    <div>
      <PageHeader title="Advanced analytics" subtitle="Disparity indices, trends with significance tests, relationship analysis with uncertainty, and data-quality reconciliation. For policy makers." />
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      {tab === 'yield' && <YieldDisparity />}
      {tab === 'relationship' && <Relationship />}
      {tab === 'rainfall' && <RainfallVar />}
      {tab === 'suicides' && <SuicidesDeep />}
      {tab === 'diabetes' && <DiabetesRisk />}
      {tab === 'weather' && <WeatherExtremes />}
    </div>
  )
}

const Sig = ({ ok }: { ok: boolean | null | undefined }) => ok
  ? <Badge tone="accent"><CheckCircle2 size={11} /> p &lt; 0.05</Badge>
  : <Badge><CircleMinus size={11} /> not significant</Badge>

function useCropOptions() {
  return useApi<{ crops: string[]; states: string[] }>('/api/policy/crop/options')
}

// ---------------------------------------------------------------- crop yield disparity
interface Disparity {
  crop: string
  states: { state: string; median_yield: number; years: number; trend_per_year: number | null; trend_p: number | null; trend_significant: boolean; avg_area_ha: number }[]
  gini_by_year: { year: number; gini: number | null; states: number }[]
  national_yield: { year: number; yield_t_ha: number; states: number }[]
  excluded_years: number[]; min_states: number
  gap_ratio: number | null
  notes: string[]
}
interface Districts { districts: { district: string; median_yield: number; years: number; latest_year: number; avg_area_ha: number; trend_per_year: number | null; trend_significant: boolean }[]; cv: number | null; gini: number | null }

function YieldDisparity() {
  const opts = useCropOptions()
  const [crop, setCrop] = useState('Rice')
  const [state, setState] = useState('Punjab')
  const s = useApi<Disparity>(`/api/policy/crop/disparity?crop=${encodeURIComponent(crop)}`)
  const dist = useApi<Districts>(`/api/policy/crop/districts?crop=${encodeURIComponent(crop)}&state=${encodeURIComponent(state)}`)
  return (
    <div>
      <FilterBar>
        <Field label="Crop"><Select value={crop} onChange={setCrop} options={opts.data?.crops ?? [crop]} className="min-w-44" /></Field>
        <Field label="State for district drill-down"><Select value={state} onChange={setState} options={opts.data?.states ?? [state]} className="min-w-52" /></Field>
      </FilterBar>
      <Gate state={s}>{d => {
        const reliable = d.states.filter(x => x.years >= 5)
        const gl = d.gini_by_year.filter(g => g.gini != null)
        return (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatTile label="Highest median yield" value={`${fmt(reliable[0]?.median_yield)} t/ha`} hint={reliable[0]?.state} />
              <StatTile label="Lowest median yield" value={`${fmt(reliable.at(-1)?.median_yield)} t/ha`} hint={reliable.at(-1)?.state} />
              <StatTile label="Top-to-bottom gap" value={d.gap_ratio ? `${fmt(d.gap_ratio, 1)}×` : '—'} hint="ratio of best to worst state" />
              <StatTile label="Inequality (Gini), latest" value={fmt(gl.at(-1)?.gini, 3)} hint={`${gl.at(-1)?.year}, across ${gl.at(-1)?.states} states`} />
            </div>
            <div className="grid gap-5 lg:grid-cols-2">
              <ChartCard title={`${d.crop}: national yield`} subtitle={`Total production ÷ total area, t/ha${d.excluded_years.length ? ` · ${d.excluded_years.join(", ")} hidden (fewer than ${d.min_states} states reported)` : ""}`} rows={d.national_yield}>
                <ChartBox height={240}>
                  <LineChart data={d.national_yield} margin={{ top: 8, right: 16 }}>
                    <CartesianGrid {...GRID} /><XAxis dataKey="year" {...AXIS} /><YAxis {...AXIS} width={40} domain={['auto', 'auto']} />
                    <Tooltip formatter={(v: number) => [`${fmt(v)} t/ha`, 'Yield']} />
                    <Line dataKey="yield_t_ha" stroke="var(--s1)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                  </LineChart>
                </ChartBox>
              </ChartCard>
              <ChartCard title="Regional inequality over time (Gini across states)" subtitle="0 = equal yields everywhere; higher = wider gap. Low-coverage years hidden" rows={d.gini_by_year}>
                <ChartBox height={240}>
                  <LineChart data={gl} margin={{ top: 8, right: 16 }}>
                    <CartesianGrid {...GRID} /><XAxis dataKey="year" {...AXIS} /><YAxis {...AXIS} width={44} domain={[0, 'auto']} />
                    <Tooltip formatter={(v: number) => [fmt(v, 3), 'Gini']} />
                    <Line dataKey="gini" stroke="var(--s7)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                  </LineChart>
                </ChartBox>
              </ChartCard>
            </div>
            <ChartCard title={`${d.crop}: median yield by state`} subtitle="t/ha; faded = fewer than 5 reporting years (unreliable)" rows={d.states} notes={d.notes}>
              <ChartBox height={Math.max(260, d.states.length * 22)}>
                <BarChart data={d.states} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={2}>
                  <CartesianGrid {...GRID} horizontal={false} vertical />
                  <XAxis type="number" {...AXIS} /><YAxis type="category" dataKey="state" {...AXIS} width={150} interval={0} />
                  <Tooltip formatter={(v: number, _n, p) => [`${fmt(v)} t/ha (${(p.payload as Disparity['states'][0]).years} yrs)`, 'Median yield']} />
                  <Bar dataKey="median_yield" radius={HBAR_RADIUS}>
                    {d.states.map(x => <Cell key={x.state} fill="var(--s1)" fillOpacity={x.years >= 5 ? 1 : 0.3} />)}
                  </Bar>
                </BarChart>
              </ChartBox>
            </ChartCard>
            <Card>
              <h3 className="mb-3 text-sm font-semibold text-ink">Yield trends by state</h3>
              <DataTable rows={d.states} columns={[
                { key: 'state', label: 'State' }, { key: 'median_yield', label: 'Median t/ha', format: v => fmt(v as number) },
                { key: 'years', label: 'Years' }, { key: 'trend_per_year', label: 'Trend (t/ha per yr)', format: v => fmtSigned(v as number, 3) },
                { key: 'trend_p', label: 'p-value', format: v => fmtP(v as number) },
                { key: 'trend_significant', label: 'Significant?', format: v => (v ? 'yes' : 'no') },
              ]} />
            </Card>
          </div>
        )
      }}</Gate>
      <div className="mt-5">
        <Gate state={dist}>{d => (
          <ChartCard title={`District drill-down: ${crop} in ${state}`}
            subtitle={d.districts.length ? `${d.districts.length} districts · CV ${fmt(d.cv, 2)} · Gini ${fmt(d.gini, 3)}` : 'No records for this crop in this state'}
            rows={d.districts}>
            {d.districts.length > 0 && (
              <ChartBox height={Math.max(200, d.districts.length * 20)}>
                <BarChart data={d.districts} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={2}>
                  <CartesianGrid {...GRID} horizontal={false} vertical />
                  <XAxis type="number" {...AXIS} /><YAxis type="category" dataKey="district" {...AXIS} width={140} interval={0} />
                  <Tooltip formatter={(v: number) => [`${fmt(v)} t/ha`, 'Median yield']} />
                  <Bar dataKey="median_yield" fill="var(--s1)" radius={HBAR_RADIUS} />
                </BarChart>
              </ChartBox>
            )}
          </ChartCard>
        )}</Gate>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- crop <-> rainfall
interface Corr { rho: number | null; p_value: number | null; ci95: [number, number] | null; n: number; strength: string; significant?: boolean }
interface Relationship {
  crop: string; state: string; pooled: Corr
  per_state: (Corr & { state: string })[]
  points: { state: string; year: number; monsoon_departure_pct: number; yield_anomaly_detrended: number | null; yield_t_ha: number }[]
  multiple_testing: { tests: number; significant: number; expected_false_positives: number }
  model_ablation: { rmse_improvement_log: number; importance_share: number; conclusion: string } | null
  notes: string[]
}

function Relationship() {
  const opts = useCropOptions()
  const [crop, setCrop] = useState('Rice')
  const [state, setState] = useState('All')
  const s = useApi<Relationship>(`/api/policy/crop/rainfall?crop=${encodeURIComponent(crop)}&state=${encodeURIComponent(state)}`)
  return (
    <div>
      <FilterBar>
        <Field label="Crop"><Select value={crop} onChange={setCrop} options={opts.data?.crops ?? [crop]} className="min-w-44" /></Field>
        <Field label="State"><Select value={state} onChange={setState} options={['All', ...(opts.data?.states ?? [])]} className="min-w-52" /></Field>
      </FilterBar>
      <Gate state={s}>{d => {
        const p = d.pooled
        const pts = d.points.filter(x => x.yield_anomaly_detrended != null)
        const forest = d.per_state.filter(r => r.rho != null).map(r => ({ ...r, err: [r.rho! - r.ci95![0], r.ci95![1] - r.rho!] }))
        return (
          <div className="space-y-5">
            <Card>
              <h3 className="text-sm font-semibold text-ink">Question: do years with a wetter or drier monsoon have higher or lower {d.crop} yields?</h3>
              <p className="mt-1 text-xs text-ink-2">Method: each state's yield is compared with its own typical level, and its long-run technology trend is removed. The result is ranked against the monsoon departure from normal (Spearman correlation, 95% bootstrap interval).</p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatTile label={`Correlation (ρ), ${d.state === 'All' ? 'all states' : d.state}`} value={fmt(p.rho, 2)} hint={p.ci95 ? `95% CI ${fmt(p.ci95[0], 2)} to ${fmt(p.ci95[1], 2)}` : p.strength} />
                <StatTile label="Strength" value={<span className="capitalize">{p.strength}</span>} hint={p.rho != null ? (p.rho > 0 ? 'wetter years go with higher yield' : 'wetter years go with lower yield') : undefined} />
                <StatTile label="Evidence" value={`n = ${p.n}`} hint={<>p = {fmtP(p.p_value)} <Sig ok={p.significant} /></>} />
                <StatTile label="Does rainfall improve prediction?" value={d.model_ablation ? (d.model_ablation.rmse_improvement_log > 0.005 ? 'Yes' : 'No') : '—'}
                  hint={d.model_ablation ? `Held-out error change: ${fmtSigned(-d.model_ablation.rmse_improvement_log, 4)} (log RMSE)` : undefined} />
              </div>
              {d.model_ablation && <p className="mt-3 text-xs text-ink-2"><b className="text-ink">Model ablation (2011–2015 test years):</b> {d.model_ablation.conclusion}.</p>}
            </Card>
            {d.multiple_testing.tests > 0 && (
              <Warning>
                {d.multiple_testing.significant} of {d.multiple_testing.tests} states show p &lt; 0.05. By chance alone about {d.multiple_testing.expected_false_positives} would,
                so individual "significant" states should be treated as leads to investigate, not conclusions.
              </Warning>
            )}
            <div className="grid gap-5 lg:grid-cols-2">
              <ChartCard title="Monsoon departure vs yield anomaly" subtitle="Each dot is one state-year. x: monsoon % from normal; y: detrended yield % from state's normal" rows={pts}>
                <ChartBox height={320}>
                  <ScatterChart margin={{ top: 8, right: 16, bottom: 8 }}>
                    <CartesianGrid {...GRID} vertical />
                    <XAxis type="number" dataKey="monsoon_departure_pct" name="Monsoon departure" unit="%" {...AXIS} />
                    <YAxis type="number" dataKey="yield_anomaly_detrended" name="Yield anomaly" unit="%" {...AXIS} width={52} />
                    <ZAxis range={[36, 36]} />
                    <ReferenceLine x={0} stroke="var(--axis)" /><ReferenceLine y={0} stroke="var(--axis)" />
                    <Tooltip cursor={{ strokeDasharray: '0' }} formatter={(v: number, n) => [`${fmt(v, 1)}%`, n]}
                      labelFormatter={() => ''} content={({ payload }) => {
                        const q = payload?.[0]?.payload as Relationship['points'][0] | undefined
                        if (!q) return null
                        return <div className="recharts-default-tooltip p-2"><b>{q.state} {q.year}</b><br />Monsoon {fmtSigned(q.monsoon_departure_pct)}%<br />Yield anomaly {fmtSigned(q.yield_anomaly_detrended ?? 0)}%<br />Yield {fmt(q.yield_t_ha)} t/ha</div>
                      }} />
                    <Scatter data={pts} fill="var(--s1)" fillOpacity={0.55} stroke="var(--surface)" strokeWidth={1} />
                  </ScatterChart>
                </ChartBox>
              </ChartCard>
              <ChartCard title="Correlation by state, with 95% interval" subtitle="Bars crossing 0 mean the direction is uncertain" rows={d.per_state} notes={d.notes}>
                <ChartBox height={Math.max(320, forest.length * 20)}>
                  <BarChart data={forest} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={3}>
                    <CartesianGrid {...GRID} horizontal={false} vertical />
                    <XAxis type="number" domain={[-1, 1]} {...AXIS} /><YAxis type="category" dataKey="state" {...AXIS} width={140} interval={0} />
                    <ReferenceLine x={0} stroke="var(--ink-2)" />
                    <Tooltip formatter={(v: number, _n, item) => { const r = item.payload as Corr; return [`ρ ${fmt(v, 2)} (CI ${fmt(r.ci95?.[0], 2)}–${fmt(r.ci95?.[1], 2)}, n=${r.n}, p=${fmtP(r.p_value)})`, 'Spearman'] }} />
                    <Bar dataKey="rho" radius={4}>
                      {forest.map(r => <Cell key={r.state} fill={r.rho! >= 0 ? 'var(--div-pos)' : 'var(--div-neg)'} fillOpacity={r.significant ? 1 : 0.4} />)}
                      <ErrorBar dataKey="err" width={4} strokeWidth={1.5} stroke="var(--ink-2)" direction="x" />
                    </Bar>
                  </BarChart>
                </ChartBox>
              </ChartCard>
            </div>
          </div>
        )
      }}</Gate>
    </div>
  )
}

// ---------------------------------------------------------------- rainfall variability
interface RainDisp { subdivisions: { subdivision: string; mean_annual_mm: number; cv: number; trend_mm_per_decade: number | null; trend_p: number | null; trend_significant: boolean; deficient_years_pct: number; excess_years_pct: number; recent_vs_early_pct: number | null; years: number }[]; notes: string[] }
interface Sub { years: { year: number; annual: number; jun_sep: number; rolling10: number | null; flag_annual_repaired: boolean }[]; trend: { slope: number | null; p_value: number | null; significant: boolean; ci95: [number, number] | null }; monsoon_trend: { slope: number | null; significant: boolean } }

function RainfallVar() {
  const s = useApi<RainDisp>('/api/policy/rainfall/disparity')
  const [sub, setSub] = useState('VIDARBHA')
  const one = useApi<Sub>(`/api/policy/rainfall/subdivision?name=${encodeURIComponent(sub)}`)
  return (
    <Gate state={s}>{d => (
      <div className="space-y-5">
        <ChartCard title="Rainfall reliability by sub-division" subtitle="Coefficient of variation: higher = more unpredictable year to year" rows={d.subdivisions} notes={d.notes}>
          <ChartBox height={300}>
            <BarChart data={d.subdivisions} margin={{ top: 8, right: 8 }} barCategoryGap={1}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="subdivision" {...AXIS} tick={false} height={20} label={{ value: 'Sub-divisions, most → least variable (hover for names)', fill: 'var(--muted)', fontSize: 12 }} />
              <YAxis {...AXIS} width={40} />
              <Tooltip formatter={(v: number) => [fmt(v, 3), 'CV']} />
              <Bar dataKey="cv" radius={BAR_RADIUS}>
                {d.subdivisions.map(x => <Cell key={x.subdivision} fill={x.subdivision === sub ? 'var(--s2)' : 'var(--s1)'} onClick={() => setSub(x.subdivision)} cursor="pointer" />)}
              </Bar>
            </BarChart>
          </ChartBox>
        </ChartCard>
        <FilterBar>
          <Field label="Sub-division"><Select value={sub} onChange={setSub} options={d.subdivisions.map(x => x.subdivision).sort()} className="min-w-64" /></Field>
        </FilterBar>
        <Gate state={one}>{o => (
          <div className="grid gap-5 lg:grid-cols-3">
            <div className="space-y-4">
              <StatTile label="Long-term trend (annual)" value={o.trend.slope != null ? `${fmtSigned(o.trend.slope * 10, 1)} mm/decade` : '—'}
                hint={<>p = {fmtP(o.trend.p_value)} <Sig ok={o.trend.significant} /></>} />
              <StatTile label="Monsoon trend" value={o.monsoon_trend.slope != null ? `${fmtSigned(o.monsoon_trend.slope * 10, 1)} mm/decade` : '—'} hint={<Sig ok={o.monsoon_trend.significant} />} />
              <StatTile label="Repaired years" value={o.years.filter(y => y.flag_annual_repaired).length}
                hint="ANNUAL disagreed with monthly sum and was recomputed" />
            </div>
            <ChartCard className="lg:col-span-2" title={`${sub}: annual rainfall`} subtitle="mm, with 10-year rolling mean" rows={o.years}>
              <Legend items={[{ label: 'Annual', color: 'var(--s1)' }, { label: '10-yr rolling mean', color: 'var(--s2)' }]} />
              <ChartBox height={280}>
                <LineChart data={o.years} margin={{ top: 8, right: 16 }}>
                  <CartesianGrid {...GRID} /><XAxis dataKey="year" {...AXIS} interval={9} /><YAxis {...AXIS} width={48} tickFormatter={yCompact} />
                  <Tooltip formatter={(v: number, n) => [`${fmtInt(v)} mm`, n === 'annual' ? 'Annual' : '10-yr mean']} />
                  <Line dataKey="annual" stroke="var(--s1)" strokeWidth={1.5} dot={false} strokeOpacity={0.7} />
                  <Line dataKey="rolling10" stroke="var(--s2)" strokeWidth={2.5} dot={false} />
                </LineChart>
              </ChartBox>
            </ChartCard>
          </div>
        )}</Gate>
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-ink">All sub-divisions</h3>
          <DataTable rows={d.subdivisions} columns={[
            { key: 'subdivision', label: 'Sub-division' }, { key: 'mean_annual_mm', label: 'Mean mm', format: v => fmtInt(v as number) },
            { key: 'cv', label: 'CV', format: v => fmt(v as number, 3) },
            { key: 'trend_mm_per_decade', label: 'Trend mm/decade', format: v => fmtSigned(v as number, 1) },
            { key: 'trend_p', label: 'p', format: v => fmtP(v as number) },
            { key: 'deficient_years_pct', label: 'Deficient yrs', format: v => fmtPct(v as number, 0) },
            { key: 'excess_years_pct', label: 'Excess yrs', format: v => fmtPct(v as number, 0) },
            { key: 'recent_vs_early_pct', label: '1986–2015 vs earlier', format: v => fmtSigned(v as number, 1, '%') },
          ]} />
        </Card>
      </div>
    )}</Gate>
  )
}

// ---------------------------------------------------------------- suicides
interface Farmers { national: { year: number; farmers: number; all_professions: number; share_pct: number }[]; by_state: { state: string; total_2001_2012: number; trend_per_year: number | null; trend_significant: boolean }[]; trend: { slope: number | null; p_value: number | null; significant: boolean }; notes: string[] }
interface Breakdown { categories: { category: string; Male?: number; Female?: number; total: number; share_pct: number }[]; states: string[]; type_codes: string[] }
interface StateTrends { states: { state: string; total_2001: number; total_2012: number; change_pct: number | null; trend_per_year: number | null; trend_p: number | null; trend_significant: boolean }[] }
interface Recon { rows: Record<string, unknown>[]; state_years: number; diverging: number; mean_gap_pct: number; notes: string[] }

function SuicidesDeep() {
  const farmers = useApi<Farmers>('/api/policy/suicides/farmers')
  const [typeCode, setTypeCode] = useState('Causes')
  const [state, setState] = useState('All')
  const [year, setYear] = useState('All')
  const br = useApi<Breakdown>(`/api/policy/suicides/breakdown?type_code=${typeCode}&state=${encodeURIComponent(state)}&year=${year}`)
  const trends = useApi<StateTrends>('/api/policy/suicides/state-trends')
  const recon = useApi<Recon>('/api/policy/suicides/reconciliation')
  const years = ['All', ...Array.from({ length: 12 }, (_, i) => String(2001 + i))]
  return (
    <div className="space-y-5">
      <Gate state={farmers}>{d => (
        <div className="grid gap-5 lg:grid-cols-2">
          <ChartCard title="Suicides recorded among farmers / agricultural workers" subtitle={`Trend ${fmtSigned(d.trend.slope, 0)} per year, p = ${fmtP(d.trend.p_value)}`} rows={d.national} notes={d.notes}>
            <ChartBox height={240}>
              <LineChart data={d.national} margin={{ top: 8, right: 16 }}>
                <CartesianGrid {...GRID} /><XAxis dataKey="year" {...AXIS} /><YAxis {...AXIS} width={52} tickFormatter={yCompact} domain={[0, 'auto']} />
                <Tooltip formatter={(v: number) => [fmtInt(v), 'Farmers']} />
                <Line dataKey="farmers" stroke="var(--s1)" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ChartBox>
          </ChartCard>
          <ChartCard title="Farmers' share of all recorded suicides" subtitle="% within the profession breakdown" rows={d.national}>
            <ChartBox height={240}>
              <LineChart data={d.national} margin={{ top: 8, right: 16 }}>
                <CartesianGrid {...GRID} /><XAxis dataKey="year" {...AXIS} /><YAxis {...AXIS} width={44} unit="%" domain={[0, 'auto']} />
                <Tooltip formatter={(v: number) => [`${fmt(v, 1)}%`, 'Share']} />
                <Line dataKey="share_pct" stroke="var(--s1)" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ChartBox>
          </ChartCard>
        </div>
      )}</Gate>

      <FilterBar>
        <Field label="Breakdown"><Select value={typeCode} onChange={setTypeCode} options={(br.data?.type_codes ?? [typeCode]).map(t => ({ value: t, label: t.replace('_', ' ') }))} className="min-w-48" /></Field>
        <Field label="State"><Select value={state} onChange={setState} options={['All', ...(br.data?.states ?? [])]} className="min-w-48" /></Field>
        <Field label="Year"><Select value={year} onChange={setYear} options={years} /></Field>
      </FilterBar>
      <Gate state={br}>{d => (
        <ChartCard title={`${typeCode.replace('_', ' ')}: top categories by gender`} subtitle={`${state === 'All' ? 'All states' : state}, ${year === 'All' ? '2001–2012' : year}`} rows={d.categories}>
          <Legend items={[{ label: 'Male', color: 'var(--s1)' }, { label: 'Female', color: 'var(--s2)' }]} />
          <ChartBox height={Math.max(260, Math.min(d.categories.length, 15) * 24)}>
            <BarChart data={d.categories.slice(0, 15)} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={3}>
              <CartesianGrid {...GRID} horizontal={false} vertical />
              <XAxis type="number" {...AXIS} tickFormatter={yCompact} />
              <YAxis type="category" dataKey="category" {...AXIS} width={220} interval={0} tickFormatter={(v: string) => v.length > 34 ? v.slice(0, 33) + '…' : v} />
              <Tooltip formatter={(v: number, n) => [fmtInt(v), n]} />
              <Bar dataKey="Male" stackId="g" fill="var(--s1)" stroke="var(--surface)" strokeWidth={1} />
              <Bar dataKey="Female" stackId="g" fill="var(--s2)" radius={HBAR_RADIUS} stroke="var(--surface)" strokeWidth={1} />
            </BarChart>
          </ChartBox>
        </ChartCard>
      )}</Gate>

      <div className="grid gap-5 lg:grid-cols-2">
        <Gate state={trends}>{d => (
          <Card>
            <h3 className="mb-3 text-sm font-semibold text-ink">State trends, 2001 → 2012</h3>
            <DataTable rows={d.states} columns={[
              { key: 'state', label: 'State' }, { key: 'total_2001', label: '2001' }, { key: 'total_2012', label: '2012' },
              { key: 'change_pct', label: 'Change', format: v => fmtSigned(v as number, 0, '%') },
              { key: 'trend_per_year', label: 'Trend/yr', format: v => fmtSigned(v as number, 0) },
              { key: 'trend_significant', label: 'p<0.05', format: v => (v ? 'yes' : 'no') },
            ]} />
          </Card>
        )}</Gate>
        <Gate state={recon}>{d => (
          <Card>
            <h3 className="text-sm font-semibold text-ink">Data reconciliation across breakdowns</h3>
            <p className="mt-1 mb-3 text-xs text-ink-2">{d.diverging} of {d.state_years} state-years have breakdowns that do not add up to the same total (mean gap {fmt(d.mean_gap_pct, 2)}%).</p>
            <DataTable rows={d.rows} maxHeight={300} columns={[
              { key: 'state', label: 'State' }, { key: 'year', label: 'Year' },
              { key: 'Means_adopted', label: 'Means' }, { key: 'Causes', label: 'Causes' }, { key: 'Professional_Profile', label: 'Profession' },
              { key: 'gap_pct', label: 'Gap %', format: v => fmt(v as number, 1) },
            ]} />
            <Notes notes={d.notes} />
          </Card>
        )}</Gate>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- diabetes
interface Risk { odds_ratios: { factor: string; odds_ratio: number; ci95: [number, number]; exposed_n: number; exposed_prev_pct: number; reference_prev_pct: number }[]; age_bmi: { age_band: string; bmi_class: string; n: number; prevalence_pct: number }[]; notes: string[] }
const AGES = ['<18', '18-29', '30-44', '45-59', '60-74', '75+']
const BMIS = ['Underweight', 'Normal', 'Overweight', 'Obese']
const SEQ = ['var(--seq-1)', 'var(--seq-2)', 'var(--seq-3)', 'var(--seq-4)', 'var(--seq-5)', 'var(--seq-6)', 'var(--seq-7)']
const BINS = [2, 5, 10, 15, 20, 30]

function DiabetesRisk() {
  const s = useApi<Risk>('/api/policy/diabetes/risk-factors')
  return <Gate state={s}>{d => {
    const forest = d.odds_ratios.map(r => ({ ...r, y: r.factor, err: [r.odds_ratio - r.ci95[0], r.ci95[1] - r.odds_ratio] }))
    const bin = (v: number) => BINS.findIndex(b => v < b) === -1 ? 6 : BINS.findIndex(b => v < b)
    return (
      <div className="space-y-5">
        <ChartCard title="Odds ratios for diabetes (unadjusted), with 95% CI" subtitle="Log scale. 1 = no association; right of 1 = higher odds" rows={d.odds_ratios.map(r => ({ ...r, ci95: r.ci95.map(x => x.toFixed(2)).join('–') }))} notes={d.notes}>
          <ChartBox height={340}>
            <ScatterChart margin={{ left: 8, right: 24, top: 8 }}>
              <CartesianGrid {...GRID} vertical horizontal={false} />
              <XAxis type="number" dataKey="odds_ratio" scale="log" domain={[0.5, 50]} {...AXIS} ticks={[0.5, 1, 2, 5, 10, 20, 50]} />
              <YAxis type="category" dataKey="y" {...AXIS} width={190} interval={0} />
              <ZAxis range={[80, 80]} />
              <ReferenceLine x={1} stroke="var(--ink-2)" />
              <Tooltip content={({ payload }) => {
                const r = payload?.[0]?.payload as Risk['odds_ratios'][0] | undefined
                if (!r) return null
                return <div className="recharts-default-tooltip p-2"><b>{r.factor}</b><br />OR {fmt(r.odds_ratio, 2)} (95% CI {fmt(r.ci95[0], 2)}–{fmt(r.ci95[1], 2)})<br />Prevalence {fmt(r.exposed_prev_pct, 1)}% vs {fmt(r.reference_prev_pct, 1)}%<br />n exposed = {fmtInt(r.exposed_n)}</div>
              }} />
              <Scatter data={forest} fill="var(--s1)" stroke="var(--surface)" strokeWidth={2}>
                <ErrorBar dataKey="err" direction="x" width={6} strokeWidth={1.5} stroke="var(--ink-2)" />
              </Scatter>
            </ScatterChart>
          </ChartBox>
        </ChartCard>
        <ChartCard title="Prevalence by age and BMI" subtitle="% with diabetes; darker = higher. Small cells are less reliable (see n)" rows={d.age_bmi}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] border-separate border-spacing-[2px] text-xs">
              <thead><tr><th className="p-2 text-left font-medium text-muted">Age \ BMI</th>{BMIS.map(b => <th key={b} className="p-2 font-medium text-ink-2">{b}</th>)}</tr></thead>
              <tbody>
                {AGES.map(a => (
                  <tr key={a}>
                    <td className="p-2 font-medium text-ink-2">{a}</td>
                    {BMIS.map(b => {
                      const c = d.age_bmi.find(x => x.age_band === a && x.bmi_class === b)
                      if (!c) return <td key={b} className="rounded bg-surface-2 p-2 text-center text-muted">—</td>
                      const i = bin(c.prevalence_pct)
                      return (
                        <td key={b} title={`${a}, ${b}: ${fmt(c.prevalence_pct, 1)}% (n=${c.n})`} className="rounded p-2 text-center"
                          style={{ background: SEQ[i], color: i >= 4 ? '#fff' : 'var(--ink)' }}>
                          <div className="font-semibold tabular">{fmt(c.prevalence_pct, 1)}%</div>
                          <div className="text-[10px] opacity-80">n={fmtInt(c.n)}</div>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-2 flex items-center gap-1 text-[11px] text-muted">
            <span>Prevalence:</span>{SEQ.map((c, i) => <span key={c} className="inline-flex items-center gap-1"><span className="inline-block h-3 w-5 rounded-sm" style={{ background: c }} />{i === 0 ? `<${BINS[0]}%` : i === 6 ? `≥${BINS[5]}%` : `${BINS[i - 1]}–${BINS[i]}`}</span>)}
          </div>
        </ChartCard>
      </div>
    )
  }}</Gate>
}

// ---------------------------------------------------------------- weather extremes
interface Extremes { yearly: { city: string; year: number; heat_days: number; heavy_rain_days: number; annual_rain_mm: number; mean_tmax: number }[]; summary: { city: string; avg_heat_days: number; avg_heavy_rain_days: number; heat_days_trend_per_decade: number | null; heat_trend_significant: boolean; tmax_trend_c_per_decade: number | null; tmax_trend_significant: boolean; rain_trend_mm_per_decade: number | null; rain_trend_significant: boolean }[]; notes: string[] }

function WeatherExtremes() {
  const s = useApi<Extremes>('/api/policy/weather/extremes')
  const [city, setCity] = useState('Delhi')
  return <Gate state={s}>{d => {
    const rows = d.yearly.filter(y => y.city === city)
    return (
      <div className="space-y-5">
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-ink">City comparison, 2000–2024</h3>
          <DataTable rows={d.summary} columns={[
            { key: 'city', label: 'City' }, { key: 'avg_heat_days', label: 'Heat days/yr (≥40°C)', format: v => fmt(v as number, 1) },
            { key: 'heat_days_trend_per_decade', label: 'Heat-day trend /decade', format: v => fmtSigned(v as number, 1) },
            { key: 'heat_trend_significant', label: 'sig.', format: v => (v ? 'yes' : 'no') },
            { key: 'tmax_trend_c_per_decade', label: 'Mean max trend °C/decade', format: v => fmtSigned(v as number, 2) },
            { key: 'tmax_trend_significant', label: 'sig.', format: v => (v ? 'yes' : 'no') },
            { key: 'avg_heavy_rain_days', label: 'Heavy-rain days/yr', format: v => fmt(v as number, 1) },
            { key: 'rain_trend_mm_per_decade', label: 'Rain trend mm/decade', format: v => fmtSigned(v as number, 0) },
          ]} />
          <Notes notes={d.notes} />
        </Card>
        <FilterBar><Field label="City"><Select value={city} onChange={setCity} options={d.summary.map(x => x.city)} className="min-w-44" /></Field></FilterBar>
        <div className="grid gap-5 lg:grid-cols-2">
          <ChartCard title={`${city}: heat days per year`} subtitle="Days with maximum ≥ 40 °C" rows={rows}>
            <ChartBox height={240}>
              <BarChart data={rows} margin={{ top: 8, right: 8 }} barCategoryGap={2}>
                <CartesianGrid {...GRID} /><XAxis dataKey="year" {...AXIS} /><YAxis {...AXIS} width={36} allowDecimals={false} />
                <Tooltip formatter={(v: number) => [v, 'Heat days']} />
                <Bar dataKey="heat_days" fill="var(--s2)" radius={BAR_RADIUS} />
              </BarChart>
            </ChartBox>
          </ChartCard>
          <ChartCard title={`${city}: heavy-rain days per year`} subtitle="Days with ≥ 64.5 mm rain" rows={rows}>
            <ChartBox height={240}>
              <BarChart data={rows} margin={{ top: 8, right: 8 }} barCategoryGap={2}>
                <CartesianGrid {...GRID} /><XAxis dataKey="year" {...AXIS} /><YAxis {...AXIS} width={36} allowDecimals={false} />
                <Tooltip formatter={(v: number) => [v, 'Heavy-rain days']} />
                <Bar dataKey="heavy_rain_days" fill="var(--s1)" radius={BAR_RADIUS} />
              </BarChart>
            </ChartBox>
          </ChartCard>
        </div>
      </div>
    )
  }}</Gate>
}
