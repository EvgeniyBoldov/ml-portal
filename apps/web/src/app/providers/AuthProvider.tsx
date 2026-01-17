import React, { useEffect, useCallback } from 'react';
import { useAuth } from '@/shared/hooks/useAuth';
import { setOnAuthFailure, clearAuthTokens } from '@/shared/api/http';

interface AuthProviderProps {
  children: React.ReactNode;
}

/**
 * AuthProvider - hydrates user on mount
 * - Calls hydrate() to restore session from refresh token
 * - Does NOT block rendering (children render immediately)
 * - Auth state is available via useAuth() hook
 * - Sets up global auth failure handler for redirect to login
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const { hydrate, isAuthReady, logout } = useAuth();

  // Handle auth failure - redirect to login without throwing errors
  const handleAuthFailure = useCallback(() => {
    clearAuthTokens();
    // Don't redirect if already on login page (prevents infinite loop)
    if (window.location.pathname === '/login' || window.location.pathname === '/') {
      return;
    }
    // Use window.location for clean redirect (avoids React Router issues)
    window.location.href = '/login';
  }, []);

  useEffect(() => {
    // Set up global auth failure handler
    setOnAuthFailure(handleAuthFailure);
  }, [handleAuthFailure]);

  useEffect(() => {
    if (!isAuthReady) {
      hydrate();
    }
  }, [hydrate, isAuthReady]);

  // Render children immediately (no blocking)
  return <>{children}</>;
}
