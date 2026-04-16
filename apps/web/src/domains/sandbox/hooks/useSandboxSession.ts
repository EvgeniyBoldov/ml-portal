/**
 * TanStack Query hooks for sandbox sessions.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { sandboxApi } from '../api';
import type { SandboxSessionCreate, SandboxSessionUpdate } from '../types';

export function useSandboxSessions(params?: { status?: string }) {
  return useQuery({
    queryKey: qk.sandbox.sessions.list(params),
    queryFn: () => sandboxApi.listSessions(params),
    staleTime: 30_000,
  });
}

export function useSandboxSession(id: string | undefined) {
  return useQuery({
    queryKey: qk.sandbox.sessions.detail(id!),
    queryFn: () => sandboxApi.getSession(id!),
    enabled: !!id,
    staleTime: 15_000,
  });
}

export function useCreateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: SandboxSessionCreate) => sandboxApi.createSession(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.sandbox.sessions.all() });
    },
  });
}

export function useUpdateSession(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: SandboxSessionUpdate) =>
      sandboxApi.updateSession(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.sandbox.sessions.detail(id) });
      qc.invalidateQueries({ queryKey: qk.sandbox.sessions.all() });
    },
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => sandboxApi.deleteSession(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.sandbox.sessions.all() });
    },
  });
}
