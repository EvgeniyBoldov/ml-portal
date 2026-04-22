import React from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '@/shared/lib/query-client';
import { ToastProvider } from '@/shared/ui/Toast';
import { GlobalConfirmDialog } from './providers/GlobalConfirmDialog';
import { AuthProvider } from './providers/AuthProvider';
import ErrorBoundary from '@/shared/ui/ErrorBoundary';
import { ThemeProvider } from './providers/ThemeProvider';

interface AppProvidersProps {
  children: React.ReactNode;
}

/**
 * AppProviders - top-level provider composition
 * Order matters:
 * 1. ErrorBoundary (catches all errors)
 * 2. ThemeProvider (theme context, must be early for CSS vars)
 * 3. QueryClientProvider (server state)
 * 4. AuthProvider (hydrates user session)
 * 5. ToastProvider (notifications)
 * 6. GlobalConfirmDialog (global modals)
 */
export function AppProviders({ children }: AppProvidersProps) {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ToastProvider>
              <GlobalConfirmDialog />
              {children}
            </ToastProvider>
          </AuthProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
