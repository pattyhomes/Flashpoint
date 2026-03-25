import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Port and backend proxy target are overridden by the desktop launcher
// (VITE_PORT, VITE_BACKEND_PORT) when running the orchestrated desktop path.
// Standalone `npm run dev` uses the defaults below (5173, 8000).
const port = parseInt(process.env.VITE_PORT ?? '5173')
const backendPort = parseInt(process.env.VITE_BACKEND_PORT ?? '8000')

export default defineConfig({
  plugins: [react()],
  server: {
    port,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
})
