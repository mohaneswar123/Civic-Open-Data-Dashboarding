import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from 'recharts'
import { CloudRain, Lock, Sparkles } from 'lucide-react'
import { Badge, Button, Card, ChartCard, ErrorBox, Field, Gate, Input, PageHeader, Select, StatTile, Tabs, Warning } from '../components/ui'
import { AXIS, BAR_RADIUS, ChartBox, GRID, HBAR_RADIUS, Legend } from '../components/charts'
import { post } from '../lib/api'
import { hasRole, useAuth } from '../lib/auth'
import { useApi, useLocalState } from '../lib/hooks'
import { fmt, fmtInt, fmtPct, fmtSigned } from '../lib/format'

interface Options {
  crop: { last_data_year: number; districts: Record<string, string[]>; crop_seasons: Record<string, string[]>; crops: string[]; seasons: string[] }
  suicides: { states: string[]; genders: string[]; age_groups: string[]; years: [number, number]; last_data_year: number }
  diabetes: { genders: string[]; smoking: string[] }
  weather: { cities: { city: string; first_date: string; last_date: string }[]; max_date: string; max_ml_horizon: number }
}

type Tab = 'crop' | 'weather' | 'diabetes' | 'suicides'
const TABS: { id: Tab; label: string }[] = [
  { id: 'crop', label: 'Crop yield' }, { id: 'weather', label: 'Weather forecast' },
  { id: 'diabetes', label: 'Diabetes risk' }, { id: 'suicides', label: 'Suicide count forecast' },
]

export default function Predictions() {
  const [tab, setTab] = useLocalState<Tab>('civic.pred.tab', 'crop')
  const opts = useApi<Options>('/api/predict/options')
  const { user } = useAuth()
  const detailed = hasRole(user, 'policy')
  return (
    <div>
      <PageHeader title="Predictions" subtitle="Machine-learning models trained on the public datasets. Every model was tested on data it never saw, and compared against a simple baseline." >
        {!detailed && <Link to="/login" className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs text-ink-2 hover:bg-surface-2"><Lock size={13} /> Policy makers: sign in for intervals, scenarios & explanations</Link>}
      </PageHeader>
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      <Gate state={opts}>{o => (
        <>
          {tab === 'crop' && <CropForm o={o} detailed={detailed} />}
          {tab === 'weather' && <WeatherForm o={o} detailed={detailed} />}
          {tab === 'diabetes' && <DiabetesForm o={o} detailed={detailed} />}
          {tab === 'suicides' && <SuicideForm o={o} detailed={detailed} />}
        </>
      )}</Gate>
    </div>
  )
}

function useSubmit<T>() {
  const [result, setResult] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async (path: string, body: unknown) => {
    setBusy(true); setError(null)
    try { setResult(await post<T>(path, body)) } catch (e) { setError((e as Error).message); setResult(null) } finally { setBusy(false) }
  }
  return { result, error, busy, run }
}

function FormLayout({ form, result, onSubmit, busy, error }: { form: ReactNode; result: ReactNode; onSubmit: () => void; busy: boolean; error: string | null }) {
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <Card className="h-fit">
        <form onSubmit={e => { e.preventDefault(); onSubmit() }} className="space-y-3">
          {form}
          <Button type="submit" disabled={busy} className="w-full"><Sparkles size={15} /> {busy ? 'Predicting…' : 'Predict'}</Button>
        </form>
      </Card>
      <div className="space-y-5 lg:col-span-2">
        {error && <ErrorBox message={error} />}
        {result ?? (!error && <Card className="text-sm text-muted">Fill in the form and press <b>Predict</b>.</Card>)}
      </div>
    </div>
  )
}

const UpgradeHint = () => (
  <p className="text-xs text-muted">Policy makers see the uncertainty range, scenario analysis and an explanation of the prediction. <Link to="/login" className="text-accent">Sign in</Link></p>
)

