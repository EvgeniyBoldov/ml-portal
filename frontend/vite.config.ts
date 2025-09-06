import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'
import path from 'node:path'

// Aliases unified across Vite and TS: @app -> src/app, @shared -> src/shared
export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  resolve: {
    alias: {
      '@app': path.resolve(__dirname, 'src/app'),
      '@shared': path.resolve(__dirname, 'src/shared'),
    }
  },
  server: { port: 5173, strictPort: true },
  preview: { port: 4173, strictPort: true }
})
