import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// /api is proxied to the FastAPI backend so the browser sees one origin.
// API_PORT (default 8000) lets a second copy run against another backend.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {}
const apiPort = env.API_PORT ?? '8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { '/api': `http://127.0.0.1:${apiPort}` } },
})
