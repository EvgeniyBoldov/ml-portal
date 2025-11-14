import { create } from 'zustand';
import {
  apiRequest,
  setAuthTokens,
  clearAuthTokens,
  refreshAccessToken,
} from '@/shared/api/http';
import type { User, LoginResponse } from '@/shared/api/types';

type AuthState = {
  user: User | null;
  isAuthReady: boolean;
  loading: boolean;
  error: string | null;
  login: (login: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
};

export const useAuthStore = create<AuthState>()((set, _get) => ({
  user: null,
  isAuthReady: false,
  loading: false,
  error: null,
  async login(login, password) {
    set({ loading: true, error: null });
    try {
      const data = await apiRequest<LoginResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ login, password }),
      });
      // Tokens are in httpOnly cookies, just save access_token to memory
      setAuthTokens({ access_token: data.access_token });
      set({ user: data.user, loading: false, error: null, isAuthReady: true });
    } catch (error: any) {
      set({ loading: false, error: error.message || 'Ошибка входа' });
      throw error;
    }
  },
  async logout() {
    try {
      await apiRequest<void>('/auth/logout', { method: 'POST' });
    } catch {
      // Ignore logout errors
    }
    clearAuthTokens();
    set({ user: null, isAuthReady: true });
  },
  async hydrate() {
    try {
      const me = await apiRequest<User>('/auth/me', { method: 'GET' });
      set({ user: me, isAuthReady: true });
    } catch {
      try {
        await refreshAccessToken();
        const me = await apiRequest<User>('/auth/me', { method: 'GET' });
        set({ user: me, isAuthReady: true });
      } catch {
        clearAuthTokens();
        set({ user: null, isAuthReady: true });
      }
    }
  },
}));
