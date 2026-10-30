import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LogIn } from 'lucide-react'
import { Button, Card, ErrorBox, Field, Input } from '../components/ui'
import { useAuth } from '../lib/auth'

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await login(username, password)
      nav('/problem')
    } catch (err) {
      setError((err as Error).message)
    } finally { setBusy(false) }
  }

  return (
    <div className="mx-auto mt-8 max-w-md">
      <Card>
        <h1 className="text-xl font-semibold text-ink">Sign in</h1>
        <p className="mt-1 mb-5 text-sm text-ink-2">Public dashboards need no account. Sign in for policy-maker analytics or administration.</p>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Username"><Input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" required /></Field>
          <Field label="Password"><Input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" required /></Field>
          {error && <ErrorBox message={error} />}
          <Button type="submit" disabled={busy} className="w-full"><LogIn size={16} /> {busy ? 'Signing in…' : 'Sign in'}</Button>
        </form>
        <div className="mt-5 rounded-lg bg-surface-2 p-3 text-xs text-ink-2">
          <div className="mb-1 font-medium text-ink">Demo accounts</div>
          <div>Policy maker: <code>policy</code> / <code>policy@123</code></div>
          <div>Admin: <code>admin</code> / <code>admin@123</code></div>
        </div>
      </Card>
    </div>
  )
}
