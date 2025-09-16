import { useAuthStore } from '@/entities/auth/model/auth.store';

export type User = { id: string; login?: string; fio?: string; role?: string };

export const useAuth = () => {
  const authStore = useAuthStore();

  return {
    user: authStore.user,
    loading: false, // authStore doesn't have loading state
    error: null, // authStore doesn't have error state
    login: authStore.login,
    fetchMe: async () => {
      try {
        await authStore.hydrate();
        return authStore.user;
      } catch {
        return null;
      }
    },
    logout: authStore.logout,
  };
};
