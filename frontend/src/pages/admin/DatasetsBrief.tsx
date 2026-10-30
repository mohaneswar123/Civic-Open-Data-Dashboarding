import { useState } from 'react'
import { ChevronDown, CloudRain, HeartPulse, Sprout, Thermometer, Users } from 'lucide-react'
import { Badge, Card, DataTable, Gate, PageHeader } from '../../components/ui'
import { useApi } from '../../lib/hooks'
import { fmtInt } from '../../lib/format'

interface Brief {
  key: string; title: string; summary: string; period: string; grain: string; use: string; target: string
  columns: { name: string; type: string; description: string }[]
  rows_raw: number | null; rows_clean: number | null; rows_quarantined: number | null
  tasks: { task: string; title: string; classes: string[]; selected: string }[]
}
const ICONS: Record<string, typeof Sprout> = { crop: Sprout, rainfall: CloudRain, suicides: Users, diabetes: HeartPulse, weather: Thermometer }

export default function DatasetsBrief() {
  const s = useApi<Brief[]>('/api/insights/brief')
  return (
    <div>
      <PageHeader title="Datasets" subtitle="A short brief of each dataset: what it holds, its size, how it is used, and what the models predict from it." />
      <Gate state={s}>{d => <div className="space-y-4">{d.map(x => <DatasetCard key={x.key} d={x} />)}</div>}</Gate>
    </div>
  )
}

function DatasetCard({ d }: { d: Brief }) {
  const [open, setOpen] = useState(false)
  const Icon = ICONS[d.key] ?? Sprout
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h2 className="flex items-center gap-2 text-base font-semibold text-ink"><Icon size={18} className="text-accent" /> {d.title}</h2>
          <p className="mt-1 text-sm text-ink-2">{d.summary}</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge>{d.period}</Badge>
          {d.rows_raw != null && <Badge>{fmtInt(d.rows_raw)} raw rows</Badge>}
          {d.rows_clean != null && <Badge tone="good">{fmtInt(d.rows_clean)} clean</Badge>}
          {!!d.rows_quarantined && <Badge tone="warning">{fmtInt(d.rows_quarantined)} quarantined</Badge>}
        </div>
      </div>
      <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[140px_1fr]">
        <dt className="text-muted">One row is</dt><dd className="text-ink">{d.grain}</dd>
        <dt className="text-muted">Used for</dt><dd className="text-ink">{d.use}</dd>
        <dt className="text-muted">Target</dt><dd className="text-ink">{d.target}</dd>
        {d.tasks.length > 0 && <>
          <dt className="text-muted">Predicted classes</dt>
          <dd className="space-y-1">
            {d.tasks.map(t => (
              <div key={t.task} className="flex flex-wrap items-center gap-1.5 text-ink">
                <span className="mr-1">{t.title}:</span>
                {t.classes.map(c => <Badge key={c} tone="accent">{c}</Badge>)}
                <span className="ml-1 text-xs text-muted">selected model: {t.selected}</span>
              </div>
            ))}
          </dd>
        </>}
      </dl>
      <button onClick={() => setOpen(!open)} className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-accent">
        <ChevronDown size={14} className={open ? 'rotate-180 transition' : 'transition'} /> {open ? 'Hide' : 'Show'} the {d.columns.length} columns
      </button>
      {open && <div className="mt-3"><DataTable rows={d.columns} columns={[{ key: 'name', label: 'Column' }, { key: 'type', label: 'Type' }, { key: 'description', label: 'Meaning' }]} /></div>}
    </Card>
  )
}
