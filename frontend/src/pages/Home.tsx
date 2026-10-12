import { Link } from 'react-router-dom'
import { ArrowRight, CloudRain, Eye, HeartPulse, Scale, ShieldCheck, Sprout, Thermometer, Users } from 'lucide-react'
import { Card, Gate, PageHeader } from '../components/ui'
import { useApi } from '../lib/hooks'

interface Overview { cards: { key: string; title: string; span: string; facts: string[] }[] }
const ICONS: Record<string, typeof Sprout> = { crop: Sprout, rainfall: CloudRain, suicides: Users, diabetes: HeartPulse, weather: Thermometer }

const PRINCIPLES = [
  { icon: Eye, title: 'Transparent methodology', text: 'Every chart states its source, what was excluded and why, and has a table view and CSV download.' },
  { icon: Scale, title: 'Analytical honesty', text: 'Uncertainty intervals, sample sizes and baselines are shown. Negative findings are reported, not hidden.' },
  { icon: ShieldCheck, title: 'Traceable data', text: 'Every published row traces back to a line in a raw government file. Invalid rows are quarantined, never silently dropped.' },
]

export default function Home() {
  const overview = useApi<Overview>('/api/public/overview')
  return (
    <div>
      <PageHeader title="Civic Open-Data Dashboard for Public Accountability"
        subtitle="Turning messy public datasets into honest, transparent, decision-useful insight." />

      <section className="grid gap-5 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <h2 className="text-xs font-semibold tracking-wide text-muted uppercase">Problem statement</h2>
          <p className="mt-3 text-[15px] leading-relaxed text-ink">
            Governments publish open data on agriculture, climate, public health and social welfare, but citizens and officials
            rarely get it in a usable, insight-driven form. Raw files are inconsistent: misspelled names, duplicate rows, totals mixed
            in with details, and units that change between rows. Simple charts built on them are easy to misread, which leads to
            incorrect or non-reproducible evidence reaching public decisions.
          </p>
          <h3 className="mt-5 text-sm font-semibold text-ink">What this platform does</h3>
          <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-ink-2">
            <li><b className="text-ink">Integrates and cleans</b> five public datasets with explicit quality rules, quarantine and lineage.</li>
            <li><b className="text-ink">Analyses trends and regional disparities</b> (where things differ, and how they change over time).</li>
            <li><b className="text-ink">Analyses relationships honestly</b>, e.g. does monsoon rainfall go with crop yield? Results come with confidence intervals and baselines.</li>
            <li><b className="text-ink">Predicts</b> with machine-learning models that are always compared against simple baselines.</li>
          </ol>
          <div className="mt-5 flex flex-wrap gap-2">
            <Link to="/dashboards" className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink">Explore dashboards <ArrowRight size={15} /></Link>
            <Link to="/predictions" className="inline-flex items-center gap-1.5 rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink hover:bg-surface-2">Try predictions</Link>
          </div>
        </Card>
        <Card className="lg:col-span-2">
          <h2 className="text-xs font-semibold tracking-wide text-muted uppercase">Who it serves</h2>
          <ul className="mt-3 space-y-3 text-sm">
            <li><b className="text-ink">Public:</b> <span className="text-ink-2">general dashboards and predictions, in plain language, no login.</span></li>
            <li><b className="text-ink">Policy makers:</b> <span className="text-ink-2">advanced analytics, including disparity indices, district drill-downs, relationship analysis, uncertainty and what-if scenarios.</span></li>
            <li><b className="text-ink">Administrators:</b> <span className="text-ink-2">system architecture, dataset lineage and quality, project specification, pipeline code and operations.</span></li>
          </ul>
          <h2 className="mt-6 text-xs font-semibold tracking-wide text-muted uppercase">Scope</h2>
          <p className="mt-2 text-sm text-ink-2">
            Datasets are analysed <b className="text-ink">independently</b>. The single cross-dataset link is <b className="text-ink">crop production ↔ rainfall</b>,
            joined by state and year.
          </p>
        </Card>
      </section>

      <h2 className="mt-8 mb-3 text-sm font-semibold text-ink">Datasets</h2>
      <Gate state={overview}>{d => (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {d.cards.map(c => {
            const Icon = ICONS[c.key] ?? Sprout
            return (
              <Card key={c.key} className="!p-4">
                <div className="flex items-center gap-2 text-ink"><Icon size={16} className="text-accent" /><span className="text-sm font-semibold">{c.title}</span></div>
                <div className="mt-2 text-lg font-semibold text-ink">{c.span}</div>
                <ul className="mt-1 space-y-0.5 text-xs text-ink-2">{c.facts.map(f => <li key={f}>{f}</li>)}</ul>
              </Card>
            )
          })}
        </div>
      )}</Gate>

      <h2 className="mt-8 mb-3 text-sm font-semibold text-ink">Principles</h2>
      <div className="grid gap-4 md:grid-cols-3">
        {PRINCIPLES.map(p => (
          <Card key={p.title} className="!p-4">
            <p.icon size={18} className="text-accent" />
            <div className="mt-2 text-sm font-semibold text-ink">{p.title}</div>
            <p className="mt-1 text-xs leading-relaxed text-ink-2">{p.text}</p>
          </Card>
        ))}
      </div>
    </div>
  )
}
