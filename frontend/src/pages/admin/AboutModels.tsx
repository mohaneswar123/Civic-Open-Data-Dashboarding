import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Tooltip, XAxis, YAxis } from 'recharts'
import { CheckCircle2, CircleSlash, Sparkles } from 'lucide-react'
import { Badge, Button, Card, ChartCard, DataTable, ErrorBox, Field, Gate, Input, PageHeader, Select, Warning } from '../../components/ui'
import { AXIS, ChartBox, GRID, HBAR_RADIUS } from '../../components/charts'
import { post } from '../../lib/api'
import { useApi, useLocalState } from '../../lib/hooks'
import { fmt } from '../../lib/format'

interface TaskCard { task: string; dataset: string; title: string; classes: string[]; selected: string; test_macro_f1: number; models: number }
interface Scores { accuracy: number; balanced_accuracy: number; macro_precision: number; macro_recall: number; macro_f1: number; roc_auc: number | null }
interface ModelRes {
  model: string; family: string; train_s: number; train_f1: number; verdict: string; reasons: string[]
  validation: Scores; test: Scores & { per_class: { precision: number; recall: number; f1: number }[]; confusion: number[][] }
}
interface Report {
  task: string; dataset: string; title: string; target: string; class_names: string[]; class_rule: string; split: string; note: string
  features: { categorical: string[]; numeric: string[] }; rows: Record<string, number>; selection_rule: string; selected: string; models: ModelRes[]
}

export default function AboutModels() {
  const list = useApi<TaskCard[]>('/api/insights/classifiers')
  const [task, setTask] = useLocalState<string>('civic.models.task', 'crop_yield')
  return (
    <div>
      <PageHeader title="About models" subtitle="Each target is turned into classes (Low / Medium / High and similar). Several classifiers are trained on the same split and compared; the one with the best validation score is selected. Predictions show the class only." />
      <Gate state={list}>{l => (
        <>
          <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {l.map(t => (
              <button key={t.task} onClick={() => setTask(t.task)}
                className={`rounded-xl border p-3 text-left transition ${t.task === task ? 'border-accent bg-accent/8 ring-2 ring-accent/20' : 'border-line bg-surface hover:bg-surface-2'}`}>
                <div className="text-xs text-muted capitalize">{t.dataset} dataset</div>
                <div className="mt-0.5 text-sm font-semibold text-ink">{t.title}</div>
                <div className="mt-2 text-xs text-ink-2">Selected: <b className="text-ink">{t.selected}</b></div>
                <div className="mt-1 flex flex-wrap gap-1">{t.classes.map(c => <Badge key={c}>{c}</Badge>)}</div>
              </button>
            ))}
          </div>
          <TaskView key={task} task={task} />
        </>
      )}</Gate>
    </div>
  )
}