// ---------------------------------------------------------------- crop
interface CropResult {
  yield_t_per_ha: number; production_t: number; warnings: string[]
  forecast: { years_beyond_data: number; last_data_year: number; trend_applied_pct_per_year: number }
  rainfall_used: { normal_monsoon_mm: number | null; scenario_monsoon_mm: number | null }
  interval_80?: [number, number]; production_interval_80?: [number, number]; interval_coverage_on_test?: number
  history?: { year: number; yield: number }[]; scenarios?: { rainfall_change_pct: number; yield_t_per_ha: number }[]
  top_features?: { feature: string; importance: number }[]
  rainfall_finding?: { conclusion: string; rmse_improvement_log: number }
}

function CropForm({ o, detailed }: { o: Options; detailed: boolean }) {
  const states = Object.keys(o.crop.districts).sort()
  const [state, setState] = useState('Punjab')
  const [district, setDistrict] = useState(o.crop.districts['Punjab']?.[0] ?? '')
  const [crop, setCrop] = useState('Wheat')
  const [season, setSeason] = useState('Rabi')
  const [area, setArea] = useState('1000')
  const [year, setYear] = useState('2018')
  const [rain, setRain] = useState('0')
  const districts = o.crop.districts[state] ?? []
  useEffect(() => { if (!districts.includes(district)) setDistrict(districts[0] ?? '') }, [state]) // eslint-disable-line react-hooks/exhaustive-deps
  const seasons = o.crop.crop_seasons[crop] ?? o.crop.seasons
  useEffect(() => { if (!seasons.includes(season)) setSeason(seasons[0]) }, [crop]) // eslint-disable-line react-hooks/exhaustive-deps
  const s = useSubmit<CropResult>()
  const submit = () => s.run('/api/predict/crop', { state, district, crop, season, area_ha: Number(area), year: Number(year), rainfall_change_pct: Number(rain) })
  const r = s.result
  return (
    <FormLayout busy={s.busy} error={s.error} onSubmit={submit}
      form={<>
        <Field label="State"><Select value={state} onChange={setState} options={states} /></Field>
        <Field label="District"><Select value={district} onChange={setDistrict} options={districts} /></Field>
        <Field label="Crop"><Select value={crop} onChange={setCrop} options={o.crop.crops} /></Field>
        <Field label="Season" hint="Seasons in which this crop was recorded"><Select value={season} onChange={setSeason} options={seasons} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Area (hectares)"><Input type="number" min={1} value={area} onChange={e => setArea(e.target.value)} /></Field>
          <Field label="Year" hint={`Data ends ${o.crop.last_data_year}; later years are forecasts`}><Input type="number" min={1997} max={2030} value={year} onChange={e => setYear(e.target.value)} /></Field>
        </div>
        <Field label={`Monsoon rainfall vs normal: ${fmtSigned(Number(rain), 0, '%')}`} hint="0% = a normal year; -20% = drought-like">
          <input type="range" min={-50} max={50} step={5} value={rain} onChange={e => setRain(e.target.value)} className="w-full accent-[var(--accent)]" />
        </Field>
      </>}
      result={r && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatTile label={r.forecast.years_beyond_data ? `Forecast yield (${r.forecast.years_beyond_data} yr ahead)` : 'Predicted yield'} value={`${fmt(r.yield_t_per_ha)} t/ha`} hint={r.interval_80 ? `80% range ${fmt(r.interval_80[0])}–${fmt(r.interval_80[1])}` : undefined} />
            <StatTile label="Predicted production" value={`${fmtInt(r.production_t)} t`} hint={r.production_interval_80 ? `${fmtInt(r.production_interval_80[0])}–${fmtInt(r.production_interval_80[1])} t` : `for ${fmtInt(Number(area))} ha`} />
            <StatTile label="Monsoon rainfall used" value={r.rainfall_used.scenario_monsoon_mm != null ? `${fmtInt(r.rainfall_used.scenario_monsoon_mm)} mm` : '—'} hint={r.rainfall_used.normal_monsoon_mm != null ? `state normal ${fmtInt(r.rainfall_used.normal_monsoon_mm)} mm` : undefined} />
          </div>
          {r.warnings.map(w => <Warning key={w}>{w}</Warning>)}
          {!detailed && <UpgradeHint />}
          {r.interval_coverage_on_test != null && (
            <Warning>Honesty note: the "80% range" contained the true value in {fmtPct(100 * r.interval_coverage_on_test, 0)} of test cases (2011–2015), so treat it as optimistic. {r.rainfall_finding?.conclusion}.</Warning>
          )}
          {r.scenarios && (
            <div className="grid gap-5 lg:grid-cols-2">
              <ChartCard title="What-if: monsoon rainfall scenarios" subtitle="Predicted yield (t/ha) as monsoon rainfall changes; dot = your scenario. Axis does not start at 0" rows={r.scenarios}>
                <ChartBox height={240}>
                  <LineChart data={r.scenarios} margin={{ top: 8, right: 16 }}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="rainfall_change_pct" {...AXIS} tickFormatter={v => `${v > 0 ? '+' : ''}${v}%`} />
                    <YAxis {...AXIS} width={44} domain={['auto', 'auto']} tickFormatter={v => fmt(v, 2)} />
                    <Tooltip formatter={(v: number) => [`${fmt(v)} t/ha`, 'Yield']} labelFormatter={v => `Rainfall ${v > 0 ? '+' : ''}${v}%`} />
                    <ReferenceLine x={Math.round(Number(rain) / 10) * 10} stroke="var(--axis)" />
                    <Line dataKey="yield_t_per_ha" stroke="var(--s1)" strokeWidth={2}
                      dot={(props: { cx?: number; cy?: number; payload?: { rainfall_change_pct: number } }) => (
                        <circle key={props.payload?.rainfall_change_pct} cx={props.cx} cy={props.cy} r={props.payload?.rainfall_change_pct === Math.round(Number(rain) / 10) * 10 ? 6 : 3}
                          fill={props.payload?.rainfall_change_pct === Math.round(Number(rain) / 10) * 10 ? 'var(--s2)' : 'var(--s1)'} stroke="var(--surface)" strokeWidth={2} />
                      )} />
                  </LineChart>
                </ChartBox>
                <p className="mt-2 text-xs text-ink-2">Range across scenarios: {fmt(Math.min(...r.scenarios.map(x => x.yield_t_per_ha)))}–{fmt(Math.max(...r.scenarios.map(x => x.yield_t_per_ha)))} t/ha
                  ({fmtPct(100 * (Math.max(...r.scenarios.map(x => x.yield_t_per_ha)) / Math.min(...r.scenarios.map(x => x.yield_t_per_ha)) - 1), 1)} spread). A small spread means the model finds this crop insensitive to rainfall.</p>
              </ChartCard>
              <ChartCard title="Recorded yield history for this district" subtitle="t/ha, dashed line = prediction" rows={r.history}>
                {r.history && r.history.length ? (
                  <ChartBox height={240}>
                    <LineChart data={r.history} margin={{ top: 8, right: 16 }}>
                      <CartesianGrid {...GRID} /><XAxis dataKey="year" {...AXIS} /><YAxis {...AXIS} width={40} domain={[0, 'auto']} />
                      <ReferenceLine y={r.yield_t_per_ha} stroke="var(--s2)" strokeDasharray="5 4" />
                      <Tooltip formatter={(v: number) => [`${fmt(v)} t/ha`, 'Recorded']} />
                      <Line dataKey="yield" stroke="var(--s1)" strokeWidth={2} dot={{ r: 3 }} />
                    </LineChart>
                  </ChartBox>
                ) : <p className="text-sm text-muted">No history for this exact combination.</p>}
              </ChartCard>
            </div>
          )}
          {r.top_features && <Importance rows={r.top_features} />}
        </>
      )} />
  )
}

