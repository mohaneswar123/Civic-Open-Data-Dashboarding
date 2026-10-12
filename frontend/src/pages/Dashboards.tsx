import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartCard, FilterBar, Field, Gate, PageHeader, Select, StatTile, Tabs, Notes } from '../components/ui'
import { AXIS, BAR_RADIUS, ChartBox, GRID, HBAR_RADIUS, Legend, yCompact } from '../components/charts'
import { useApi, useLocalState } from '../lib/hooks'
import { fmt, fmtCompact, fmtInt, fmtPct, MONTHS } from '../lib/format'

type Tab = 'crop' | 'rainfall' | 'suicides' | 'diabetes' | 'weather'
const TABS: { id: Tab; label: string }[] = [
  { id: 'crop', label: 'Crop production' }, { id: 'rainfall', label: 'Rainfall' }, { id: 'suicides', label: 'Suicides' },
  { id: 'diabetes', label: 'Diabetes' }, { id: 'weather', label: 'City weather' },
]

export default function Dashboards() {
  const [tab, setTab] = useLocalState<Tab>('civic.dash.tab', 'crop')
  return (
    <div>
      <PageHeader title="Dashboards" subtitle="General trends and regional differences for each dataset. Each chart has a table view, a CSV download and notes on how to read it." />
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      {tab === 'crop' && <Crop />}
      {tab === 'rainfall' && <Rainfall />}
      {tab === 'suicides' && <Suicides />}
      {tab === 'diabetes' && <Diabetes />}
      {tab === 'weather' && <Weather />}
    </div>
  )
}

// ---------------------------------------------------------------- crop
interface CropData {
  yearly: { year: number; production_t: number; area_ha: number; states_reporting: number; complete: boolean }[]
  top_crops: { crop: string; avg_annual_t: number }[]
  states: { state: string; avg_annual_t: number; avg_area_ha: number }[]
  seasons: { season: string; avg_area_ha: number }[]
  max_states: number
  notes: string[]
}

function Crop() {
  const s = useApi<CropData>('/api/public/crop')
  return <Gate state={s}>{d => {
    const complete = d.yearly.filter(y => y.complete)
    const best = complete.reduce((a, b) => (b.production_t > a.production_t ? b : a), complete[0])
    return (
      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Years covered" value={`${d.yearly[0].year}–${d.yearly.at(-1)!.year}`} hint={`${complete.length} years with near-complete state coverage`} />
          <StatTile label="Peak production (complete years)" value={`${fmtCompact(best.production_t)} t`} hint={`in ${best.year}`} />
          <StatTile label="Top crop by tonnage" value={d.top_crops[0].crop} hint={`${fmtCompact(d.top_crops[0].avg_annual_t)} t per year`} />
          <StatTile label="Top state by tonnage" value={d.states[0].state} hint={`${fmtCompact(d.states[0].avg_annual_t)} t per year`} />
        </div>
        <ChartCard title="Total production by year (tonnes)" subtitle={`Faded bars: fewer than 80% of ${d.max_states} states reported, so they are not comparable`}
          rows={d.yearly} notes={d.notes}>
          <ChartBox height={300}>
            <BarChart data={d.yearly} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap={2}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="year" {...AXIS} />
              <YAxis {...AXIS} tickFormatter={yCompact} width={56} />
              <Tooltip formatter={(v: number) => [`${fmtInt(v)} t`, 'Production']}
                labelFormatter={(y) => { const r = d.yearly.find(x => x.year === y); return `${y} · ${r?.states_reporting} states reporting${r?.complete ? '' : ' (incomplete)'}` }} />
              <Bar dataKey="production_t" radius={BAR_RADIUS}>
                {d.yearly.map(y => <Cell key={y.year} fill="var(--s1)" fillOpacity={y.complete ? 1 : 0.28} />)}
              </Bar>
            </BarChart>
          </ChartBox>
        </ChartCard>
        <div className="grid gap-5 lg:grid-cols-2">
          <ChartCard title="Top 10 crops by average annual production" subtitle="Tonnes per year, tonne-measured crops only" rows={d.top_crops}>
            <ChartBox height={320}>
              <BarChart data={d.top_crops} layout="vertical" margin={{ left: 8, right: 16 }} barCategoryGap={3}>
                <CartesianGrid {...GRID} horizontal={false} vertical />
                <XAxis type="number" {...AXIS} tickFormatter={yCompact} />
                <YAxis type="category" dataKey="crop" {...AXIS} width={110} interval={0} />
                <Tooltip formatter={(v: number) => [`${fmtInt(v)} t/yr`, 'Average']} />
                <Bar dataKey="avg_annual_t" fill="var(--s1)" radius={HBAR_RADIUS} />
              </BarChart>
            </ChartBox>
          </ChartCard>
          <ChartCard title="States by average annual production" subtitle="Top 15. Big states produce more partly because they are big; see yield in Advanced analytics" rows={d.states}>
            <ChartBox height={320}>
              <BarChart data={d.states.slice(0, 15)} layout="vertical" margin={{ left: 8, right: 16 }} barCategoryGap={3}>
                <CartesianGrid {...GRID} horizontal={false} vertical />
                <XAxis type="number" {...AXIS} tickFormatter={yCompact} />
                <YAxis type="category" dataKey="state" {...AXIS} width={120} interval={0} />
                <Tooltip formatter={(v: number) => [`${fmtInt(v)} t/yr`, 'Average']} />
                <Bar dataKey="avg_annual_t" fill="var(--s1)" radius={HBAR_RADIUS} />
              </BarChart>
            </ChartBox>
          </ChartCard>
        </div>
        <ChartCard title="Cropped area by season" subtitle="Average hectares per year" rows={d.seasons}>
          <ChartBox height={220}>
            <BarChart data={d.seasons} margin={{ top: 8, right: 8 }} barCategoryGap={8}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="season" {...AXIS} />
              <YAxis {...AXIS} tickFormatter={yCompact} width={56} />
              <Tooltip formatter={(v: number) => [`${fmtInt(v)} ha`, 'Area']} />
              <Bar dataKey="avg_area_ha" fill="var(--s1)" radius={BAR_RADIUS} />
            </BarChart>
          </ChartBox>
        </ChartCard>
      </div>
    )
  }}</Gate>
}

