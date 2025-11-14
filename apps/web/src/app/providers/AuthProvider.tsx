import React, { useEffect } from 'react';
import { useAuth } from '@/shared/hooks/useAuth';

interface AuthProviderProps {
  children: React.ReactNode;
}

/**
 * AuthProvider - hydrates user on mount
 * - Calls hydrate() to restore session from refresh token
 * - Does NOT block rendering (children render immediately)
 * - Auth state is available via useAuth() hook
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const { hydrate, isAuthReady } = useAuth();

  useEffect(() => {
    if (!isAuthReady) {
      hydrate();
    }
  }, [hydrate, isAuthReady]);

  // Render children immediately (no blocking)
  return <>{children}</>;
}