function Importance({ rows, title = 'What the model relies on (global feature importance)' }: { rows: { feature: string; importance: number }[]; title?: string }) {
  return (
    <ChartCard title={title} subtitle="Share of total gain" rows={rows}>
      <ChartBox height={Math.max(160, rows.length * 26)}>
        <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={3}>
          <CartesianGrid {...GRID} horizontal={false} vertical />
          <XAxis type="number" {...AXIS} tickFormatter={v => `${Math.round(v * 100)}%`} />
          <YAxis type="category" dataKey="feature" {...AXIS} width={150} interval={0} />
          <Tooltip formatter={(v: number) => [`${fmt(100 * v, 1)}%`, 'Importance']} />
          <Bar dataKey="importance" fill="var(--s1)" radius={HBAR_RADIUS} />
        </BarChart>
      </ChartBox>
    </ChartCard>
  )
}

// ---------------------------------------------------------------- weather
interface WxResult {
  city: string; for_date: string; last_data_date: string; days_beyond_data: number
  mode: 'ml_forecast' | 'climate_outlook'; lead_days: number; based_on?: string; explanation: string
  tmax: number; rain_probability: number; rain_expected: boolean
  observed_on_base_day?: { tmax: number; tmin: number; precip_mm: number }; actual: { tmax: number; rain: boolean } | null
  tmax_band_80?: [number, number]; rain_threshold?: number; warming_adjustment_c?: number; trend_c_per_decade?: number
  climatology?: { tmax: number; rain_probability: number }
  recent?: { date: string; tmax: number; precip: number }[]
  path?: { date: string; lead_days: number; tmax: number; rain_probability: number }[]
  outlook_window?: { date: string; tmax: number; rain_probability: number }[]
}

