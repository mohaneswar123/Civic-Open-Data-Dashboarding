import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, getToken, post, setToken } from './api'

export type Role = 'public' | 'policy' | 'admin'
export interface User { username: string; role: Role; name: string }

const RANK: Record<Role, number> = { public: 0, policy: 1, admin: 2 }
export const hasRole = (user: User, min: Role) => RANK[user.role] >= RANK[min]
export const ROLE_LABEL: Record<Role, string> = { public: 'Public', policy: 'Policy maker', admin: 'Admin' }

const PUBLIC: User = { username: 'anonymous', role: 'public', name: 'Public visitor' }

interface AuthState {
  user: User
  ready: boolean
  login: (username: string, password: string) => Promise<User>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User>(PUBLIC)
  const [ready, setReady] = useState(false)

  const logout = useCallback(() => { setToken(null); setUser(PUBLIC) }, [])

  useEffect(() => {
    // Re-validate a stored token with the server (role comes from the server, never from local storage).
    if (!getToken()) { setReady(true); return }
    api<User>('/api/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
  }, [])

  useEffect(() => {
    const onUnauthorized = () => logout()
    window.addEventListener('civic:unauthorized', onUnauthorized)
    return () => window.removeEventListener('civic:unauthorized', onUnauthorized)
  }, [logout])

  const login = async (username: string, password: string) => {
    const res = await post<{ access_token: string; user: User }>('/api/auth/login', { username, password })
    setToken(res.access_token)
    setUser(res.user)
    return res.user
  }

  return <AuthContext.Provider value={{ user, ready, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
