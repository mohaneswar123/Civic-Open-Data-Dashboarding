import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Loading } from './components/ui'
import { AuthProvider, hasRole, useAuth, type Role } from './lib/auth'
import Home from './pages/Home'
import Login from './pages/Login'

const Dashboards = lazy(() => import('./pages/Dashboards'))
const Advanced = lazy(() => import('./pages/Advanced'))
const Predictions = lazy(() => import('./pages/Predictions'))
const Models = lazy(() => import('./pages/Models'))
const Architecture = lazy(() => import('./pages/admin/Architecture'))
const Datasets = lazy(() => import('./pages/admin/Datasets'))
const ProjectInfo = lazy(() => import('./pages/admin/ProjectInfo'))
const Code = lazy(() => import('./pages/admin/Code'))
const Operations = lazy(() => import('./pages/admin/Operations'))

/** UI guard for navigation only - the API enforces the same roles server-side. */
function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, ready } = useAuth()
  if (!ready) return <Loading />
  if (!hasRole(user, role)) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Home />} />
              <Route path="login" element={<Login />} />
              <Route path="dashboards" element={<Dashboards />} />
              <Route path="predictions" element={<Predictions />} />
              <Route path="models" element={<Models />} />
              <Route path="advanced" element={<RequireRole role="policy"><Advanced /></RequireRole>} />
              <Route path="admin">
                <Route path="architecture" element={<RequireRole role="admin"><Architecture /></RequireRole>} />
                <Route path="datasets" element={<RequireRole role="admin"><Datasets /></RequireRole>} />
                <Route path="project" element={<RequireRole role="admin"><ProjectInfo /></RequireRole>} />
                <Route path="code" element={<RequireRole role="admin"><Code /></RequireRole>} />
                <Route path="operations" element={<RequireRole role="admin"><Operations /></RequireRole>} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  )
}
