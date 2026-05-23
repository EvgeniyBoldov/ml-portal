/**
 * Platform Settings hooks
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  platformSettingsApi,
  executionLimitsApi,
  orchestrationApi,
  systemLLMRolesApi,
  type PlatformSettings,
  type PlatformSettingsUpdate,
  type OrchestrationSettings,
  type ExecutorSettingsUpdate,
  type PlannerRoleUpdate,
  type SynthesizerRoleUpdate,
  type FactExtractorRoleUpdate,
  type SummaryCompactorRoleUpdate,
  type ExecutionLimits,
  type ExecutionLimitsUpdate,
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

export function usePlatformExecutionLimits() {
  return useQuery({
    queryKey: ['admin', 'execution-limits', 'platform'],
    queryFn: () => executionLimitsApi.getPlatform(),
    staleTime: 30_000,
  });
}

export function useUpdatePlatformExecutionLimits() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: ExecutionLimitsUpdate): Promise<ExecutionLimits> =>
      executionLimitsApi.updatePlatform(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'execution-limits', 'platform'] });
      showSuccess('Лимиты платформы обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

export function useAgentExecutionLimits(agentSlug?: string) {
  return useQuery({
    queryKey: ['admin', 'execution-limits', 'agent', agentSlug ?? ''],
    queryFn: () => executionLimitsApi.getAgent(agentSlug || ''),
    enabled: Boolean(agentSlug),
    staleTime: 30_000,
  });
}

export function useUpdateAgentExecutionLimits(agentSlug?: string) {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: ExecutionLimitsUpdate): Promise<ExecutionLimits> => {
      if (!agentSlug) {
        return Promise.reject(new Error('agent slug is required'));
      }
      return executionLimitsApi.updateAgent(agentSlug, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'execution-limits', 'agent', agentSlug ?? ''] });
      showSuccess('Лимиты агента обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

export function useOrchestratorExecutionLimits(role?: string) {
  return useQuery({
    queryKey: ['admin', 'execution-limits', 'orchestrator', role ?? ''],
    queryFn: () => executionLimitsApi.getOrchestrator(role || ''),
    enabled: Boolean(role),
    staleTime: 30_000,
  });
}

export function useUpdateOrchestratorExecutionLimits(role?: string) {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: ExecutionLimitsUpdate): Promise<ExecutionLimits> => {
      if (!role) {
        return Promise.reject(new Error('orchestrator role is required'));
      }
      return executionLimitsApi.updateOrchestrator(role, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'execution-limits', 'orchestrator', role ?? ''] });
      showSuccess('Лимиты оркестратора обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

// === SystemLLMRole Hooks ===

export function useActivePlannerRole() {
  return useQuery({
    queryKey: ['system-llm-roles', 'active', 'planner'],
    queryFn: () => systemLLMRolesApi.getActive('planner'),
    staleTime: 30_000,
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

export function useActiveSynthesizerRole() {
  return useQuery({
    queryKey: qk.admin.systemLlmRoles.active('synthesizer'),
    queryFn: () => systemLLMRolesApi.getActive('synthesizer'),
    staleTime: 30_000,
  });
}

export function useActiveFactExtractorRole() {
  return useQuery({
    queryKey: qk.admin.systemLlmRoles.active('fact_extractor'),
    queryFn: () => systemLLMRolesApi.getActive('fact_extractor'),
    staleTime: 30_000,
  });
}

export function useActiveSummaryCompactorRole() {
  return useQuery({
    queryKey: qk.admin.systemLlmRoles.active('summary_compactor'),
    queryFn: () => systemLLMRolesApi.getActive('summary_compactor'),
    staleTime: 30_000,
  });
}

export function useUpdateSynthesizerRole() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: SynthesizerRoleUpdate) => systemLLMRolesApi.updateSynthesizer(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.systemLlmRoles.active('synthesizer') });
      showSuccess('Настройки Synthesizer обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

export function useUpdateFactExtractorRole() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: FactExtractorRoleUpdate) => systemLLMRolesApi.updateFactExtractor(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.systemLlmRoles.active('fact_extractor') });
      showSuccess('Настройки Fact Extractor обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

export function useUpdateSummaryCompactorRole() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: SummaryCompactorRoleUpdate) => systemLLMRolesApi.updateSummaryCompactor(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.systemLlmRoles.active('summary_compactor') });
      showSuccess('Настройки Summary Compactor обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}
