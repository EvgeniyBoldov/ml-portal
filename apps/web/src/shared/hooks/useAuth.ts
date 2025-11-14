import { useAuthStore } from '@/entities/auth/model/auth.store';

/**
 * useAuth - access to auth state and actions
 * - user: current user or null
 * - isAuthenticated: true if user is logged in
 * - login, logout, hydrate: auth actions
 */
export function useAuth() {
  const user = useAuthStore(state => state.user);
  const loading = useAuthStore(state => state.loading);
  const error = useAuthStore(state => state.error);
  const login = useAuthStore(state => state.login);
  const logout = useAuthStore(state => state.logout);
  const hydrate = useAuthStore(state => state.hydrate);
  const isAuthReady = useAuthStore(state => state.isAuthReady);

  return {
    user,
    isAuthenticated: !!user,
    isAuthReady,
    loading,
    error,
    login,
    logout,
    hydrate,
  };
}
