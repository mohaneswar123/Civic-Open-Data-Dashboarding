import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  BarChart3, Boxes, BrainCircuit, Code2, Database, FileText, Gauge, Home, LogIn, LogOut, Menu, Moon,
  Network, ScrollText, ShieldCheck, Sun, X, type LucideIcon,
} from 'lucide-react'
import { hasRole, ROLE_LABEL, useAuth, type Role } from '../lib/auth'
import { useApi, useLocalState } from '../lib/hooks'

interface NavItem { to: string; label: string; icon: LucideIcon; role: Role }
const NAV: { section: string; items: NavItem[] }[] = [
  { section: 'Explore', items: [
    { to: '/', label: 'Problem & overview', icon: Home, role: 'public' },
    { to: '/dashboards', label: 'Dashboards', icon: BarChart3, role: 'public' },
    { to: '/predictions', label: 'Predictions', icon: BrainCircuit, role: 'public' },
    { to: '/models', label: 'Model transparency', icon: Gauge, role: 'public' },
  ] },
  { section: 'Policy makers', items: [
    { to: '/advanced', label: 'Advanced analytics', icon: ShieldCheck, role: 'policy' },
  ] },
  { section: 'Administration', items: [
    { to: '/admin/architecture', label: 'System architecture', icon: Network, role: 'admin' },
    { to: '/admin/datasets', label: 'Datasets & lineage', icon: Database, role: 'admin' },
    { to: '/admin/project', label: 'Project info', icon: FileText, role: 'admin' },
    { to: '/admin/code', label: 'Python code', icon: Code2, role: 'admin' },
    { to: '/admin/operations', label: 'Operations', icon: ScrollText, role: 'admin' },
  ] },
]

interface Health { status: string; database: boolean; models_missing: string[]; last_pipeline_run?: { overall: string; finished_at: string } }

function ThemeToggle() {
  const [theme, setTheme] = useLocalState<'light' | 'dark' | 'system'>('civic.theme', 'system')
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
  }, [theme])
  const next = theme === 'dark' ? 'light' : 'dark'
  const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)
  return (
    <button onClick={() => setTheme(next)} aria-label="Toggle colour theme" title="Toggle colour theme"
      className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-ink">
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const health = useApi<Health>('/api/health')
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  const nav = useNavigate()
  useEffect(() => setOpen(false), [loc.pathname])

  const sidebar = (
    <nav className="flex h-full flex-col gap-6 overflow-y-auto p-4">
      <Link to="/" className="flex items-center gap-2.5 px-2">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-accent-ink"><Boxes size={17} /></span>
        <span className="leading-tight">
          <span className="block text-sm font-semibold text-ink">Civic Open-Data</span>
          <span className="block text-[11px] text-muted">Public accountability dashboard</span>
        </span>
      </Link>
      {NAV.map(group => {
        const items = group.items.filter(i => hasRole(user, i.role))
        if (!items.length) return null
        return (
          <div key={group.section}>
            <div className="mb-1.5 px-2 text-[11px] font-semibold tracking-wide text-muted uppercase">{group.section}</div>
            <ul className="space-y-0.5">
              {items.map(i => (
                <li key={i.to}>
                  <NavLink to={i.to} end={i.to === '/'}
                    className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition ${isActive ? 'bg-accent/10 font-medium text-accent' : 'text-ink-2 hover:bg-surface-2 hover:text-ink'}`}>
                    <i.icon size={16} /> {i.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
      <div className="mt-auto rounded-lg border border-line p-3 text-xs">
        <div className="text-muted">Signed in as</div>
        <div className="font-medium text-ink">{user.name}</div>
        <div className="mb-2 text-muted">Role: {ROLE_LABEL[user.role]}</div>
        {user.role === 'public'
          ? <Link to="/login" className="inline-flex items-center gap-1.5 font-medium text-accent"><LogIn size={14} /> Sign in (policy / admin)</Link>
          : <button onClick={() => { logout(); nav('/') }} className="inline-flex items-center gap-1.5 font-medium text-accent"><LogOut size={14} /> Sign out</button>}
      </div>
    </nav>
  )

  const h = health.data
  const degraded = health.error || (h && h.status !== 'ok')
  return (
    <div className="min-h-screen bg-page">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-surface lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 bg-surface">{sidebar}</aside>
        </div>
      )}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-line bg-surface/90 px-4 py-2.5 backdrop-blur sm:px-6">
          <button className="rounded-lg p-2 text-ink lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">{open ? <X size={18} /> : <Menu size={18} />}</button>
          <div className="flex items-center gap-2 text-xs text-muted">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: degraded ? 'var(--warning)' : 'var(--good)' }} />
            {health.error ? 'API offline' : h ? (h.status === 'ok' ? 'All data & models healthy' : 'Degraded mode') : 'Checking…'}
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden rounded-full bg-surface-2 px-2.5 py-1 text-xs text-ink-2 sm:inline">{ROLE_LABEL[user.role]}</span>
            <ThemeToggle />
          </div>
        </header>
        {degraded && (
          <div className="border-b border-line bg-[color:var(--warning)]/12 px-4 py-2 text-xs text-ink sm:px-6">
            {health.error
              ? 'The API server is not reachable. Start it with: uvicorn backend.app.main:app --port 8000'
              : `Running in degraded mode${h?.models_missing.length ? ` — models missing: ${h.models_missing.join(', ')}` : ''}${!h?.database ? ' — analytics database missing' : ''}${h?.last_pipeline_run && h.last_pipeline_run.overall !== 'ok' ? ' — last pipeline run did not fully succeed (some data may be stale)' : ''}. Unaffected sections keep working.`}
          </div>
        )}
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
          <Outlet />
        </main>
        <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-muted sm:px-6">
          Data: data.gov.in (crop, rainfall, NCRB), Open-Meteo, public diabetes dataset. Analyses show associations, not causes.
          If you or someone you know is struggling, call <b className="text-ink-2">Tele-MANAS 14416</b> (24x7, free).
        </footer>
      </div>
    </div>
  )
}