const addDays = (iso: string, n: number) => { const d = new Date(iso.slice(0, 10) + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10) }

function WeatherForm({ o, detailed }: { o: Options; detailed: boolean }) {
  const [city, setCity] = useState('Mumbai')
  const meta = o.weather.cities.find(c => c.city === city)
  const last = meta?.last_date.slice(0, 10) ?? '2024-12-31'
  const [date, setDate] = useState(() => addDays(last, 1))
  const s = useSubmit<WxResult>()
  const r = s.result
  const quick = [
    { label: 'Past day (check vs actual)', value: '2024-07-10' },
    { label: 'Next day after data', value: addDays(last, 1) },
    { label: `${o.weather.max_ml_horizon} days after data`, value: addDays(last, o.weather.max_ml_horizon) },
    { label: 'Tomorrow (real calendar)', value: addDays(new Date().toISOString(), 1) },
  ]
  return (
    <FormLayout busy={s.busy} error={s.error} onSubmit={() => s.run('/api/predict/weather', { city, date })}
      form={<>
        <Field label="City"><Select value={city} onChange={setCity} options={o.weather.cities.map(c => c.city)} /></Field>
        <Field label="Date to predict" hint={`Observations end ${last}. Up to ${o.weather.max_ml_horizon} days later: ML forecast. Further ahead: climate outlook.`}>
          <Input type="date" value={date} onChange={e => setDate(e.target.value)} min={addDays(meta?.first_date ?? '2000-01-01', 8)} max={o.weather.max_date} />
        </Field>
        <div className="flex flex-wrap gap-1.5">
          {quick.map(q => <button key={q.label} type="button" onClick={() => setDate(q.value)}
            className={`rounded-full border px-2.5 py-1 text-[11px] ${date === q.value ? 'border-accent bg-accent/10 text-accent' : 'border-line text-ink-2 hover:bg-surface-2'}`}>{q.label}</button>)}
        </div>
      </>}
      result={r && (
        <>
          <Card className="!p-4">
            <div className="flex flex-wrap items-center gap-2">
              {r.mode === 'ml_forecast'
                ? <Badge tone="accent">ML forecast · {r.lead_days}-day lead</Badge>
                : <Badge tone="warning">Climate outlook · {fmtInt(r.lead_days)} days beyond data</Badge>}
              {r.actual && <Badge tone="good">verifiable: actual value known</Badge>}
            </div>
            <p className="mt-2 text-xs text-ink-2">{r.explanation}</p>
          </Card>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatTile label={`Max temperature on ${r.for_date}`} value={`${fmt(r.tmax, 1)} °C`}
              hint={r.tmax_band_80 ? `80% range ${fmt(r.tmax_band_80[0], 1)}–${fmt(r.tmax_band_80[1], 1)} °C` : r.mode === 'climate_outlook' ? 'typical value' : undefined} />
            <StatTile label={r.mode === 'climate_outlook' ? 'Historical chance of a rainy day' : 'Chance of rain (≥ 2.5 mm)'} value={fmtPct(100 * r.rain_probability, 0)}
              hint={<span className="inline-flex items-center gap-1"><CloudRain size={13} /> {r.mode === 'climate_outlook' ? 'share of past years with rain on this date' : r.rain_expected ? 'Rain expected' : 'No rain expected'}</span>} />
            <StatTile label="What actually happened" value={r.actual ? `${fmt(r.actual.tmax, 1)} °C` : 'Not yet known'}
              hint={r.actual ? `${r.actual.rain ? 'it rained' : 'no rain'} · error ${fmtSigned(r.tmax - r.actual.tmax, 1)} °C` : `date is after the last observation (${r.last_data_date})`} />
          </div>
          {!detailed && <UpgradeHint />}
          {r.mode === 'climate_outlook' && r.warming_adjustment_c != null && detailed && (
            <Warning>Includes a warming adjustment of {fmtSigned(r.warming_adjustment_c, 2)} °C (city trend {fmtSigned(r.trend_c_per_decade, 2)} °C per decade, 2000–2024). This describes typical conditions, not the actual weather on that day.</Warning>
          )}
          {r.path && (
            <ChartCard title={`${o.weather.max_ml_horizon}-day forecast from the last observation (${r.last_data_date})`} subtitle="Error grows with lead time. Dot = the date you picked" rows={r.path}>
              <div className="grid gap-4 lg:grid-cols-2">
                <ChartBox height={220}>
                  <LineChart data={r.path} margin={{ top: 8, right: 16 }}>
                    <CartesianGrid {...GRID} /><XAxis dataKey="date" {...AXIS} tickFormatter={d => d.slice(5)} /><YAxis {...AXIS} width={40} domain={['auto', 'auto']} unit="°" />
                    <Tooltip formatter={(v: number) => [`${fmt(v, 1)} °C`, 'Max temp']} />
                    <Line dataKey="tmax" stroke="var(--s2)" strokeWidth={2}
                      dot={(p: { cx?: number; cy?: number; payload?: { date: string } }) => <circle key={p.payload?.date} cx={p.cx} cy={p.cy} r={p.payload?.date === r.for_date ? 6 : 3} fill="var(--s2)" stroke="var(--surface)" strokeWidth={2} />} />
                  </LineChart>
                </ChartBox>
                <ChartBox height={220}>
                  <BarChart data={r.path} margin={{ top: 8, right: 8 }} barCategoryGap={4}>
                    <CartesianGrid {...GRID} /><XAxis dataKey="date" {...AXIS} tickFormatter={d => d.slice(5)} /><YAxis {...AXIS} width={40} domain={[0, 1]} tickFormatter={v => `${Math.round(v * 100)}%`} />
                    <Tooltip formatter={(v: number) => [fmtPct(100 * v, 0), 'Chance of rain']} />
                    <Bar dataKey="rain_probability" radius={BAR_RADIUS}>{r.path.map(x => <Cell key={x.date} fill="var(--s1)" fillOpacity={x.date === r.for_date ? 1 : 0.55} />)}</Bar>
                  </BarChart>
                </ChartBox>
              </div>
            </ChartCard>
          )}
          {r.outlook_window && (
            <ChartCard title="Climate outlook around the chosen date" subtitle="Typical max temperature (°C) and historical rainy-day chance, ±15 days" rows={r.outlook_window}>
              <div className="grid gap-4 lg:grid-cols-2">
                <ChartBox height={220}>
                  <LineChart data={r.outlook_window} margin={{ top: 8, right: 16 }}>
                    <CartesianGrid {...GRID} /><XAxis dataKey="date" {...AXIS} tickFormatter={d => d.slice(5)} interval={6} /><YAxis {...AXIS} width={40} domain={['auto', 'auto']} unit="°" />
                    <ReferenceLine x={r.for_date} stroke="var(--axis)" />
                    <Tooltip formatter={(v: number) => [`${fmt(v, 1)} °C`, 'Typical max']} />
                    <Line dataKey="tmax" stroke="var(--s2)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ChartBox>
                <ChartBox height={220}>
                  <LineChart data={r.outlook_window} margin={{ top: 8, right: 16 }}>
                    <CartesianGrid {...GRID} /><XAxis dataKey="date" {...AXIS} tickFormatter={d => d.slice(5)} interval={6} /><YAxis {...AXIS} width={40} domain={[0, 1]} tickFormatter={v => `${Math.round(v * 100)}%`} />
                    <ReferenceLine x={r.for_date} stroke="var(--axis)" />
                    <Tooltip formatter={(v: number) => [fmtPct(100 * v, 0), 'Rainy-day chance']} />
                    <Line dataKey="rain_probability" stroke="var(--s1)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ChartBox>
              </div>
            </ChartCard>
          )}
          {r.recent && r.mode === 'ml_forecast' && (
            <ChartCard title={`Observed before the forecast (up to ${r.based_on})`} subtitle="Max temperature °C · these values are the model's input" rows={r.recent}>
              <ChartBox height={200}>
                <LineChart data={r.recent} margin={{ top: 8, right: 16 }}>
                  <CartesianGrid {...GRID} /><XAxis dataKey="date" {...AXIS} tickFormatter={d => d.slice(5)} /><YAxis {...AXIS} width={36} domain={['auto', 'auto']} />
                  <Tooltip formatter={(v: number) => [`${fmt(v, 1)} °C`, 'Max']} />
                  <Line dataKey="tmax" stroke="var(--s2)" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ChartBox>
            </ChartCard>
          )}
        </>
      )} />
  )
}

