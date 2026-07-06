import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,       // pin the dev port so the OAuth redirect target is predictable
    strictPort: true, // fail loudly if 5173 is taken, instead of silently using 5174
    // Forward backend paths to :8000 so the browser sees a single origin.
    // This keeps the OAuth session cookie first-party (no cross-origin loss).
    proxy: {
      '/api': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
    },
  },
})
