import React, { lazy, Suspense } from 'react';
import { Navigate } from 'react-router-dom';
import { useRBAC } from '@shared/hooks/useRBAC';
import { useAuth } from '@shared/hooks/useAuth';

const Forbidden = lazy(() => import('@/domains/common/pages/Forbidden'));

interface AdminGuardProps {
  children: React.ReactNode;
}

/**
 * AdminGuard - protects admin routes
 * - Redirects to /gpt/chat if user is not admin
 * - Shows 403 page if authenticated but not admin
 * - Waits for auth to be ready before checking
 */
export function AdminGuard({ children }: AdminGuardProps) {
  const { isAuthReady, isAuthenticated } = useAuth();
  const { isAdmin } = useRBAC();

  // Wait for auth to hydrate
  if (!isAuthReady) {
    return <div className="admin-guard-loading">Загрузка...</div>;
  }

  // Not authenticated → redirect to login (handled by GPTGate)
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Authenticated but not admin → 403
  if (!isAdmin) {
    return (
      <Suspense fallback={<div />}>
        <Forbidden />
      </Suspense>
    );
  }

  // Admin → render children
  return <>{children}</>;
}
