import { useAuth } from './useAuth';

export type UserRole = 'admin' | 'editor' | 'reader';
export type UserScope = 'rag:read' | 'rag:write' | 'admin:users' | 'admin:tenants';

/**
 * useRBAC - Role-Based Access Control
 * - hasRole(role): check if user has specific role
 * - hasScope(scope): check if user has specific scope (future)
 * - isAdmin: shortcut for hasRole('admin')
 */
export function useRBAC() {
  const { user } = useAuth();

  const hasRole = (role: UserRole): boolean => {
    if (!user?.role) return false;
    return user.role === role;
  };

  const hasScope = (scope: UserScope): boolean => {
    if (user?.role === 'admin') return true;
    return false;
  };

  return {
    hasRole,
    hasScope,
    isAdmin: hasRole('admin'),
    isEditor: hasRole('editor'),
    isReader: hasRole('reader'),
  };
}
