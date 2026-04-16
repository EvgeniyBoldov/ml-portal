/**
 * Platform Settings hooks
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  platformSettingsApi,
  orchestrationApi,
  systemLLMRolesApi,
  type PlatformSettings,
  type PlatformSettingsUpdate,
  type OrchestrationSettings,
  type ExecutorSettingsUpdate,
  type SystemLLMRole,
  type TriageRoleUpdate,
  type PlannerRoleUpdate,
  type SummaryRoleUpdate,
  type MemoryRoleUpdate,
} from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

export function usePlatformSettings() {
  return useQuery({
    queryKey: qk.platform.settings(),
    queryFn: () => platformSettingsApi.get(),
    staleTime: 30_000,
  });
}

export function useOrchestrationSettings() {
  return useQuery({
    queryKey: qk.admin.orchestration.settings(),
    queryFn: () => orchestrationApi.get(),
    staleTime: 30_000,
  });
}

export function useUpdateOrchestrationSettings() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: ExecutorSettingsUpdate): Promise<OrchestrationSettings> =>
      orchestrationApi.updateExecutor(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.orchestration.all() });
      showSuccess('Настройки оркестрации обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

export function useUpdatePlatformSettings() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: PlatformSettingsUpdate) => platformSettingsApi.update(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.platform.settings() });
      showSuccess('Настройки платформы обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

// === SystemLLMRole Hooks ===

export function useActiveTriageRole() {
  return useQuery({
    queryKey: ['system-llm-roles', 'active', 'triage'],
    queryFn: () => systemLLMRolesApi.getActive('triage'),
    staleTime: 30_000,
  });
}

export function useActivePlannerRole() {
  return useQuery({
    queryKey: ['system-llm-roles', 'active', 'planner'],
    queryFn: () => systemLLMRolesApi.getActive('planner'),
    staleTime: 30_000,
  });
}

export function useActiveSummaryRole() {
  return useQuery({
    queryKey: ['system-llm-roles', 'active', 'summary'],
    queryFn: () => systemLLMRolesApi.getActive('summary'),
    staleTime: 30_000,
  });
}

export function useActiveMemoryRole() {
  return useQuery({
    queryKey: ['system-llm-roles', 'active', 'memory'],
    queryFn: () => systemLLMRolesApi.getActive('memory'),
    staleTime: 30_000,
  });
}

export function useUpdateTriageRole() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: TriageRoleUpdate) => systemLLMRolesApi.updateTriage(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-llm-roles', 'active', 'triage'] });
      showSuccess('Настройки Triage обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

export function useUpdatePlannerRole() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: PlannerRoleUpdate) => systemLLMRolesApi.updatePlanner(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-llm-roles', 'active', 'planner'] });
      showSuccess('Настройки Planner обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

export function useUpdateSummaryRole() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: SummaryRoleUpdate) => systemLLMRolesApi.updateSummary(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-llm-roles', 'active', 'summary'] });
      showSuccess('Настройки Summary обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

export function useUpdateMemoryRole() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: MemoryRoleUpdate) => systemLLMRolesApi.updateMemory(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-llm-roles', 'active', 'memory'] });
      showSuccess('Настройки Memory обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}
