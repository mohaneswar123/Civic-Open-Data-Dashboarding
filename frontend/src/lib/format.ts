const compact = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 })
const full = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export const fmtCompact = (v: number | null | undefined) => (v == null ? '—' : compact.format(v))
export const fmtInt = (v: number | null | undefined) => (v == null ? '—' : full.format(Math.round(v)))
export const fmt = (v: number | null | undefined, d = 2) => (v == null ? '—' : v.toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d }))
export const fmtPct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v.toFixed(d)}%`)
export const fmtSigned = (v: number | null | undefined, d = 1, unit = '') =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(d)}${unit}`
export const fmtP = (p: number | null | undefined) => (p == null ? '—' : p < 0.001 ? '<0.001' : p.toFixed(3))

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Export rows to a CSV download - every chart's data is also available as a file. */
export function downloadCsv(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return
  const cols = Object.keys(rows[0])
  const esc = (v: unknown) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = [cols.join(','), ...rows.map(r => cols.map(c => esc(r[c])).join(','))].join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  a.click()
  URL.revokeObjectURL(url)
}