function TaskView({ task }: { task: string }) {
  const r = useApi<Report>(`/api/insights/classifiers/${task}`)
  const [focus, setFocus] = useState<string | null>(null)
  return (
    <Gate state={r}>{d => {
      const sel = d.models.find(m => m.model === d.selected)!
      const shown = d.models.find(m => m.model === (focus ?? d.selected))!
      const ranked = [...d.models].sort((a, b) => b.validation.macro_f1 - a.validation.macro_f1)
      return (
        <div className="space-y-5">
          <Card>
            <div className="grid gap-5 lg:grid-cols-2">
              <div>
                <h2 className="text-base font-semibold text-ink">{d.title}</h2>
                <p className="mt-1 text-sm text-ink-2"><b className="text-ink">Predicts:</b> {d.target}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-sm"><b className="text-ink">Classes:</b>{d.class_names.map(c => <Badge key={c} tone="accent">{c}</Badge>)}</div>
                <p className="mt-2 text-xs text-ink-2">{d.class_rule}</p>
              </div>
              <div className="space-y-1.5 text-xs text-ink-2">
                <p><b className="text-ink">Data split:</b> {d.split} ({Object.entries(d.rows).map(([k, v]) => `${k} ${v.toLocaleString('en-IN')}`).join(' · ')} rows)</p>
                <p><b className="text-ink">Selection rule:</b> {d.selection_rule}</p>
                <p><b className="text-ink">Inputs:</b> {[...d.features.categorical, ...d.features.numeric].join(', ')}</p>
                <p><b className="text-ink">Note:</b> {d.note}</p>
              </div>
            </div>
          </Card>

          <Card>
            <h3 className="mb-3 text-sm font-semibold text-ink">Evaluation of every model (test split unless marked)</h3>
            <DataTable rows={ranked.map(m => ({
              model: m.model, family: m.family, val_f1: m.validation.macro_f1, f1: m.test.macro_f1, acc: m.test.accuracy,
              bal: m.test.balanced_accuracy, p: m.test.macro_precision, rec: m.test.macro_recall, auc: m.test.roc_auc, t: m.train_s, verdict: m.verdict,
            }))} columns={[
              { key: 'model', label: 'Model' }, { key: 'family', label: 'Family' },
              { key: 'val_f1', label: 'Validation macro-F1', format: v => fmt(v as number, 3) },
              { key: 'f1', label: 'Macro-F1', format: v => fmt(v as number, 3) }, { key: 'acc', label: 'Accuracy', format: v => fmt(v as number, 3) },
              { key: 'bal', label: 'Balanced acc.', format: v => fmt(v as number, 3) }, { key: 'p', label: 'Macro precision', format: v => fmt(v as number, 3) },
              { key: 'rec', label: 'Macro recall', format: v => fmt(v as number, 3) }, { key: 'auc', label: 'ROC-AUC', format: v => v == null ? '—' : fmt(v as number, 3) },
              { key: 't', label: 'Train (s)', format: v => fmt(v as number, 1) },
              { key: 'verdict', label: 'Status', format: v => (v === 'Selected' ? '✓ Selected' : 'Not selected') },
            ]} />
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <ChartCard title={`${sel.model} has the best validation macro-F1`} subtitle="Macro-F1 on the validation split, used for selection (0 to 1, higher is better)"
              rows={ranked.map(m => ({ model: m.model, validation_macro_f1: m.validation.macro_f1, test_macro_f1: m.test.macro_f1 }))}>
              <ChartBox height={Math.max(200, ranked.length * 34)}>
                <BarChart data={ranked} layout="vertical" margin={{ left: 8, right: 44 }} barCategoryGap={4}>
                  <CartesianGrid {...GRID} horizontal={false} vertical />
                  <XAxis type="number" domain={[0, 1]} {...AXIS} />
                  <YAxis type="category" dataKey="model" {...AXIS} width={130} interval={0} />
                  <Tooltip formatter={(v: number) => [fmt(v, 3), 'Validation macro-F1']} />
                  <Bar dataKey="validation.macro_f1" radius={HBAR_RADIUS} onClick={(e: { model?: string }) => e.model && setFocus(e.model)} cursor="pointer">
                    {ranked.map(m => <Cell key={m.model} fill={m.model === d.selected ? 'var(--s1)' : 'var(--axis)'} />)}
                    <LabelList dataKey="validation.macro_f1" position="right" formatter={(v: number) => fmt(v, 3)} style={{ fontSize: 11, fill: 'var(--ink-2)' }} />
                  </Bar>
                </BarChart>
              </ChartBox>
            </ChartCard>

            <Card>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-ink">Confusion matrix (test split)</h3>
                <Select value={shown.model} onChange={setFocus} options={d.models.map(m => m.model)} className="!w-48 !py-1 text-xs" />
              </div>
              <Confusion m={shown.test.confusion} classes={d.class_names} />
              <p className="mt-2 text-[11px] text-muted">Rows = actual class, columns = predicted class. Each cell shows the count and the share of that actual class; the diagonal holds the correct predictions.</p>
            </Card>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
                {shown.verdict === 'Selected' ? <CheckCircle2 size={16} className="text-good" /> : <CircleSlash size={16} className="text-muted" />}
                Why {shown.model} was {shown.verdict === 'Selected' ? 'selected' : 'not selected'}
              </h3>
              <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">{shown.reasons.map(x => <li key={x}>{x}</li>)}</ul>
              <h4 className="mt-4 mb-2 text-xs font-semibold text-ink uppercase">Per-class results ({shown.model}, test)</h4>
              <DataTable rows={d.class_names.map((c, i) => ({ cls: c, ...shown.test.per_class[i] }))} columns={[
                { key: 'cls', label: 'Class' }, { key: 'precision', label: 'Precision', format: v => fmt(v as number, 3) },
                { key: 'recall', label: 'Recall', format: v => fmt(v as number, 3) }, { key: 'f1', label: 'F1', format: v => fmt(v as number, 3) },
              ]} />
              <div className="mt-4 space-y-1.5">
                <h4 className="text-xs font-semibold text-ink uppercase">Other models</h4>
                {d.models.filter(m => m.model !== shown.model).map(m => (
                  <button key={m.model} onClick={() => setFocus(m.model)} className="block w-full rounded-lg px-2 py-1.5 text-left text-xs text-ink-2 hover:bg-surface-2">
                    <b className="text-ink">{m.model}</b> · {m.verdict} · {m.reasons[0]}
                  </button>
                ))}
              </div>
            </Card>
            <PredictPanel task={task} report={d} />
          </div>
        </div>
      )
    }}</Gate>
  )
}