// ---------------------------------------------------------------- diabetes
interface DiaResult { probability: number; risk_band: string; disclaimer: string; threshold?: number; base_rate?: number; contributions?: { feature: string; value: unknown; contribution: number }[] }
const LABELS: Record<string, string> = { HbA1c_level: 'HbA1c', blood_glucose_level: 'Blood glucose', bmi: 'BMI', age: 'Age', hypertension: 'Hypertension', heart_disease: 'Heart disease', smoking_history: 'Smoking', gender: 'Gender' }

function DiabetesForm({ o, detailed }: { o: Options; detailed: boolean }) {
  const [f, setF] = useState({ gender: 'Female', age: '45', hypertension: '0', heart_disease: '0', smoking_history: 'never', bmi: '27', HbA1c_level: '5.8', blood_glucose_level: '130' })
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v })
  const s = useSubmit<DiaResult>()
  const r = s.result
  const contrib = useMemo(() => r?.contributions?.map(c => ({ ...c, label: `${LABELS[c.feature] ?? c.feature} = ${c.value}` })), [r])
  const tone = r?.risk_band === 'High' ? 'critical' : r?.risk_band === 'Moderate' ? 'warning' : 'good'
  return (
    <FormLayout busy={s.busy} error={s.error}
      onSubmit={() => s.run('/api/predict/diabetes', { ...f, age: +f.age, hypertension: +f.hypertension, heart_disease: +f.heart_disease, bmi: +f.bmi, HbA1c_level: +f.HbA1c_level, blood_glucose_level: +f.blood_glucose_level })}
      form={<>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Gender"><Select value={f.gender} onChange={set('gender')} options={o.diabetes.genders} /></Field>
          <Field label="Age"><Input type="number" min={0} max={120} value={f.age} onChange={e => set('age')(e.target.value)} /></Field>
          <Field label="Hypertension"><Select value={f.hypertension} onChange={set('hypertension')} options={[{ value: '0', label: 'No' }, { value: '1', label: 'Yes' }]} /></Field>
          <Field label="Heart disease"><Select value={f.heart_disease} onChange={set('heart_disease')} options={[{ value: '0', label: 'No' }, { value: '1', label: 'Yes' }]} /></Field>
        </div>
        <Field label="Smoking history"><Select value={f.smoking_history} onChange={set('smoking_history')} options={o.diabetes.smoking} /></Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="BMI"><Input type="number" step="0.1" min={10} max={100} value={f.bmi} onChange={e => set('bmi')(e.target.value)} /></Field>
          <Field label="HbA1c %"><Input type="number" step="0.1" min={3} max={20} value={f.HbA1c_level} onChange={e => set('HbA1c_level')(e.target.value)} /></Field>
          <Field label="Glucose mg/dL"><Input type="number" min={40} max={600} value={f.blood_glucose_level} onChange={e => set('blood_glucose_level')(e.target.value)} /></Field>
        </div>
      </>}
      result={r && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <StatTile label="Estimated probability of diabetes" value={fmtPct(100 * r.probability, 1)} hint={r.base_rate != null ? `dataset average ${fmtPct(100 * r.base_rate, 1)}` : undefined} />
            <StatTile label="Risk band" value={<Badge tone={tone}>{r.risk_band}</Badge>} hint={r.threshold != null ? `"High" from ${fmtPct(100 * r.threshold, 0)} (threshold maximising F1)` : undefined} />
          </div>
          <Warning>{r.disclaimer}</Warning>
          {!detailed && <UpgradeHint />}
          {contrib && (
            <ChartCard title="Why this estimate? (SHAP contributions)" subtitle="Log-odds pushed up (red) or down (blue) by each input, for this person" rows={contrib}>
              <ChartBox height={Math.max(200, contrib.length * 28)}>
                <BarChart data={contrib} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={3}>
                  <CartesianGrid {...GRID} horizontal={false} vertical />
                  <XAxis type="number" {...AXIS} /><YAxis type="category" dataKey="label" {...AXIS} width={170} interval={0} />
                  <ReferenceLine x={0} stroke="var(--ink-2)" />
                  <Tooltip formatter={(v: number) => [fmtSigned(v, 2), 'log-odds']} />
                  <Bar dataKey="contribution" radius={4}>
                    {contrib.map(c => <Cell key={c.feature} fill={c.contribution >= 0 ? 'var(--div-neg)' : 'var(--div-pos)'} />)}
                  </Bar>
                </BarChart>
              </ChartBox>
            </ChartCard>
          )}
        </>
      )} />
  )
}

