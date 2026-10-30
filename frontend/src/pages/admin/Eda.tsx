import type { ReactNode } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from 'recharts'
import { CheckCircle2 } from 'lucide-react'
import { Card, ChartCard, DataTable, Gate, PageHeader, StatTile, Tabs } from '../../components/ui'
import { AXIS, BAR_RADIUS, ChartBox, GRID, HBAR_RADIUS, yCompact } from '../../components/charts'
import { useApi, useLocalState } from '../../lib/hooks'
import { fmt, fmtCompact, fmtInt } from '../../lib/format'

type Key = 'crop' | 'rainfall' | 'suicides' | 'diabetes' | 'weather'
const TABS: { id: Key; label: string }[] = [
  { id: 'crop', label: 'Crop production' }, { id: 'rainfall', label: 'Rainfall' }, { id: 'suicides', label: 'Suicides' },
  { id: 'diabetes', label: 'Diabetes' }, { id: 'weather', label: 'City weather' },
]

interface Summary { label: string; count: number; mean: number; std: number; min: number; q1: number; median: number; q3: number; max: number; outlier_pct: number }
interface Hist { label: string; log: boolean; bins: { x0: number; x1: number; count: number }[] }
interface Cats { label: string; measure: string; distinct: number; top: { value: string; count: number }[] }
interface Quality {
  raw_rows: number; raw_columns: number; missing: { column: string; missing: number; pct: number }[]
  missing_cells: number; missing_cells_pct: number; exact_duplicates: number; key_duplicates: number | null; key_columns: string[] | null
  text_issues: { column: string; rows: number }[]; negatives: { column: string; rows: number }[]
  issues: { issue: string; rows: number; action: string; detail: string }[]
  flow: { raw: number; quarantined: number; merged: number; clean: number | null }
}
interface EdaData {
  dataset: string; rows: number
  summary: Summary[]; histograms: Hist[]; categories: Cats[]
  pairs: { pair: string; r: number }[]
  trend: { label: string; x: string; points: { x: number | string; y: number }[] }
  targets: { task: string; title: string; rule: string; classes: { name: string; train: number; validation: number; test: number }[] }[]
  quality: Quality
  notes: string[]
}

const ONE = 'var(--s1)'
const label = { fontSize: 11, fill: 'var(--ink-2)' }
const small = (v: number) => (v !== 0 && Math.abs(v) < 0.01 ? '<0.01' : Math.abs(v) < 10 && v !== 0 ? Number(v.toPrecision(2)).toString() : fmtCompact(v))

export default function Eda() {
  const [tab, setTab] = useLocalState<Key>('civic.eda.tab', 'crop')
  const s = useApi<EdaData>(`/api/insights/eda/${tab}`)
  return (
    <div>
      <PageHeader title="EDA visualisations" subtitle="First the quality of the raw file (missing values, duplicates, problems found), then simple pictures of the cleaned data." />
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      <Gate state={s}>{d => <EdaView d={d} />}</Gate>
    </div>
  )
}

function Section({ n, title, intro, children }: { n: number; title: string; intro: string; children: ReactNode }) {
  return (
    <section className="space-y-4">
      <div className="border-b border-line pb-2">
        <h2 className="text-base font-semibold text-ink">{n}. {title}</h2>
        <p className="text-xs text-ink-2">{intro}</p>
      </div>
      {children}
    </section>
  )
}

function AllClear({ text }: { text: string }) {
  return <div className="flex items-center gap-2 rounded-lg bg-[color:var(--good)]/10 px-3 py-6 text-sm text-ink justify-center"><CheckCircle2 size={18} className="text-good" /> {text}</div>
}

function HBars({ rows, valueKey, nameKey, color = ONE, colors, fmtValue, height }: {
  rows: Record<string, unknown>[]; valueKey: string; nameKey: string; color?: string; colors?: string[]; fmtValue: (v: number) => string; height?: number
}) {
  return (
    <ChartBox height={height ?? Math.max(90, rows.length * 34 + 20)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 70, top: 4, bottom: 4 }} barCategoryGap={6}>
        <XAxis type="number" hide domain={[0, 'dataMax']} />
        <YAxis type="category" dataKey={nameKey} {...AXIS} axisLine={false} width={170} interval={0} tickFormatter={(v: string) => v.length > 26 ? v.slice(0, 25) + '…' : v} />
        <Tooltip formatter={(v: number) => [fmtValue(v), '']} separator="" />
        <Bar dataKey={valueKey} radius={HBAR_RADIUS} fill={color} maxBarSize={26}>
          {colors && rows.map((_, i) => <Cell key={i} fill={colors[i]} />)}
          <LabelList dataKey={valueKey} position="right" formatter={fmtValue} style={label} />
        </Bar>
      </BarChart>
    </ChartBox>
  )
}

