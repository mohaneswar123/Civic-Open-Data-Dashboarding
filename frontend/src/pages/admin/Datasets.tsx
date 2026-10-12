import { useState } from 'react'
import { Badge, Card, DataTable, Gate, PageHeader, StatTile, Tabs } from '../../components/ui'
import { useApi } from '../../lib/hooks'
import { fmtInt } from '../../lib/format'

interface Rule { rule: string; description: string; action: string; rows: number; top_partitions?: Record<string, number> }
interface Dataset {
  name: string
  source: { file: string; title: string; publisher: string; url: string; licence: string; grain: string; units: Record<string, string>; sha256: string; bytes: number; modified: string }
  rows_in: number; rows_clean: number; rows_quarantined: number; rows_merged?: number; lineage_coverage_pct: number; reconciliation_errors: number
  steps: string[]; output_tables: Record<string, number>; quarantine_table: string | null; notes: string[]
  quality: { rules: Rule[]; partitions: Record<string, unknown>[] }
  schema: Record<string, { column_name: string; column_type: string }[]>
}

export default function Datasets() {
  const s = useApi<Dataset[]>('/api/admin/datasets')
  const [active, setActive] = useState('crop')
  return (
    <div>
      <PageHeader title="Datasets & lineage" subtitle="Source provenance, cleaning steps, quality rules, schema and quarantined rows for each dataset. Every published row is accounted for." />
      <Gate state={s}>{d => {
        const ds = d.find(x => x.name === active) ?? d[0]
        return (
          <>
            <Tabs tabs={d.map(x => ({ id: x.name, label: x.name }))} value={ds.name} onChange={setActive} />
            <DatasetView ds={ds} />
          </>
        )
      }}</Gate>
    </div>
  )
}

function DatasetView({ ds }: { ds: Dataset }) {
  const q = useApi<{ rows: Record<string, unknown>[]; reasons: { reason: string; n: number }[]; message?: string }>(`/api/admin/quarantine/${ds.name}?limit=100`)
  const [table, setTable] = useState(Object.keys(ds.output_tables)[0])
  const sample = useApi<Record<string, unknown>[]>(`/api/admin/datasets/${table}/sample?limit=15`)
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatTile label="Rows in raw file" value={fmtInt(ds.rows_in)} />
        <StatTile label="Clean rows published" value={fmtInt(ds.rows_clean)} />
        <StatTile label="Quarantined" value={fmtInt(ds.rows_quarantined)} hint={ds.rows_merged ? `+ ${fmtInt(ds.rows_merged)} merged (summed)` : undefined} />
        <StatTile label="Lineage coverage" value={`${ds.lineage_coverage_pct}%`} hint="rows accounted for" />
        <StatTile label="Reconciliation errors" value={ds.reconciliation_errors} hint={ds.reconciliation_errors === 0 ? <Badge tone="good">pass</Badge> : <Badge tone="critical">fail</Badge>} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <h3 className="text-sm font-semibold text-ink">Source & provenance</h3>
          <dl className="mt-3 grid grid-cols-[120px_1fr] gap-x-3 gap-y-1.5 text-xs">
            <dt className="text-muted">Title</dt><dd className="text-ink">{ds.source.title}</dd>
            <dt className="text-muted">Publisher</dt><dd className="text-ink">{ds.source.publisher}</dd>
            <dt className="text-muted">URL</dt><dd><a href={ds.source.url} target="_blank" rel="noreferrer" className="text-accent">{ds.source.url}</a></dd>
            <dt className="text-muted">Licence</dt><dd className="text-ink">{ds.source.licence}</dd>
            <dt className="text-muted">File</dt><dd className="text-ink">{ds.source.file} ({fmtInt(ds.source.bytes / 1024)} KB, modified {ds.source.modified})</dd>
            <dt className="text-muted">SHA-256</dt><dd className="font-mono text-[10px] break-all text-ink-2">{ds.source.sha256}</dd>
            <dt className="text-muted">Grain</dt><dd className="text-ink">{ds.source.grain}</dd>
            <dt className="text-muted">Units</dt><dd className="text-ink">{Object.entries(ds.source.units).map(([k, v]) => <div key={k}>{k}: {v}</div>)}</dd>
          </dl>
        </Card>
        <Card>
          <h3 className="text-sm font-semibold text-ink">Transformation steps (in order)</h3>
          <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs text-ink-2">{ds.steps.map(s => <li key={s}>{s}</li>)}</ol>
          <h3 className="mt-4 text-sm font-semibold text-ink">Output tables</h3>
          <div className="mt-2 flex flex-wrap gap-2">{Object.entries(ds.output_tables).map(([t, n]) => <Badge key={t} tone="accent">{t} · {fmtInt(n)}</Badge>)}</div>
          {ds.notes.length > 0 && <ul className="mt-4 list-disc space-y-1 pl-5 text-xs text-ink-2">{ds.notes.map(n => <li key={n}>{n}</li>)}</ul>}
        </Card>
      </div>
      <Card>
        <h3 className="mb-3 text-sm font-semibold text-ink">Quality rules applied</h3>
        <DataTable rows={ds.quality.rules.map(r => ({ ...r, top_partitions: r.top_partitions ? Object.entries(r.top_partitions).slice(0, 3).map(([k, v]) => `${k} (${v})`).join(', ') : '' }))}
          columns={[{ key: 'rule', label: 'Rule' }, { key: 'action', label: 'Action' }, { key: 'rows', label: 'Rows' }, { key: 'description', label: 'Description' }, { key: 'top_partitions', label: 'Most affected' }]} />
      </Card>
      <Card>
        <h3 className="mb-3 text-sm font-semibold text-ink">Per-partition health</h3>
        <p className="mb-3 text-xs text-ink-2">Quality per state, city or sub-division, so one broken partition cannot hide inside a good global average.</p>
        {ds.quality.partitions.length > 0 && <DataTable rows={ds.quality.partitions} columns={Object.keys(ds.quality.partitions[0]).map(k => ({ key: k, label: k }))} maxHeight={300} />}
      </Card>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-ink">Schema & sample</h3>
            {Object.keys(ds.output_tables).map(t => (
              <button key={t} onClick={() => setTable(t)} className={`rounded-full px-2 py-0.5 text-[11px] ${t === table ? 'bg-accent text-accent-ink' : 'bg-surface-2 text-ink-2'}`}>{t}</button>
            ))}
          </div>
          <DataTable rows={ds.schema[table] ?? []} columns={[{ key: 'column_name', label: 'Column' }, { key: 'column_type', label: 'Type' }]} maxHeight={240} />
          <div className="mt-3"><Gate state={sample}>{rows => rows.length ? <DataTable rows={rows} columns={Object.keys(rows[0]).map(k => ({ key: k, label: k }))} maxHeight={260} /> : null}</Gate></div>
        </Card>
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-ink">Quarantined rows (first 100)</h3>
          <Gate state={q}>{d => d.rows.length === 0
            ? <p className="text-xs text-muted">{d.message ?? 'None'}</p>
            : <>
              <div className="mb-2 flex flex-wrap gap-2">{d.reasons.map(r => <Badge key={r.reason} tone="warning">{r.reason}: {fmtInt(r.n)}</Badge>)}</div>
              <DataTable rows={d.rows} columns={Object.keys(d.rows[0]).map(k => ({ key: k, label: k }))} maxHeight={420} />
            </>}</Gate>
        </Card>
      </div>
    </div>
  )
}
