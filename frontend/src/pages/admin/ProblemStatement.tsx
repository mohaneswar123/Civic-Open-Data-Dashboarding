import { AlertTriangle, CheckCircle2, Target, Users } from 'lucide-react'
import { Card, PageHeader } from '../../components/ui'

const PROBLEMS = [
  ['Scattered and inconsistent', 'The same district or state is spelled differently across files, and values carry stray spaces.'],
  ['Totals mixed with details', 'Rows such as “Total foodgrain” sit beside the crops they add up, so naive sums double-count.'],
  ['Units change between rows', 'Coconut is counted in nuts and cotton in bales, while other crops are in tonnes.'],
  ['The same events counted many times', 'NCRB lists every suicide under five breakdowns; adding them inflates totals about fivefold.'],
  ['Easy to misread', 'Years with fewer reporting states look like a collapse; correlations look like causes.'],
]

const OBJECTIVES = [
  ['O1', 'Integrate and clean the public datasets with explicit, traceable quality rules.'],
  ['O2', 'Analyse trends and regional disparities (the reference analysis).'],
  ['O3', 'Analyse relationships honestly, e.g. monsoon rainfall against crop yield, with uncertainty.'],
  ['O4', 'Deliver a role-based public accountability dashboard with transparent methodology.'],
  ['O5', 'Validate the result: accuracy, lineage, failure handling and usability.'],
]

const ROLES = [
  ['Public', 'General dashboards and predictions in plain language, with no login.'],
  ['Policy maker', 'Disparities, district drill-downs, relationship analysis, uncertainty and what-if scenarios.'],
  ['Administrator', 'Datasets, EDA, model evaluation, architecture, lineage, code and operations.'],
]

const OUTCOMES = [
  ['100%', 'of 676,030 raw records accounted for (clean, quarantined or merged)'],
  ['0', 'reconciliation errors across all five datasets'],
  ['< 10 s', 'to rebuild every dataset from the raw files with one command'],
  ['5', 'prediction tasks, each with several classifiers compared and one selected'],
]

export default function ProblemStatement() {
  return (
    <div>
      <PageHeader title="Problem statement" subtitle="DSCI-20 · Civic Open-Data Dashboard for Public Accountability" />
      <Card>
        <h2 className="flex items-center gap-2 text-sm font-semibold text-ink"><Target size={16} className="text-accent" /> The problem</h2>
        <p className="mt-3 text-[15px] leading-relaxed text-ink">
          Governments publish open data on agriculture, climate, public health and social welfare, but citizens and officials rarely receive it in
          a usable, insight-driven form. Raw files are fragmented and inconsistent, and charts drawn straight from them can be wrong without looking
          wrong. The result is incomplete, incorrect or non-reproducible evidence reaching public decisions.
        </p>
        <p className="mt-3 text-[15px] leading-relaxed text-ink">
          <b>Goal:</b> turn messy public datasets into honest, transparent and decision-useful insight, where every published number can be traced
          back to a line in a government file.
        </p>
      </Card>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink"><AlertTriangle size={16} style={{ color: 'var(--serious)' }} /> What goes wrong with raw open data</h2>
          <ul className="mt-3 space-y-3">
            {PROBLEMS.map(([t, d]) => <li key={t} className="text-sm"><b className="text-ink">{t}.</b> <span className="text-ink-2">{d}</span></li>)}
          </ul>
        </Card>
        <Card>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink"><CheckCircle2 size={16} className="text-good" /> Objectives</h2>
          <ol className="mt-3 space-y-3">
            {OBJECTIVES.map(([k, d]) => <li key={k} className="flex gap-3 text-sm"><span className="font-semibold text-accent">{k}</span><span className="text-ink-2">{d}</span></li>)}
          </ol>
        </Card>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink"><Users size={16} className="text-accent" /> Who it serves</h2>
          <ul className="mt-3 space-y-3">
            {ROLES.map(([r, d]) => <li key={r} className="text-sm"><b className="text-ink">{r}:</b> <span className="text-ink-2">{d}</span></li>)}
          </ul>
          <h3 className="mt-5 text-sm font-semibold text-ink">Scope</h3>
          <p className="mt-2 text-sm text-ink-2">Five datasets are analysed independently: crop production, IMD rainfall, NCRB suicides, diabetes indicators and city weather. The only cross-dataset link is <b className="text-ink">crop production ↔ rainfall</b>, joined by state and year.</p>
        </Card>
        <Card>
          <h2 className="text-sm font-semibold text-ink">What the system has achieved so far</h2>
          <div className="mt-3 grid grid-cols-2 gap-3">
            {OUTCOMES.map(([v, d]) => (
              <div key={d} className="rounded-lg bg-surface-2 p-3">
                <div className="text-2xl font-semibold text-ink">{v}</div>
                <div className="mt-1 text-xs text-ink-2">{d}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
