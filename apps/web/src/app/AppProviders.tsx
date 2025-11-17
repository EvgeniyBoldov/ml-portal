import React from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '@/shared/lib/query-client';
import { ToastProvider } from '@/shared/ui/Toast';
import { GlobalConfirmDialog } from './providers/GlobalConfirmDialog';
import { AuthProvider } from './providers/AuthProvider';
import { ErrorBoundary } from './components/ErrorBoundary';
import { SSEProvider } from './providers/SSEProvider';

interface AppProvidersProps {
  children: React.ReactNode;
}

/**
 * AppProviders - top-level provider composition
 * Order matters:
 * 1. ErrorBoundary (catches all errors)
 * 2. QueryClientProvider (server state)
 * 3. AuthProvider (hydrates user session)
 * 4. SSEProvider (real-time updates for RAG documents)
 * 5. ToastProvider (notifications)
 * 6. GlobalConfirmDialog (global modals)
 */
export function AppProviders({ children }: AppProvidersProps) {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <SSEProvider>
            <ToastProvider>
              <GlobalConfirmDialog />
              {children}
            </ToastProvider>
          </SSEProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
