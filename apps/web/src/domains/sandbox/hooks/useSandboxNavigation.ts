import { useQuery } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { sandboxApi } from '../api';
import type { SandboxCatalog } from '../types';

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

  return {
    data: data ?? EMPTY_CATALOG,
    ...rest,
  };
}