// ---------------------------------------------------------------- rainfall
interface RainData {
  india: { year: number; annual_mm: number; monsoon_mm: number; departure_pct: number }[]
  subdivisions: { subdivision: string; mean_annual_mm: number; mean_monsoon_mm: number }[]
  monthly: { month: string; mm: number }[]
  notes: string[]
}

function Rainfall() {
  const s = useApi<RainData>('/api/public/rainfall')
  return <Gate state={s}>{d => {
    const deficient = d.india.filter(y => y.departure_pct <= -10).length
    const wettest = d.subdivisions[0], driest = d.subdivisions.at(-1)!
    return (
      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Record length" value={`${d.india.length} years`} hint="1901–2015, 36 IMD sub-divisions" />
          <StatTile label="Average monsoon share" value={fmtPct(100 * d.india.reduce((a, b) => a + b.monsoon_mm, 0) / d.india.reduce((a, b) => a + b.annual_mm, 0), 0)} hint="of annual rain falls Jun–Sep" />
          <StatTile label="Wettest sub-division" value={wettest.subdivision} hint={`${fmtInt(wettest.mean_annual_mm)} mm / year`} />
          <StatTile label="Driest sub-division" value={driest.subdivision} hint={`${fmtInt(driest.mean_annual_mm)} mm / year; ${deficient} deficient all-India years overall`} />
        </div>
        <ChartCard title="Rainfall departure from normal, by year" subtitle="Average of sub-divisions, % vs 1961–2010 normal. Blue = wetter, red = drier" rows={d.india} notes={d.notes}>
          <ChartBox height={280}>
            <BarChart data={d.india} margin={{ top: 8, right: 8 }} barCategoryGap={1}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="year" {...AXIS} interval={9} />
              <YAxis {...AXIS} tickFormatter={v => `${v}%`} width={48} />
              <ReferenceLine y={0} stroke="var(--axis)" />
              <Tooltip formatter={(v: number) => [`${fmt(v, 1)}%`, 'Departure']} />
              <Bar dataKey="departure_pct">
                {d.india.map(y => <Cell key={y.year} fill={y.departure_pct >= 0 ? 'var(--div-pos)' : 'var(--div-neg)'} />)}
              </Bar>
            </BarChart>
          </ChartBox>
        </ChartCard>
        <div className="grid gap-5 lg:grid-cols-2">
          <ChartCard title="Average rainfall by month" subtitle="mm, mean across sub-divisions and years" rows={d.monthly}>
            <ChartBox height={260}>
              <BarChart data={d.monthly} margin={{ top: 8, right: 8 }} barCategoryGap={4}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="month" {...AXIS} />
                <YAxis {...AXIS} width={44} />
                <Tooltip formatter={(v: number) => [`${fmt(v, 0)} mm`, 'Rainfall']} />
                <Bar dataKey="mm" fill="var(--s1)" radius={BAR_RADIUS} />
              </BarChart>
            </ChartBox>
          </ChartCard>
          <ChartCard title="Average annual rainfall by sub-division" subtitle="mm per year. Regional disparity is large" rows={d.subdivisions}>
            <ChartBox height={260}>
              <BarChart data={d.subdivisions} margin={{ top: 8, right: 8 }} barCategoryGap={1}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="subdivision" {...AXIS} tick={false} label={{ value: '36 sub-divisions, wettest → driest', fill: 'var(--muted)', fontSize: 12 }} height={24} />
                <YAxis {...AXIS} width={48} tickFormatter={yCompact} />
                <Tooltip formatter={(v: number) => [`${fmtInt(v)} mm`, 'Annual']} />
                <Bar dataKey="mean_annual_mm" fill="var(--s1)" radius={BAR_RADIUS} />
              </BarChart>
            </ChartBox>
          </ChartCard>
        </div>
      </div>
    )
  }}</Gate>
}

