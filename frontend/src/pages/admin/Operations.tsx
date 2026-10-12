import { Badge, Card, DataTable, Gate, PageHeader, StatTile } from '../../components/ui'
import { useApi } from '../../lib/hooks'

interface Run { run_id: string; finished_at: string; duration_s: number; overall: string; reconciliation_errors: number; datasets: Record<string, { status: string; seconds: number; error?: string }> }
interface Telemetry { started_at: string; window_size: number; routes: { route: string; count: number; errors: number; denied: number; p50_ms: number; p95_ms: number; p99_ms: number }[]; recent: { ts: string; method: string; route: string; status: number; ms: number }[] }
interface Health { status: string; database: boolean; models_missing: string[] }

export default function Operations() {
  const runs = useApi<Run[]>('/api/admin/pipeline/runs')
  const tel = useApi<Telemetry>('/api/admin/telemetry')
  const health = useApi<Health>('/api/health')
  return (
    <div>
      <PageHeader title="Operations" subtitle="Pipeline runs, system health and API telemetry. Rebuild everything with `python run_all.py`." />
      <div className="space-y-5">
        <Gate state={health}>{h => (
          <div className="grid gap-4 sm:grid-cols-3">
            <StatTile label="System status" value={<Badge tone={h.status === 'ok' ? 'good' : 'warning'}>{h.status === 'ok' ? '● healthy' : '▲ degraded'}</Badge>} />
            <StatTile label="Analytics database" value={h.database ? 'available' : 'missing'} />
            <StatTile label="Models" value={h.models_missing.length ? `${h.models_missing.length} missing` : 'all 4 loaded'} hint={h.models_missing.join(', ') || undefined} />
          </div>
        )}</Gate>
        <Gate state={runs}>{r => (
          <Card>
            <h3 className="mb-3 text-sm font-semibold text-ink">Pipeline runs (latest first)</h3>
            <DataTable rows={r.map(x => ({
              run_id: x.run_id, finished_at: x.finished_at, duration_s: x.duration_s, overall: x.overall,
              reconciliation_errors: x.reconciliation_errors,
              datasets: Object.entries(x.datasets).map(([k, v]) => `${k}: ${v.status}`).join(' · '),
            }))} columns={[
              { key: 'run_id', label: 'Run' }, { key: 'finished_at', label: 'Finished (UTC)' }, { key: 'duration_s', label: 'Seconds' },
              { key: 'overall', label: 'Overall' }, { key: 'reconciliation_errors', label: 'Recon. errors' }, { key: 'datasets', label: 'Datasets' },
            ]} />
          </Card>
        )}</Gate>
        <Gate state={tel}>{t => (
          <>
            <Card>
              <h3 className="text-sm font-semibold text-ink">API latency by route</h3>
              <p className="mb-3 text-xs text-muted">Since {t.started_at} · last {t.window_size} requests</p>
              <DataTable rows={t.routes} columns={[
                { key: 'route', label: 'Route' }, { key: 'count', label: 'Calls' }, { key: 'p50_ms', label: 'p50 ms' }, { key: 'p95_ms', label: 'p95 ms' },
                { key: 'p99_ms', label: 'p99 ms' }, { key: 'errors', label: '5xx' }, { key: 'denied', label: '401/403' },
              ]} />
            </Card>
            <Card>
              <h3 className="mb-3 text-sm font-semibold text-ink">Recent requests</h3>
              <DataTable rows={t.recent} columns={[{ key: 'ts', label: 'Time' }, { key: 'method', label: 'Method' }, { key: 'route', label: 'Route' }, { key: 'status', label: 'Status' }, { key: 'ms', label: 'ms' }]} maxHeight={320} />
            </Card>
          </>
        )}</Gate>
      </div>
    </div>
  )
}
