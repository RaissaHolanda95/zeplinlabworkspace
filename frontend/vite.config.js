import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    hmr: { overlay: false },
    // Evita polling que pode disparar reconexões/HMR desnecessários ao alternar janelas.
    watch: { usePolling: false },
  },
})
