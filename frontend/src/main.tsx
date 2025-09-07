import React from 'react'
import ReactDOM from 'react-dom/client'
import AppRouter from './app/router'
import './theme.css'

// Load mocks conditionally without top-level await (side-effect import)
if ((import.meta as any).env?.VITE_USE_MOCKS === 'true') {
  // fire-and-forget dynamic import; side effects in the module will patch fetch
  import('./mocks/enableMocks')
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppRouter />
  </React.StrictMode>
)
