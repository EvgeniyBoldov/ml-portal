import React from 'react'
import ReactDOM from 'react-dom/client'
import AppRouter from './app/router'
import './theme.css'

// Initialize auth tokens from localStorage
const initAuthTokens = () => {
  const token = localStorage.getItem('access_token');
  if (token) {
    (window as any).__auth_tokens = { access_token: token };
  }
};

initAuthTokens();

if ((import.meta as any).env?.VITE_USE_MOCKS === 'true') {
  import('./mocks/enableMocks')
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppRouter />
  </React.StrictMode>
)
