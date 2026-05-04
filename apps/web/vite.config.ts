import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'
import path from 'node:path'

export default defineConfig(({ command, mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), '')
  
  return {
    plugins: [react(), tsconfigPaths()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
        '@app': path.resolve(__dirname, 'src/app'),
        '@shared': path.resolve(__dirname, 'src/shared'),
        '@domains': path.resolve(__dirname, 'src/domains'),
        '@entities': path.resolve(__dirname, 'src/entities'),
      },
    },
    server: {
      host: true, // Listen on all addresses
      port: Number(env.VITE_PORT) || 5173,
      strictPort: false,
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        },
      },
    },
    preview: {
      host: true, // Listen on all addresses
      port: Number(env.VITE_PREVIEW_PORT) || 4173,
      strictPort: false,
    },
    build: {
      sourcemap: env.VITE_SOURCEMAP === 'true',
      minify: 'esbuild',
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom'],
            router: ['react-router-dom'],
            query: ['@tanstack/react-query'],
            zustand: ['zustand'],
          },
        },
      },
    },
    define: {
      __APP_VERSION__: JSON.stringify(env.VITE_APP_VERSION || '1.0.0'),
      __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
    },
  }
})