function EdaView({ d }: { d: EdaData }) {
  const q = d.quality
  const missingCols = q.missing.filter(m => m.missing > 0)
  const flow = [
    { step: 'Rows in the raw file', rows: q.flow.raw },
    { step: 'Removed (quarantined)', rows: q.flow.quarantined },
    { step: 'Merged into other rows', rows: q.flow.merged },
    { step: 'Clean rows used', rows: q.flow.clean ?? d.rows },
  ]
  const flowColors = ['var(--axis)', 'var(--critical)', 'var(--warning)', 'var(--good)']
  const dups = [{ kind: 'Exact copies of a row', rows: q.exact_duplicates }, ...(q.key_duplicates != null ? [{ kind: 'Same key, different values', rows: q.key_duplicates }] : [])]
  const outliers = d.summary.map(s => ({ variable: s.label, pct: s.outlier_pct }))
  const other = [...q.text_issues.map(t => ({ check: `Extra spaces in “${t.column}”`, rows: t.rows })), ...q.negatives.map(n => ({ check: `Negative values in “${n.column}”`, rows: n.rows }))]

  return (
    <div className="space-y-10">
      {/* -------------------------------------------------- 1. data quality */}
      <Section n={1} title="Data quality of the raw file" intro="Checked on the original government file, before any cleaning.">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <StatTile label="Rows in raw file" value={fmtInt(q.raw_rows)} hint={`${q.raw_columns} columns`} />
          <StatTile label="Missing values" value={fmtInt(q.missing_cells)} hint={`${fmt(q.missing_cells_pct, 2)}% of all cells`} />
          <StatTile label="Exact duplicate rows" value={fmtInt(q.exact_duplicates)} />
          <StatTile label="Same-key duplicates" value={q.key_duplicates == null ? 'n/a' : fmtInt(q.key_duplicates)} hint={q.key_columns ? `key: ${q.key_columns.join(', ')}` : 'no natural key (anonymous records)'} />
          <StatTile label="Clean rows used" value={fmtInt(q.flow.clean ?? d.rows)} hint={`${fmt(100 * (q.flow.clean ?? d.rows) / q.raw_rows, 1)}% of the raw rows`} />
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <ChartCard title="From raw file to clean table" subtitle="Every raw row is accounted for: removed, merged, or kept" rows={flow}>
            <HBars rows={flow} nameKey="step" valueKey="rows" colors={flowColors} fmtValue={fmtInt} />
          </ChartCard>
          <ChartCard title="Missing values by column" subtitle={missingCols.length ? `${missingCols.length} of ${q.missing.length} columns have gaps` : 'Checked every column'} rows={q.missing}>
            {missingCols.length
              ? <HBars rows={missingCols.map(m => ({ column: m.column, pct: m.pct, missing: m.missing }))} nameKey="column" valueKey="pct" color="var(--critical)" fmtValue={v => `${fmt(v, 2)}%`} />
              : <AllClear text={`No missing values in any of the ${q.missing.length} columns`} />}
          </ChartCard>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <ChartCard title="Duplicate records" subtitle="Exact copies, and rows that repeat the same key with different values" rows={dups}>
            {dups.some(x => x.rows > 0)
              ? <HBars rows={dups} nameKey="kind" valueKey="rows" color="var(--warning)" fmtValue={fmtInt} />
              : <AllClear text="No duplicate records found" />}
          </ChartCard>
          <ChartCard title="Problems found and how they were handled" subtitle="Rows affected by each quality rule" rows={q.issues}>
            {q.issues.length
              ? <>
                <HBars rows={q.issues} nameKey="issue" valueKey="rows" color="var(--serious)" fmtValue={fmtInt} />
                <ul className="mt-2 space-y-1 text-xs text-ink-2">{q.issues.map(i => <li key={i.issue}><b className="text-ink">{i.issue}:</b> {i.action}. <span className="text-muted">{i.detail}</span></li>)}</ul>
              </>
              : <AllClear text="No rule found a problem in this file" />}
          </ChartCard>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <ChartCard title="Outliers" subtitle="Share of values far outside the usual range (IQR rule); they are flagged, not deleted" rows={outliers}>
            <HBars rows={outliers} nameKey="variable" valueKey="pct" color="var(--warning)" fmtValue={v => `${fmt(v, 1)}%`} />
          </ChartCard>
          <ChartCard title="Formatting and value checks" subtitle="Stray spaces in text and impossible negative numbers" rows={other}>
            {other.length
              ? <HBars rows={other} nameKey="check" valueKey="rows" color="var(--warning)" fmtValue={fmtInt} />
              : <AllClear text="No stray spaces or negative values found" />}
          </ChartCard>
        </div>
      </Section>

      {/* -------------------------------------------------- 2. distributions */}
      <Section n={2} title="How the values are spread" intro="Taller bars mean more records in that range.">
        <div className="grid gap-5 lg:grid-cols-2">
          {d.histograms.map(h => <Histogram key={h.label} h={h} s={d.summary.find(x => x.label === h.label)} />)}
        </div>
      </Section>

      {/* -------------------------------------------------- 3. categories */}
      <Section n={3} title="Most common values" intro="The largest groups in each category column.">
        <div className="grid gap-5 lg:grid-cols-2">
          {d.categories.map(c => {
            const top = c.top.slice(0, 8)
            return (
              <ChartCard key={c.label} title={c.label} subtitle={`${top[0]?.value} is the largest of ${c.distinct} groups`} rows={c.top}>
                <HBars rows={top} nameKey="value" valueKey="count" fmtValue={v => fmtCompact(v)} />
              </ChartCard>
            )
          })}
        </div>
      </Section>

      {/* -------------------------------------------------- 4. relationships */}
      <Section n={4} title="Which variables move together" intro="Correlation from −1 to +1: right (blue) = rise together, left (red) = one rises as the other falls, near 0 = no link.">
        <ChartCard title={d.pairs.length ? `Strongest link: ${d.pairs[0].pair} (${d.pairs[0].r.toFixed(2)})` : 'Correlations'} subtitle="Pairs sorted by strength" rows={d.pairs}>
          <ChartBox height={Math.max(140, d.pairs.length * 34 + 30)}>
            <BarChart data={d.pairs} layout="vertical" margin={{ left: 8, right: 48, top: 4, bottom: 4 }} barCategoryGap={6}>
              <XAxis type="number" domain={[-1, 1]} ticks={[-1, -0.5, 0, 0.5, 1]} {...AXIS} />
              <YAxis type="category" dataKey="pair" {...AXIS} axisLine={false} width={230} interval={0} />
              <ReferenceLine x={0} stroke="var(--ink-2)" />
              <Tooltip formatter={(v: number) => [v.toFixed(2), 'correlation']} />
              <Bar dataKey="r" radius={4}>
                {d.pairs.map(p => <Cell key={p.pair} fill={p.r >= 0 ? 'var(--div-pos)' : 'var(--div-neg)'} />)}
                <LabelList dataKey="r" position="right" formatter={(v: number) => v.toFixed(2)} style={label} />
              </Bar>
            </BarChart>
          </ChartBox>
        </ChartCard>
      </Section>

      {/* -------------------------------------------------- 5. trend */}
      <Section n={5} title={d.trend.x === 'Year' ? 'Change over time' : `Pattern across ${d.trend.x.toLowerCase()}s`} intro="One line, one measure.">
        <ChartCard title={d.trend.label} subtitle={`by ${d.trend.x.toLowerCase()}`} rows={d.trend.points}>
          <ChartBox height={260}>
            <LineChart data={d.trend.points} margin={{ top: 12, right: 24 }}>
              <CartesianGrid {...GRID} /><XAxis dataKey="x" {...AXIS} /><YAxis {...AXIS} width={52} tickFormatter={yCompact} domain={['auto', 'auto']} />
              <Tooltip formatter={(v: number) => [fmtCompact(v), d.trend.label]} />
              <Line dataKey="y" stroke={ONE} strokeWidth={2.5} dot={{ r: 3 }} />
            </LineChart>
          </ChartBox>
        </ChartCard>
      </Section>

      {/* -------------------------------------------------- 6. classes */}
      {d.targets.length > 0 && (
        <Section n={6} title="Prediction classes" intro="How the records are shared between the classes the models predict.">
          <div className="grid gap-5 lg:grid-cols-2">
            {d.targets.map(t => {
              const total = t.classes.reduce((a, c) => a + c.train + c.validation + c.test, 0) || 1
              const rows = t.classes.map(c => ({ name: c.name, pct: 100 * (c.train + c.validation + c.test) / total }))
              return (
                <ChartCard key={t.task} title={t.title} subtitle={t.rule} rows={rows}>
                  <ChartBox height={220}>
                    <BarChart data={rows} margin={{ top: 20, right: 8 }} barCategoryGap="30%">
                      <XAxis dataKey="name" {...AXIS} /><YAxis hide domain={[0, 'dataMax']} />
                      <Tooltip formatter={(v: number) => [`${fmt(v, 1)}%`, 'share of records']} />
                      <Bar dataKey="pct" fill={ONE} radius={BAR_RADIUS}><LabelList dataKey="pct" position="top" formatter={(v: number) => `${fmt(v, 1)}%`} style={label} /></Bar>
                    </BarChart>
                  </ChartBox>
                </ChartCard>
              )
            })}
          </div>
        </Section>
      )}

      {/* -------------------------------------------------- 7. table */}
      <Section n={d.targets.length ? 7 : 6} title="Summary statistics" intro="The numbers behind the charts above.">
        <Card>
          <DataTable rows={d.summary} columns={[
            { key: 'label', label: 'Variable' }, { key: 'count', label: 'Count', format: v => fmtInt(v as number) },
            { key: 'min', label: 'Min', format: v => small(v as number) }, { key: 'median', label: 'Median', format: v => small(v as number) },
            { key: 'mean', label: 'Mean', format: v => small(v as number) }, { key: 'max', label: 'Max', format: v => small(v as number) },
          ]} />
          {d.notes.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-ink-2">{d.notes.map(n => <li key={n}>{n}</li>)}</ul>}
        </Card>
      </Section>
    </div>
  )
}

function Histogram({ h, s }: { h: Hist; s?: Summary }) {
  // merge pairs of bins: 12 wider bars read more easily than 24 thin ones
  const merged = h.bins.reduce<{ x0: number; x1: number; count: number }[]>((acc, b, i) => {
    if (i % 2 === 0) acc.push({ ...b }); else { acc[acc.length - 1].x1 = b.x1; acc[acc.length - 1].count += b.count }
    return acc
  }, [])
  const val = (x: number) => small(h.log ? 10 ** x : x)
  const rows = merged.map(b => ({ range: `${val(b.x0)} to ${val(b.x1)}`, from: val(b.x0), count: b.count }))
  const peak = rows.reduce((a, b) => (b.count > a.count ? b : a), rows[0])
  const sub = s ? `Middle value ${small(s.median)}; half of the records lie between ${small(s.q1)} and ${small(s.q3)}` : `Most records: ${peak.range}`
  return (
    <ChartCard title={h.label} subtitle={sub + (h.log ? ' · ranges grow ×10 every few bars' : '')} rows={rows}>
      <ChartBox height={220}>
        <BarChart data={rows} margin={{ top: 8, right: 8 }} barCategoryGap={2}>
          <XAxis dataKey="from" {...AXIS} interval={1} />
          <YAxis {...AXIS} width={44} tickFormatter={yCompact} />
          <Tooltip formatter={(v: number) => [fmtInt(v), 'records']} labelFormatter={(_, p) => (p?.[0]?.payload as { range?: string } | undefined)?.range ?? ''} />
          <Bar dataKey="count" radius={BAR_RADIUS}>
            {rows.map(r => <Cell key={r.range} fill={r === peak ? ONE : 'var(--seq-3)'} />)}
          </Bar>
        </BarChart>
      </ChartBox>
    </ChartCard>
  )
}
