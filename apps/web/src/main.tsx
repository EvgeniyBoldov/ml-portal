import React from 'react';
import ReactDOM from 'react-dom/client';
import { AppProviders } from './app/AppProviders';
import AppRouter from './app/router';
import { initTheme } from './shared/lib/theme';
import './shared/ui/tokens.css';
import './shared/ui/themes/light.css';
import './shared/ui/themes/dark.css';
import './theme.css';

// Initialize theme before rendering
initTheme();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppProviders>
      <AppRouter />
    </AppProviders>
  </React.StrictMode>
);
