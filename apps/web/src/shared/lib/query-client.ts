import { QueryClient } from '@tanstack/react-query';

/**
 * Centralized QueryClient with defaults from architecture rules:
 * - staleTime: 30s (data fresh for 30s)
 * - gcTime: 5min (cache kept for 5min after last use)
 * - retry: 1 (single retry on failure)
 * - refetchOnWindowFocus: false (avoid unnecessary refetches)
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // 30s
      gcTime: 5 * 60_000, // 5min
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 1,
    },
  },
});
