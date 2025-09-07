// Пример dev-прокси. Подключается вручную: импортируй объект в vite.config.ts
// и передай как server.proxy. Например:
// import proxy from './vite.proxy.example'
// export default defineConfig({ server: { proxy } })
export default {
  '/api': {
    target: 'http://localhost:8000',
    changeOrigin: true,
    secure: false
  }
}
