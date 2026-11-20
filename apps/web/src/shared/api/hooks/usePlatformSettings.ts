/**
 * Platform Settings hooks
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  platformSettingsApi,
  executionLimitsApi,
  
  systemLLMRolesApi,
  type PlatformSettingsUpdate,
  
  
  
  
  
  
  
  type DocumentMemoryExtractorRoleUpdate,
  type ActorLimits,
  type ActorLimitsResolution,
  type OrchestratorRoleSettingsUpdate,
  type OrchestratorRoleSettingsResult,
  type RuntimeLimits,
  type SystemLLMRoleType,
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

export function useFillPlatformSettingsDefaults() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: () => platformSettingsApi.fillDefaults(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.platform.settings() });
      showSuccess('Пустые поля заполнены значениями по умолчанию');
    },
    onError: (err: Error) => showError(err.message),
  });
}

export function usePlatformExecutionLimits() {
  return useQuery({
    queryKey: ['admin', 'execution-limits', 'runtime'],
    queryFn: () => executionLimitsApi.getRuntime(),
    staleTime: 30_000,
  });
}

export function useUpdatePlatformExecutionLimits() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: RuntimeLimits): Promise<RuntimeLimits> => executionLimitsApi.updateRuntime(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'execution-limits', 'runtime'] });
      showSuccess('Лимиты платформы обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

export function useAgentDefaultExecutionLimits() {
  return useQuery({ queryKey: ['admin', 'execution-limits', 'defaults', 'agents'], queryFn: () => executionLimitsApi.getAgentDefaults(), staleTime: 30_000 });
}

export function useUpdateAgentDefaultExecutionLimits() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ActorLimits) => executionLimitsApi.updateAgentDefaults(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'execution-limits', 'defaults', 'agents'] }),
  });
}

export function useOrchestratorDefaultExecutionLimits() {
  return useQuery({ queryKey: ['admin', 'execution-limits', 'defaults', 'orchestrators'], queryFn: () => executionLimitsApi.getOrchestratorDefaults(), staleTime: 30_000 });
}

export function useUpdateOrchestratorDefaultExecutionLimits() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ActorLimits) => executionLimitsApi.updateOrchestratorDefaults(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'execution-limits', 'defaults', 'orchestrators'] }),
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
    mutationFn: (data: ActorLimits): Promise<ActorLimitsResolution> => {
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


export function useUpdateOrchestratorRoleSettings(role: SystemLLMRoleType) {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  return useMutation({
    mutationFn: (data: OrchestratorRoleSettingsUpdate): Promise<OrchestratorRoleSettingsResult> =>
      systemLLMRolesApi.updateActiveSettings(role, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.systemLlmRoles.active(role) });
      queryClient.invalidateQueries({ queryKey: ['admin', 'execution-limits', 'orchestrator', role] });
      showSuccess('Настройки оркестратора обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}

// === SystemLLMRole Hooks ===

export function useActivePlannerRole() {
  return useQuery({
    queryKey: qk.admin.systemLlmRoles.active('planner'),
    queryFn: () => systemLLMRolesApi.getActive('planner'),
    staleTime: 30_000,
  });
}

export function useActiveTurnPreflightRole() {
  return useQuery({
    queryKey: qk.admin.systemLlmRoles.active('turn_preflight'),
    queryFn: () => systemLLMRolesApi.getActive('turn_preflight'),
    staleTime: 30_000,
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

export function useActiveFactCompactorRole() {
  return useQuery({
    queryKey: qk.admin.systemLlmRoles.active('fact_compactor'),
    queryFn: () => systemLLMRolesApi.getActive('fact_compactor'),
    staleTime: 30_000,
  });
}

export function useActiveDocumentMemoryExtractorRole() {
  return useQuery({
    queryKey: qk.admin.systemLlmRoles.active('document_memory_extractor'),
    queryFn: () => systemLLMRolesApi.getActive('document_memory_extractor'),
    staleTime: 30_000,
  });
}




export function useUpdateDocumentMemoryExtractorRole() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  return useMutation({
    mutationFn: (data: DocumentMemoryExtractorRoleUpdate) => systemLLMRolesApi.updateActive('document_memory_extractor', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.systemLlmRoles.active('document_memory_extractor') });
      showSuccess('Настройки изучателя документов обновлены');
    },
    onError: (err: Error) => showError(err.message),
  });
}
