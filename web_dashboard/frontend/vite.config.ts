import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev: `pnpm dev` proxies /api to the FastAPI server on :8501.
// Prod: `pnpm build` emits dist/, which web_dashboard/server.py serves.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8501' },
  },
  build: {
    chunkSizeWarningLimit: 900,
  },
})
