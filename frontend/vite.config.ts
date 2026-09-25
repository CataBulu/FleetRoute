import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the API runs separately on :8000 (uvicorn); Vite proxies to it.
// In production Starlette serves the built files and the API from one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.PORT) || 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
