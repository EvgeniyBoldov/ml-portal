import React from 'react'
import ReactDOM from 'react-dom/client'
import AppRouter from './app/router'
import './theme.css'

if ((import.meta as any).env?.VITE_USE_MOCKS === 'true') {
  import('./mocks/enableMocks')
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppRouter />
  </React.StrictMode>
)
