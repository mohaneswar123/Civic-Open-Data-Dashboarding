import type { ReactNode } from 'react'
import { ArrowDown, ArrowRight } from 'lucide-react'
import { Card, PageHeader } from '../../components/ui'

function Box({ title, kind, items, tone = 'var(--s1)' }: { title: string; kind: string; items: string[]; tone?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3" style={{ borderTop: `3px solid ${tone}` }}>
      <div className="text-[10px] font-semibold tracking-wide text-muted uppercase">{kind}</div>
      <div className="text-sm font-semibold text-ink">{title}</div>
      <ul className="mt-1.5 space-y-0.5 text-[11px] text-ink-2">{items.map(i => <li key={i}>• {i}</li>)}</ul>
    </div>
  )
}

const Arrow = ({ label, down }: { label?: string; down?: boolean }) => (
  <div className={`flex items-center justify-center gap-1 text-[10px] text-muted ${down ? 'flex-col py-1' : 'px-1'}`}>
    {down ? <ArrowDown size={16} /> : <ArrowRight size={16} className="hidden lg:block" />}
    {down && label && <span>{label}</span>}
    {!down && <ArrowDown size={16} className="lg:hidden" />}
  </div>
)

function Lane({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-2 text-xs font-semibold text-ink-2">{title}</div>
      <div className="flex flex-col items-stretch gap-1 lg:flex-row lg:items-center">{children}</div>
    </div>
  )
}

export default function Architecture() {
  return (
    <div>
      <PageHeader title="System architecture" subtitle="How raw government files become published, traceable insight. Every arrow is an interface that is implemented and tested." />
      <Card className="space-y-5">
        <Lane title="1 · Data engineering: python -m pipeline.run (idempotent, about 8 s)">
          <Box kind="Input" title="Raw open data (CSV)" tone="var(--s3)" items={['crop_production.csv', 'rainfall_india_cleaned.csv', 'cleaned_suicides.csv', 'diabetes_prediction_dataset.csv', 'india_2000_2024_daily_weather.csv']} />
          <Arrow />
          <Box kind="Validate" title="Schema & provenance" items={['required columns & types', 'SHA-256 of every file', 'fail → dataset marked failed']} />
          <Arrow />
          <Box kind="Clean" title="Quality rules engine" items={['normalise names & units', 'quarantine invalid rows (+reason)', 'flag suspicious rows', 'repair from primary values', 'per-partition health']} />
          <Arrow />
          <Box kind="Store" title="DuckDB (civic.duckdb)" tone="var(--s7)" items={['clean tables', 'quarantine_* tables', 'atomic file swap', 'last-good fallback']} />
          <Arrow />
          <Box kind="Evidence" title="Lineage & quality reports" tone="var(--s4)" items={['rows in = clean + quarantined + merged', 'reconciliation error count', 'run log (JSONL)']} />
        </Lane>
        <Arrow down label="read-only SQL" />
        <Lane title="2 · Analytics & ML: python -m ml.train_all (seeded, versioned)">
          <Box kind="Reference (O2)" title="Trends & regional disparity" items={['OLS trends + p-values', 'Gini, CV, rankings', 'coverage-aware totals']} />
          <Arrow />
          <Box kind="Contribution (O3)" title="Relationship analysis" tone="var(--s2)" items={['crop yield ↔ monsoon rainfall', 'detrended Spearman + bootstrap CI', 'multiple-testing warning', 'model ablation (with / without rain)']} />
          <Arrow />
          <Box kind="Models" title="LightGBM + baselines" items={['crop yield to 2030 (+ conformal interval)', 'rain & max temp, 1–7 days ahead', 'diabetes risk (+ SHAP)', 'suicide counts, multi-year (back-tested)']} />
          <Arrow />
          <Box kind="Evidence" title="Model reports" tone="var(--s4)" items={['time-separated test sets', 'baseline vs candidate', 'condition-wise errors', 'data hash for each model']} />
        </Lane>
        <Arrow down label="joblib bundles + JSON reports" />
        <Lane title="3 · Serving: FastAPI (uvicorn) and React (Vite)">
          <Box kind="API" title="FastAPI backend" tone="var(--s7)" items={['/api/public/* (anyone)', '/api/insights/* (anyone)', '/api/policy/* (policy+)', '/api/admin/* (admin)', '/api/predict/* (role-aware detail)', '/api/health (degraded flag)']} />
          <Arrow />
          <Box kind="Security" title="JWT + RBAC" tone="var(--s8)" items={['bcrypt password hashes', 'role checked on every request', '401 / 403 responses', 'code viewer path allow-list']} />
          <Arrow />
          <Box kind="Ops" title="Telemetry" items={['latency p50 / p95 / p99 per route', 'error & denied counts', 'request log file']} />
          <Arrow />
          <Box kind="UI" title="React dashboard" tone="var(--s3)" items={['Public: dashboards & predictions', 'Policy: advanced analytics', 'Admin: lineage, code, ops', 'table view + CSV on every chart']} />
        </Lane>
      </Card>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <h3 className="text-sm font-semibold text-ink">Technology stack</h3>
          <table className="mt-3 w-full text-xs">
            <tbody className="divide-y divide-line">
              {[
                ['Data processing', 'Python 3.13, pandas 3, NumPy'],
                ['Analytics store', 'DuckDB (embedded SQL, columnar)'],
                ['Machine learning', 'scikit-learn, LightGBM, SciPy'],
                ['API', 'FastAPI, Uvicorn, PyJWT, bcrypt'],
                ['Frontend', 'React 19, TypeScript, Vite, Tailwind CSS 4'],
                ['Charts', 'Recharts (CVD-validated palette)'],
                ['Testing', 'pytest (pipeline, negative tests, API access control)'],
              ].map(([k, v]) => <tr key={k}><td className="py-1.5 pr-3 font-medium text-ink">{k}</td><td className="py-1.5 text-ink-2">{v}</td></tr>)}
            </tbody>
          </table>
        </Card>
        <Card>
          <h3 className="text-sm font-semibold text-ink">Failure handling (negative tests NT-1 to NT-5)</h3>
          <ul className="mt-3 space-y-2 text-xs text-ink-2">
            <li><b className="text-ink">NT-1 Messy data:</b> invalid rows are quarantined with a reason before commit; re-runs are idempotent.</li>
            <li><b className="text-ink">NT-2 Easy to misread:</b> incomplete years are faded, counts are labelled as "not rates", and aggregate rows are excluded.</li>
            <li><b className="text-ink">NT-3 Misleading conclusions:</b> CIs, p-values, multiple-testing warnings and baseline comparisons appear on every analysis.</li>
            <li><b className="text-ink">NT-4 Broken partition:</b> quality is reported per state, city or sub-division, not only globally.</li>
            <li><b className="text-ink">NT-5 Access control:</b> the server enforces roles, and the code viewer cannot read files outside its allow-list.</li>
            <li><b className="text-ink">Degraded mode:</b> if one dataset fails, the others still publish and the failed one serves its last good version; the UI shows a banner.</li>
          </ul>
        </Card>
      </div>
    </div>
  )
}
