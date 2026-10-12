import { useMemo, useState } from 'react'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import { FileCode2, Folder } from 'lucide-react'
import { Card, Gate, PageHeader } from '../../components/ui'
import { useApi } from '../../lib/hooks'

hljs.registerLanguage('python', python)

interface Tree { group: string; files: { path: string; lines: number }[] }
const GROUP_LABEL: Record<string, string> = { pipeline: 'Data cleaning pipeline', ml: 'ML training', backend: 'API backend', tests: 'Tests' }

export default function Code() {
  const tree = useApi<Tree[]>('/api/admin/code')
  const [path, setPath] = useState('pipeline/run.py')
  const file = useApi<{ path: string; content: string }>(`/api/admin/code/file?path=${encodeURIComponent(path)}`)
  const html = useMemo(() => file.data ? hljs.highlight(file.data.content, { language: 'python' }).value : '', [file.data])
  return (
    <div>
      <PageHeader title="Python code" subtitle="Read-only view of the data-cleaning, ML-training and API source code. Run locally with: python run_all.py" />
      <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
        <Card className="h-fit !p-3">
          <Gate state={tree}>{t => (
            <nav className="space-y-4">
              {t.map(g => (
                <div key={g.group}>
                  <div className="mb-1 flex items-center gap-1.5 px-1 text-xs font-semibold text-ink-2"><Folder size={13} /> {GROUP_LABEL[g.group] ?? g.group}</div>
                  <ul>
                    {g.files.filter(f => f.lines > 0).map(f => (
                      <li key={f.path}>
                        <button onClick={() => setPath(f.path)}
                          className={`flex w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-left text-xs ${f.path === path ? 'bg-accent/10 font-medium text-accent' : 'text-ink-2 hover:bg-surface-2'}`}>
                          <span className="flex items-center gap-1.5 truncate"><FileCode2 size={12} /> {f.path.split('/').slice(1).join('/')}</span>
                          <span className="text-[10px] text-muted">{f.lines}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </nav>
          )}</Gate>
        </Card>
        <Card className="min-w-0 !p-0">
          <div className="border-b border-line px-4 py-2 font-mono text-xs text-ink-2">{path}</div>
          <Gate state={file}>{f => (
            <div className="max-h-[75vh] overflow-auto">
              <table className="w-full font-mono text-[12.5px] leading-5">
                <tbody>
                  {html.split('\n').map((line, i) => (
                    <tr key={i}>
                      <td className="w-12 pr-3 text-right text-muted select-none align-top">{i + 1}</td>
                      <td className="pr-4 whitespace-pre"><code className="hljs" dangerouslySetInnerHTML={{ __html: line || ' ' }} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <span className="sr-only">{f.path}</span>
            </div>
          )}</Gate>
        </Card>
      </div>
    </div>
  )
}
