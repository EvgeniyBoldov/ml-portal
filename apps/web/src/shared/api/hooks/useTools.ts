/**
 * Tools hooks - concrete implementations for Tool entities
 * 
 * Uses universal hooks with Tool-specific configuration
 */
import { useEntityEditor } from '@/shared/hooks/useEntityEditor';
import { toolReleasesApi, type ToolDetail, type ToolUpdateRequest } from '@/shared/api/toolReleases';
import { qk } from '@/shared/api/keys';
import type { QueryKey } from '@tanstack/react-query';

/* ─── Tool (not Group) Detail Hook ─── */
export function useToolDetail(id: string) {
  return useEntityEditor<ToolDetail, never, ToolUpdateRequest>({
    entityType: 'tool',
    entityNameLabel: 'Инструменты',
    entityTypeLabel: 'инструмент',
    basePath: '/admin/tools',
    listPath: '/admin/tools',
    api: {
      get: (id: string) => toolReleasesApi.getTool(id),
      create: () => Promise.reject(new Error('Tools are synchronized from runtime code')),
      update: (id: string, data: ToolUpdateRequest) => toolReleasesApi.updateTool(id, data),
    },
    queryKeys: {
      list: qk.tools.list({}) as QueryKey,
      detail: (id: string) => qk.tools.detail(id) as QueryKey,
    },
    getInitialFormData: (entity: ToolDetail | undefined) => ({
      name: entity?.name ?? '',
      tags: entity?.tags ?? [],
      domains: entity?.domains ?? [],
    }),
    messages: {
      create: '',
      update: 'Инструмент обновлен',
      delete: '',
    },
  });
}
