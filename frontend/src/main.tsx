import React from 'react'
import ReactDOM from 'react-dom/client'
import AppRouter from './app/router'
import './theme.css'

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'
if (USE_MOCKS) {
  await import('./mocks/enableMocks')
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppRouter />
  </React.StrictMode>
)