// ---------------------------------------------------------------- suicides
interface SuiResult {
  forecast: number; method: string; actual: number | null; warnings: string[]; years_beyond_data: number; last_data_year: number
  band_80?: [number, number]; all_methods?: Record<string, number> | null; history?: { year: number; total: number }[]
  path?: { year: number; forecast: number; low: number; high: number }[]; conclusion?: string
}

function SuicideForm({ o, detailed }: { o: Options; detailed: boolean }) {
  const [state, setState] = useState('Maharashtra')
  const [gender, setGender] = useState('Male')
  const [age, setAge] = useState('30-44')
  const [year, setYear] = useState(String(o.suicides.last_data_year + 3))
  const s = useSubmit<SuiResult>()
  const r = s.result
  const years = Array.from({ length: o.suicides.years[1] - o.suicides.years[0] + 1 }, (_, i) => String(o.suicides.years[0] + i))
  const chart = r?.history ? [
    ...r.history.map(h => ({ year: h.year, recorded: h.total })),
    ...(r.path ?? []).map(p => ({ year: p.year, forecast: p.forecast, range: [p.low, p.high] as [number, number] })),
  ] : null
  if (chart && r?.path?.length && r.history?.length) {  // join the forecast line to the last recorded point
    const lastRec = chart.find(c => c.year === r.last_data_year)
    if (lastRec) Object.assign(lastRec, { forecast: (lastRec as { recorded: number }).recorded })
  }
  return (
    <FormLayout busy={s.busy} error={s.error} onSubmit={() => s.run('/api/predict/suicides', { state, gender, age_group: age, year: +year })}
      form={<>
        <Field label="State"><Select value={state} onChange={setState} options={o.suicides.states} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Gender"><Select value={gender} onChange={setGender} options={o.suicides.genders} /></Field>
          <Field label="Age group"><Select value={age} onChange={setAge} options={o.suicides.age_groups} /></Field>
        </div>
        <Field label="Year to forecast" hint={`Data ends ${o.suicides.last_data_year}. Earlier years are back-tests (compared with the recorded value).`}>
          <Select value={year} onChange={setYear} options={years.map(y => ({ value: y, label: +y > o.suicides.last_data_year ? `${y} (forecast)` : `${y} (back-test)` }))} />
        </Field>
      </>}
      result={r && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatTile label={r.years_beyond_data ? `Forecast for ${year} (${r.years_beyond_data} yr ahead)` : `Back-test for ${year}`} value={fmtInt(r.forecast)}
              hint={r.band_80 ? `80% range ${fmtInt(r.band_80[0])}–${fmtInt(r.band_80[1])}` : 'recorded suicides'} />
            <StatTile label="Recorded (actual)" value={r.actual != null ? fmtInt(r.actual) : '—'} hint={r.actual != null ? `error ${fmtSigned(r.forecast - r.actual, 0)}` : 'future year: not yet known'} />
            <StatTile label="Method" value={<span className="text-base">{r.method.replace(/_/g, ' ')}</span>} hint="chosen by validation / rolling back-test" />
          </div>
          {r.warnings.map(w => <Warning key={w}>{w}</Warning>)}
          {!detailed && <UpgradeHint />}
          {r.conclusion && <Card className="text-xs text-ink-2"><b className="text-ink">Honest finding:</b> {r.conclusion} For several years ahead, back-testing found that carrying trends forward did worse than assuming counts stay near recent levels, so the forecast is flat while the uncertainty band widens each year.</Card>}
          {chart && (
            <ChartCard title="Recorded history and forecast" subtitle={r.path?.length ? 'Shaded area = 80% range; it widens with each year ahead' : 'Dashed line = forecast'} rows={chart}>
              <Legend items={[{ label: 'Recorded', color: 'var(--s1)' }, { label: 'Forecast', color: 'var(--s2)', dashed: true }]} />
              <ChartBox height={260}>
                <ComposedChart data={chart} margin={{ top: 8, right: 16 }}>
                  <CartesianGrid {...GRID} /><XAxis dataKey="year" {...AXIS} /><YAxis {...AXIS} width={52} domain={[0, 'auto']} />
                  <Tooltip formatter={(v: number | [number, number], n) => [Array.isArray(v) ? `${fmtInt(v[0])}–${fmtInt(v[1])}` : fmtInt(v), n === 'range' ? '80% range' : n === 'recorded' ? 'Recorded' : 'Forecast']} />
                  <Area dataKey="range" stroke="none" fill="var(--s2)" fillOpacity={0.15} />
                  <Line dataKey="recorded" stroke="var(--s1)" strokeWidth={2} dot={{ r: 3 }} connectNulls={false} />
                  <Line dataKey="forecast" stroke="var(--s2)" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 2 }} />
                  {!r.path?.length && <ReferenceLine y={r.forecast} stroke="var(--s2)" strokeDasharray="5 4" />}
                </ComposedChart>
              </ChartBox>
            </ChartCard>
          )}
          {r.all_methods && (
            <Card>
              <h3 className="mb-2 text-sm font-semibold text-ink">All candidate methods</h3>
              <ul className="space-y-1 text-sm text-ink-2">
                {Object.entries(r.all_methods).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k.replace(/_/g, ' ')} {r.method === k && <Badge tone="accent">selected</Badge>}</span><span className="tabular text-ink">{fmtInt(v)}</span></li>)}
              </ul>
            </Card>
          )}
        </>
      )} />
  )
}
