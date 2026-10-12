import { useEffect, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { Card, ErrorBox, Loading, PageHeader } from '../../components/ui'
import { getToken } from '../../lib/api'

const OBJECTIVES = [
  ['O1', 'Validate the problem & freeze the contract', 'Integrated, cleaned civic dataset with lineage, schema, quality rules and idempotent replay.', 'Pipeline + Datasets & lineage page'],
  ['O2', 'Reference: trends & regional disparities', 'Documented trends and disparities with baselines.', 'Dashboards + yield / rainfall disparity'],
  ['O3', 'Contribution: relationships, honestly', 'Defensible relationship analysis with uncertainty and a positive or negative conclusion.', 'Crop ↔ rainfall analysis + model ablation'],
  ['O4', 'Integrate the operable system', 'Transparent dashboard with telemetry, degraded mode and recovery.', 'FastAPI + React + health / ops'],
  ['O5', 'Independent acceptance', 'Validation report on rigour and usability; negative tests.', 'pytest suite + model reports'],
]
const KPIS = [
  ['KPI-1', 'Analytical honesty', '≥ 80/100 rubric', 'CIs, p-values, baselines, caveats on every view'],
  ['KPI-2', 'Insight usefulness', '≥ 80/100 rubric', 'Role-specific dashboards, drill-downs, what-if'],
  ['KPI-3', 'Transparency of methodology', '≥ 80/100 rubric', 'Notes panel, table view, open code (admin)'],
  ['KPI-4', 'End-to-end lineage coverage', '≥ 95%', '100%: every raw row is clean, quarantined or merged'],
  ['KPI-5', 'Reconciliation error count', '= 0', '0 in all datasets (see Datasets page)'],
  ['KPI-6', 'Pipeline latency p95', '≤ 0.8 × reference', 'Run time logged per run (Operations)'],
]

export default function ProjectInfo() {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    // The PDF endpoint is admin-only, so it is fetched with the token and shown from a blob URL.
    let obj: string | null = null
    fetch('/api/admin/project/pdf', { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => (r.ok ? r.blob() : Promise.reject(new Error(`PDF unavailable (${r.status})`))))
      .then(b => { obj = URL.createObjectURL(b); setUrl(obj) })
      .catch(e => setError(e.message))
    return () => { if (obj) URL.revokeObjectURL(obj) }
  }, [])

  return (
    <div>
      <PageHeader title="Project information" subtitle="DSCI-20 · Civic Open-Data Dashboard for Public Accountability · KL University capstone (CP1 + CP2)" />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <h3 className="text-sm font-semibold text-ink">Problem to solve</h3>
          <p className="mt-2 text-sm text-ink-2">Governments publish open data, but citizens and officials rarely have it in a usable, insight-driven form. The result is incomplete, incorrect or non-reproducible evidence reaching downstream decisions.</p>
          <h3 className="mt-4 text-sm font-semibold text-ink">Final achievement required</h3>
          <p className="mt-2 text-sm text-ink-2">A civic open-data dashboard that turns messy public datasets into honest, transparent, decision-useful insight.</p>
          <h3 className="mt-4 text-sm font-semibold text-ink">Scope decisions in this implementation</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-2">
            <li>Five datasets, each analysed independently; the only cross-dataset link is crop ↔ rainfall.</li>
            <li>Three roles (public, policy maker, admin), enforced on the server.</li>
            <li>Runs locally; no production certification (excluded by the specification).</li>
          </ul>
        </Card>
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-ink">Objectives → where they are implemented</h3>
          <table className="w-full text-xs"><tbody className="divide-y divide-line">
            {OBJECTIVES.map(([id, t, out, where]) => (
              <tr key={id}><td className="py-2 pr-2 align-top font-semibold text-accent">{id}</td><td className="py-2 pr-2 align-top"><div className="font-medium text-ink">{t}</div><div className="text-ink-2">{out}</div></td><td className="py-2 align-top text-ink-2">{where}</td></tr>
            ))}
          </tbody></table>
        </Card>
      </div>
      <Card className="mt-5">
        <h3 className="mb-3 text-sm font-semibold text-ink">KPIs and how this system addresses them</h3>
        <table className="w-full text-xs"><thead className="text-left text-muted"><tr><th className="py-1">ID</th><th>Measure</th><th>Target</th><th>Implementation evidence</th></tr></thead>
          <tbody className="divide-y divide-line">{KPIS.map(r => <tr key={r[0]}>{r.map((c, i) => <td key={i} className={`py-1.5 pr-3 ${i === 0 ? 'font-semibold text-accent' : 'text-ink-2'}`}>{c}</td>)}</tr>)}</tbody>
        </table>
      </Card>
      <Card className="mt-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-ink">Original specification (PDF)</h3>
          {url && <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-accent">Open in new tab <ExternalLink size={12} /></a>}
        </div>
        {error ? <ErrorBox message={error} /> : url ? <iframe src={url} title="Project specification" className="h-[75vh] w-full rounded-lg border border-line" /> : <Loading />}
      </Card>
    </div>
  )
}
