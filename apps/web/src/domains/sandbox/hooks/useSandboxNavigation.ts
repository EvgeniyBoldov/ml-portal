import { useMemo } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { systemLLMRolesApi } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import { sandboxApi } from '../api';
import type { SandboxCatalog } from '../types';

const ORCHESTRATOR_META: Array<{
  id: string;
  name: string;
  description: string;
}> = [
  { id: 'triage', name: 'Триадж', description: 'Первичный разбор запроса' },
  { id: 'planner', name: 'Планер', description: 'Планирование шагов выполнения' },
  { id: 'summary', name: 'Саммари', description: 'Сборка итогового ответа' },
];

export function useSandboxCatalog(sessionId: string | undefined) {
  return useQuery({
    queryKey: qk.sandbox.catalog.detail(sessionId ?? ''),
    queryFn: () => sandboxApi.getCatalog(sessionId ?? ''),
    enabled: !!sessionId,
    staleTime: 30_000,
  });
}

const EMPTY_CATALOG: SandboxCatalog = {
  tools: [],
  domain_groups: [],
  agents: [],
  system_routers: [],
  resolver_blueprints: [],
};

export function useCatalogData(sessionId: string | undefined) {
  const { data, ...rest } = useSandboxCatalog(sessionId);
  const orchestratorQueries = useQueries({
    queries: [
      {
        queryKey: qk.admin.systemLlmRoles.active('triage'),
        queryFn: () => systemLLMRolesApi.getActive('triage'),
        staleTime: 30_000,
      },
      {
        queryKey: qk.admin.systemLlmRoles.active('planner'),
        queryFn: () => systemLLMRolesApi.getActive('planner'),
        staleTime: 30_000,
      },
      {
        queryKey: qk.admin.systemLlmRoles.active('summary'),
        queryFn: () => systemLLMRolesApi.getActive('summary'),
        staleTime: 30_000,
      },
    ],
  });

  const orchestrators = useMemo(() => {
    const triageConfig = orchestratorQueries[0]?.data as Record<string, unknown> | undefined;
    const plannerConfig = orchestratorQueries[1]?.data as Record<string, unknown> | undefined;
    const summaryConfig = orchestratorQueries[2]?.data as Record<string, unknown> | undefined;

    const configById: Record<string, Record<string, unknown>> = {
      triage: triageConfig ?? {},
      planner: plannerConfig ?? {},
      summary: summaryConfig ?? {},
    };

    return ORCHESTRATOR_META.map((item) => ({
      id: item.id,
      name: item.name,
      description: item.description,
      config: configById[item.id] ?? {},
    }));
  }, [orchestratorQueries]);

  const isOrchestratorsLoading = orchestratorQueries.some((query) => query.isLoading);

  return {
    data: {
      ...(data ?? EMPTY_CATALOG),
      system_routers: orchestrators,
    },
    isOrchestratorsLoading,
    ...rest,
  };
}
