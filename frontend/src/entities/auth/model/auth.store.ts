import { create } from "zustand";
import { persist } from "zustand/middleware";
import { apiRequest, setAuthTokens, clearAuthTokens, refreshAccessToken } from "@/shared/api/http";
import type { User, LoginResponse, AuthTokens } from "@/shared/api/types";

type AuthState = {
  user: User | null;
  tokens: AuthTokens | null;
  isAuthReady: boolean;
  login: (login: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      tokens: null,
      isAuthReady: false,
      async login(login, password) {
        const data = await apiRequest<LoginResponse>("/auth/login", { method: "POST", body: JSON.stringify({ login, password }) });
        const tokens = { 
          access_token: data.access_token, 
          token_type: data.token_type,
          refresh_token: data.refresh_token, 
          expires_in: data.expires_in 
        };
        setAuthTokens(tokens);
        set({ tokens });
        set({ user: data.user });
      },
      async logout() {
        try { await apiRequest<void>("/auth/logout", { method: "POST" }); } catch {}
        clearAuthTokens();
        set({ tokens: null, user: null });
      },
      async hydrate() {
        try {
          const me = await apiRequest<User>("/auth/me", { method: "GET" });
          set({ user: me, isAuthReady: true });
        } catch {
          try {
            await refreshAccessToken();
            const me = await apiRequest<User>("/auth/me", { method: "GET" });
            set({ user: me, isAuthReady: true });
          } catch {
            clearAuthTokens();
            set({ user: null, tokens: null, isAuthReady: true });
          }
        }
      },
    }),
    { name: "auth-store", partialize: (s) => ({ tokens: s.tokens }) }
  )
);