const SEQ = ['var(--seq-1)', 'var(--seq-2)', 'var(--seq-3)', 'var(--seq-4)', 'var(--seq-5)', 'var(--seq-6)', 'var(--seq-7)']

function Confusion({ m, classes }: { m: number[][]; classes: string[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-[3px] text-xs">
        <thead>
          <tr><th className="p-1 text-left text-muted">Actual ↓ / Predicted →</th>{classes.map(c => <th key={c} className="p-1 font-medium text-ink-2">{c}</th>)}</tr>
        </thead>
        <tbody>
          {m.map((row, i) => {
            const tot = row.reduce((a, b) => a + b, 0) || 1
            return (
              <tr key={classes[i]}>
                <td className="p-1 pr-2 font-medium whitespace-nowrap text-ink-2">{classes[i]}</td>
                {row.map((v, j) => {
                  const share = v / tot
                  const k = Math.min(6, Math.floor(share * 7))
                  return (
                    <td key={j} className={`rounded-md p-2 text-center tabular ${i === j ? 'ring-2 ring-accent/60' : ''}`}
                      style={{ background: SEQ[k], color: k >= 4 ? '#fff' : 'var(--ink)' }} title={`${classes[i]} predicted as ${classes[j]}: ${v.toLocaleString('en-IN')} (${(100 * share).toFixed(1)}%)`}>
                      <div className="font-semibold">{v.toLocaleString('en-IN')}</div>
                      <div className="text-[10px] opacity-80">{(100 * share).toFixed(1)}%</div>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ------------------------------------------------------------------ prediction (class label only)
interface Opts {
  models: string[]; selected: string; classes: string[]
  districts?: Record<string, string[]>; crop_seasons?: Record<string, string[]>; crops?: string[]
  genders?: string[]; smoking?: string[]; cities?: string[]; first_date?: string; last_date?: string
  states?: string[]; age_groups?: string[]; years?: [number, number]
}

function PredictPanel({ task, report }: { task: string; report: Report }) {
  const o = useApi<Opts>(`/api/insights/classifiers/${task}/options`)
  return (
    <Card>
      <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink"><Sparkles size={16} className="text-accent" /> Predict a class</h3>
      <p className="mb-4 text-xs text-ink-2">The result is the predicted class only. Choose any model to compare; the selected one is the default.</p>
      <Gate state={o}>{opts => <PredictForm task={task} opts={opts} classes={report.class_names} />}</Gate>
    </Card>
  )
}

function PredictForm({ task, opts, classes }: { task: string; opts: Opts; classes: string[] }) {
  const [model, setModel] = useState(opts.selected)
  const [x, setX] = useState<Record<string, string>>(() => defaults(task, opts))
  const [res, setRes] = useState<{ label: string; model: string; is_selected_model: boolean } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: string) => (v: string) => { setX(p => ({ ...p, [k]: v })); setRes(null) }
  const districts = opts.districts?.[x.state] ?? []
  useEffect(() => { if (task === 'crop_yield' && districts.length && !districts.includes(x.district)) set('district')(districts[0]) }, [x.state]) // eslint-disable-line react-hooks/exhaustive-deps
  const seasons = opts.crop_seasons?.[x.crop] ?? []
  useEffect(() => { if (task === 'crop_yield' && seasons.length && !seasons.includes(x.season)) set('season')(seasons[0]) }, [x.crop]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async () => {
    setBusy(true); setErr(null)
    try { setRes(await post('/api/insights/classifiers/' + task + '/predict', { model, inputs: x })) } catch (e) { setErr((e as Error).message); setRes(null) } finally { setBusy(false) }
  }
  const idx = res ? classes.indexOf(res.label) : -1
  const tone = idx < 0 ? 'neutral' : classes.length === 2 ? (idx === 1 ? 'critical' : 'good') : (['good', 'neutral', 'warning'] as const)[idx]

  return (
    <form onSubmit={e => { e.preventDefault(); run() }} className="space-y-3">
      <Field label="Model"><Select value={model} onChange={v => { setModel(v); setRes(null) }} options={opts.models.map(m => ({ value: m, label: m === opts.selected ? `${m} (selected)` : m }))} /></Field>
      {task === 'crop_yield' && <>
        <div className="grid grid-cols-2 gap-3">
          <Field label="State"><Select value={x.state} onChange={set('state')} options={Object.keys(opts.districts ?? {}).sort()} /></Field>
          <Field label="District"><Select value={x.district} onChange={set('district')} options={districts} /></Field>
          <Field label="Crop"><Select value={x.crop} onChange={set('crop')} options={opts.crops ?? []} /></Field>
          <Field label="Season"><Select value={x.season} onChange={set('season')} options={seasons} /></Field>
          <Field label="Area (hectares)"><Input type="number" min={1} value={x.area_ha} onChange={e => set('area_ha')(e.target.value)} /></Field>
          <Field label="Year"><Input type="number" min={1997} max={2030} value={x.year} onChange={e => set('year')(e.target.value)} /></Field>
        </div>
      </>}
      {task === 'diabetes' && <div className="grid grid-cols-2 gap-3">
        <Field label="Gender"><Select value={x.gender} onChange={set('gender')} options={opts.genders ?? []} /></Field>
        <Field label="Age"><Input type="number" min={0} max={120} value={x.age} onChange={e => set('age')(e.target.value)} /></Field>
        <Field label="Hypertension"><Select value={x.hypertension} onChange={set('hypertension')} options={[{ value: '0', label: 'No' }, { value: '1', label: 'Yes' }]} /></Field>
        <Field label="Heart disease"><Select value={x.heart_disease} onChange={set('heart_disease')} options={[{ value: '0', label: 'No' }, { value: '1', label: 'Yes' }]} /></Field>
        <Field label="Smoking history"><Select value={x.smoking_history} onChange={set('smoking_history')} options={opts.smoking ?? []} /></Field>
        <Field label="BMI"><Input type="number" step="0.1" value={x.bmi} onChange={e => set('bmi')(e.target.value)} /></Field>
        <Field label="HbA1c (%)"><Input type="number" step="0.1" value={x.HbA1c_level} onChange={e => set('HbA1c_level')(e.target.value)} /></Field>
        <Field label="Glucose (mg/dL)"><Input type="number" value={x.blood_glucose_level} onChange={e => set('blood_glucose_level')(e.target.value)} /></Field>
      </div>}
      {task.startsWith('weather') && <div className="grid grid-cols-2 gap-3">
        <Field label="City"><Select value={x.city} onChange={set('city')} options={opts.cities ?? []} /></Field>
        <Field label="Day to predict" hint={`${opts.first_date} to ${opts.last_date}`}><Input type="date" value={x.date} min={opts.first_date} max={opts.last_date} onChange={e => set('date')(e.target.value)} /></Field>
      </div>}
      {task === 'suicides' && <div className="grid grid-cols-2 gap-3">
        <Field label="State"><Select value={x.state} onChange={set('state')} options={opts.states ?? []} /></Field>
        <Field label="Gender"><Select value={x.gender} onChange={set('gender')} options={opts.genders ?? []} /></Field>
        <Field label="Age group"><Select value={x.age_group} onChange={set('age_group')} options={opts.age_groups ?? []} /></Field>
        <Field label="Year"><Select value={x.year} onChange={set('year')} options={opts.years ? Array.from({ length: opts.years[1] - opts.years[0] + 1 }, (_, i) => String(opts.years![0] + i)) : []} /></Field>
      </div>}
      <Button type="submit" disabled={busy} className="w-full"><Sparkles size={15} /> {busy ? 'Predicting…' : 'Predict class'}</Button>
      {err && <ErrorBox message={err} />}
      {res && (
        <div className="rounded-xl border border-line bg-surface-2 p-4 text-center">
          <div className="text-xs text-muted">Predicted class</div>
          <div className="mt-2"><Badge tone={tone}><span className="px-2 py-1 text-lg font-semibold">{res.label}</span></Badge></div>
          <div className="mt-3 flex flex-wrap justify-center gap-1.5">
            {classes.map(c => <span key={c} className={`rounded-full px-2 py-0.5 text-[11px] ${c === res.label ? 'bg-accent text-accent-ink' : 'bg-surface text-muted'}`}>{c}</span>)}
          </div>
          <div className="mt-3 text-xs text-ink-2">by {res.model}{res.is_selected_model ? ' (the selected model)' : ' (not the selected model)'}</div>
        </div>
      )}
      {res && !res.is_selected_model && <Warning>This prediction comes from a model that was not selected; compare it with the selected model's answer.</Warning>}
    </form>
  )
}

function defaults(task: string, o: Opts): Record<string, string> {
  if (task === 'crop_yield') return { state: 'Punjab', district: o.districts?.Punjab?.[0] ?? '', crop: 'Wheat', season: 'Rabi', area_ha: '1000', year: '2014' }
  if (task === 'diabetes') return { gender: 'Female', age: '45', hypertension: '0', heart_disease: '0', smoking_history: 'never', bmi: '27', HbA1c_level: '5.8', blood_glucose_level: '130' }
  if (task.startsWith('weather')) return { city: 'Mumbai', date: '2024-07-10' }
  return { state: 'Maharashtra', gender: 'Male', age_group: '30-44', year: '2012' }
}
