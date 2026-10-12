// Thin fetch wrapper: attaches the JWT, turns HTTP errors into readable messages.

const TOKEN_KEY = 'civic.token'

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t: string | null) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* private mode */ }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  let res: Response
  try {
    res = await fetch(path, { ...init, headers })
  } catch {
    throw new ApiError(0, 'Cannot reach the API server. Is the backend running on port 8000?')
  }
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      msg = typeof body.detail === 'string' ? body.detail
        : Array.isArray(body.detail) ? body.detail.map((d: { loc?: string[]; msg: string }) => `${d.loc?.slice(-1)[0] ?? ''}: ${d.msg}`).join('; ')
        : msg
    } catch { /* not JSON */ }
    if (res.status === 401 && token) window.dispatchEvent(new Event('civic:unauthorized'))
    throw new ApiError(res.status, msg)
  }
  return res.json() as Promise<T>
}

export const post = <T,>(path: string, body: unknown) => api<T>(path, { method: 'POST', body: JSON.stringify(body) })