// ---------------------------------------------------------------- suicides
interface SuiData {
  yearly: { year: number; total: number; male: number; female: number }[]
  states_2012: { state: string; total: number }[]
  age_groups: { age_group: string; total: number }[]
  notes: string[]
}

function Suicides() {
  const s = useApi<SuiData>('/api/public/suicides')
  return <Gate state={s}>{d => {
    const first = d.yearly[0], last = d.yearly.at(-1)!
    const male = d.yearly.reduce((a, b) => a + b.male, 0), all = d.yearly.reduce((a, b) => a + b.total, 0)
    return (
      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label={`Recorded suicides, ${last.year}`} value={fmtInt(last.total)} hint={`${fmtPct(100 * (last.total / first.total - 1))} vs ${first.year}`} />
          <StatTile label="Male share (2001–2012)" value={fmtPct(100 * male / all)} />
          <StatTile label={`Highest count, ${last.year}`} value={d.states_2012[0].state} hint={`${fmtInt(d.states_2012[0].total)} recorded`} />
          <StatTile label="Most affected age group" value={[...d.age_groups].sort((a, b) => b.total - a.total)[0].age_group} hint="by total count" />
        </div>
        <ChartCard title="Recorded suicides by year and gender" rows={d.yearly} notes={d.notes}>
          <Legend items={[{ label: 'Male', color: 'var(--s1)' }, { label: 'Female', color: 'var(--s2)' }]} />
          <ChartBox height={280}>
            <LineChart data={d.yearly} margin={{ top: 8, right: 16 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="year" {...AXIS} />
              <YAxis {...AXIS} tickFormatter={yCompact} width={52} domain={[0, 'auto']} />
              <Tooltip formatter={(v: number, n) => [fmtInt(v), n === 'male' ? 'Male' : 'Female']} />
              <Line dataKey="male" stroke="var(--s1)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              <Line dataKey="female" stroke="var(--s2)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
            </LineChart>
          </ChartBox>
        </ChartCard>
        <div className="grid gap-5 lg:grid-cols-2">
          <ChartCard title="Recorded suicides by state, 2012" subtitle="Top 15, counts (not population-adjusted)" rows={d.states_2012}>
            <ChartBox height={340}>
              <BarChart data={d.states_2012.slice(0, 15)} layout="vertical" margin={{ left: 8, right: 16 }} barCategoryGap={3}>
                <CartesianGrid {...GRID} horizontal={false} vertical />
                <XAxis type="number" {...AXIS} tickFormatter={yCompact} />
                <YAxis type="category" dataKey="state" {...AXIS} width={110} interval={0} />
                <Tooltip formatter={(v: number) => [fmtInt(v), 'Recorded']} />
                <Bar dataKey="total" fill="var(--s1)" radius={HBAR_RADIUS} />
              </BarChart>
            </ChartBox>
          </ChartCard>
          <ChartCard title="By age group, 2001–2012" rows={d.age_groups}>
            <ChartBox height={340}>
              <BarChart data={d.age_groups} margin={{ top: 8, right: 8 }} barCategoryGap={6}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="age_group" {...AXIS} />
                <YAxis {...AXIS} tickFormatter={yCompact} width={52} />
                <Tooltip formatter={(v: number) => [fmtInt(v), 'Recorded']} />
                <Bar dataKey="total" fill="var(--s1)" radius={BAR_RADIUS} />
              </BarChart>
            </ChartBox>
          </ChartCard>
        </div>
      </div>
    )
  }}</Gate>
}

// ---------------------------------------------------------------- diabetes
interface Prev { grp: string; n: number; prevalence_pct: number }
interface DiaData {
  overall: { records: number; prevalence_pct: number; mean_bmi: number; mean_hba1c: number }
  by_age: Prev[]; by_bmi: Prev[]; by_gender: Prev[]; by_smoking: Prev[]; notes: string[]
}
const AGE_ORDER = ['<18', '18-29', '30-44', '45-59', '60-74', '75+']
const BMI_ORDER = ['Underweight', 'Normal', 'Overweight', 'Obese']

function PrevChart({ title, rows, order }: { title: string; rows: Prev[]; order?: string[] }) {
  const data = order ? order.map(o => rows.find(r => r.grp === o)).filter(Boolean) as Prev[] : rows
  return (
    <ChartCard title={title} subtitle="% of records with diabetes" rows={data}>
      <ChartBox height={220}>
        <BarChart data={data} margin={{ top: 8, right: 8 }} barCategoryGap={6}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="grp" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={v => `${v}%`} width={40} />
          <Tooltip formatter={(v: number, _n, p) => [`${fmt(v, 1)}% (n = ${fmtInt((p.payload as Prev).n)})`, 'Prevalence']} />
          <Bar dataKey="prevalence_pct" fill="var(--s1)" radius={BAR_RADIUS} />
        </BarChart>
      </ChartBox>
    </ChartCard>
  )
}

function Diabetes() {
  const s = useApi<DiaData>('/api/public/diabetes')
  return <Gate state={s}>{d => (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Records (after de-duplication)" value={fmtInt(d.overall.records)} />
        <StatTile label="Diabetes prevalence in sample" value={fmtPct(d.overall.prevalence_pct)} />
        <StatTile label="Mean BMI" value={fmt(d.overall.mean_bmi, 1)} hint="kg/m²" />
        <StatTile label="Mean HbA1c" value={`${fmt(d.overall.mean_hba1c, 2)}%`} hint="6.5% or more indicates diabetes" />
      </div>
      <Notes notes={d.notes} />
      <div className="grid gap-5 lg:grid-cols-2">
        <PrevChart title="Prevalence by age" rows={d.by_age} order={AGE_ORDER} />
        <PrevChart title="Prevalence by BMI class" rows={d.by_bmi} order={BMI_ORDER} />
        <PrevChart title="Prevalence by smoking history" rows={d.by_smoking} />
        <PrevChart title="Prevalence by gender" rows={d.by_gender} />
      </div>
    </div>
  )}</Gate>
}

// ---------------------------------------------------------------- weather
interface WxData {
  cities: string[]; city: string
  monthly: { month: number; tmax: number; tmin: number; rain_mm: number }[]
  yearly: { year: number; mean_tmax: number; rain_mm: number; rainy_days: number }[]
  compare: { city: string; mean_tmax: number; annual_rain_mm: number }[]
  notes: string[]
}

function Weather() {
  const [city, setCity] = useState('Delhi')
  const s = useApi<WxData>(`/api/public/weather?city=${encodeURIComponent(city)}`)
  return (
    <div>
      <FilterBar>
        <Field label="City"><Select value={city} onChange={setCity} options={s.data?.cities ?? [city]} className="min-w-44" /></Field>
      </FilterBar>
      <Gate state={s}>{d => {
        const monthly = d.monthly.map(m => ({ ...m, label: MONTHS[m.month - 1] }))
        const compare = [...d.compare].sort((a, b) => b.annual_rain_mm - a.annual_rain_mm)
        return (
          <div className="space-y-5">
            <div className="grid gap-5 lg:grid-cols-2">
              <ChartCard title={`${d.city}: average daily temperature by month`} subtitle="°C, 2000–2024" rows={monthly} notes={d.notes}>
                <Legend items={[{ label: 'Daily maximum', color: 'var(--s2)' }, { label: 'Daily minimum', color: 'var(--s1)' }]} />
                <ChartBox height={240}>
                  <LineChart data={monthly} margin={{ top: 8, right: 16 }}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="label" {...AXIS} />
                    <YAxis {...AXIS} width={36} unit="°" />
                    <Tooltip formatter={(v: number, n) => [`${fmt(v, 1)} °C`, n === 'tmax' ? 'Max' : 'Min']} />
                    <Line dataKey="tmax" stroke="var(--s2)" strokeWidth={2} dot={{ r: 3 }} />
                    <Line dataKey="tmin" stroke="var(--s1)" strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart>
                </ChartBox>
              </ChartCard>
              <ChartCard title={`${d.city}: average rainfall by month`} subtitle="mm per month" rows={monthly}>
                <ChartBox height={262}>
                  <BarChart data={monthly} margin={{ top: 8, right: 8 }} barCategoryGap={4}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="label" {...AXIS} />
                    <YAxis {...AXIS} width={40} />
                    <Tooltip formatter={(v: number) => [`${fmt(v, 0)} mm`, 'Rain']} />
                    <Bar dataKey="rain_mm" fill="var(--s1)" radius={BAR_RADIUS} />
                  </BarChart>
                </ChartBox>
              </ChartCard>
            </div>
            <div className="grid gap-5 lg:grid-cols-2">
              <ChartCard title={`${d.city}: mean daily maximum temperature by year`} subtitle="°C" rows={d.yearly}>
                <ChartBox height={240}>
                  <LineChart data={d.yearly} margin={{ top: 8, right: 16 }}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="year" {...AXIS} />
                    <YAxis {...AXIS} width={40} domain={['auto', 'auto']} unit="°" />
                    <Tooltip formatter={(v: number) => [`${fmt(v, 2)} °C`, 'Mean max']} />
                    <Line dataKey="mean_tmax" stroke="var(--s2)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                  </LineChart>
                </ChartBox>
              </ChartCard>
              <ChartCard title={`${d.city}: annual rainfall`} subtitle="mm per year" rows={d.yearly}>
                <ChartBox height={240}>
                  <BarChart data={d.yearly} margin={{ top: 8, right: 8 }} barCategoryGap={2}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="year" {...AXIS} />
                    <YAxis {...AXIS} width={48} tickFormatter={yCompact} />
                    <Tooltip formatter={(v: number) => [`${fmtInt(v)} mm`, 'Rain']} />
                    <Bar dataKey="rain_mm" fill="var(--s1)" radius={BAR_RADIUS} />
                  </BarChart>
                </ChartBox>
              </ChartCard>
            </div>
            <ChartCard title="All cities: average annual rainfall" subtitle="mm per year, 2000–2024" rows={d.compare}>
              <ChartBox height={240}>
                <BarChart data={compare} margin={{ top: 8, right: 8 }} barCategoryGap={6}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="city" {...AXIS} />
                  <YAxis {...AXIS} width={48} tickFormatter={yCompact} />
                  <Tooltip formatter={(v: number) => [`${fmtInt(v)} mm`, 'Annual rain']} />
                  <Bar dataKey="annual_rain_mm" radius={BAR_RADIUS}>
                    {compare.map(c => <Cell key={c.city} fill={c.city === d.city ? 'var(--s1)' : 'var(--axis)'} />)}
                  </Bar>
                </BarChart>
              </ChartBox>
            </ChartCard>
          </div>
        )
      }}</Gate>
    </div>
  )
}
