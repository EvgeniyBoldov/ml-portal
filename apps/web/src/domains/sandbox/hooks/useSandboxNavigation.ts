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
  { id: 'planner', name: 'Планер', description: 'Планирование шагов выполнения' },
  { id: 'synthesizer', name: 'Synthesizer', description: 'Сборка итогового ответа' },
  { id: 'fact_extractor', name: 'Fact Extractor', description: 'Извлечение фактов для памяти' },
  { id: 'summary_compactor', name: 'Summary Compactor', description: 'Компрессия rolling summary' },
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
        queryKey: qk.admin.systemLlmRoles.active('planner'),
        queryFn: () => systemLLMRolesApi.getActive('planner'),
        staleTime: 30_000,
      },
      {
        queryKey: qk.admin.systemLlmRoles.active('synthesizer'),
        queryFn: () => systemLLMRolesApi.getActive('synthesizer'),
        staleTime: 30_000,
      },
      {
        queryKey: qk.admin.systemLlmRoles.active('fact_extractor'),
        queryFn: () => systemLLMRolesApi.getActive('fact_extractor'),
        staleTime: 30_000,
      },
      {
        queryKey: qk.admin.systemLlmRoles.active('summary_compactor'),
        queryFn: () => systemLLMRolesApi.getActive('summary_compactor'),
        staleTime: 30_000,
      },
    ],
  });

  const orchestrators = useMemo(() => {
    const plannerConfig = orchestratorQueries[0]?.data as Record<string, unknown> | undefined;
    const synthesizerConfig = orchestratorQueries[1]?.data as Record<string, unknown> | undefined;
    const factExtractorConfig = orchestratorQueries[2]?.data as Record<string, unknown> | undefined;
    const summaryCompactorConfig = orchestratorQueries[3]?.data as Record<string, unknown> | undefined;

    const configById: Record<string, Record<string, unknown>> = {
      planner: plannerConfig ?? {},
      synthesizer: synthesizerConfig ?? {},
      fact_extractor: factExtractorConfig ?? {},
      summary_compactor: summaryCompactorConfig ?? {},
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
