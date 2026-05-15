/**
 * Agents hooks - concrete implementations for Agent entities
 * 
 * Uses universal hooks with Agent-specific configuration
 */
import { useSearchParams } from 'react-router-dom';
import { useEntityList } from '@/shared/hooks/useEntityList';
import { useEntityEditor } from '@/shared/hooks/useEntityEditor';
import { useVersionEditor } from '@/shared/hooks/useVersionEditor';
import { agentsApi, type Agent, type AgentDetail, type AgentCreate, type AgentUpdate, type AgentVersion, type AgentVersionCreate } from '@/shared/api/agents';
import { qk } from '@/shared/api/keys';
import type { QueryKey } from '@tanstack/react-query';

function toNullableString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

function toNullableNumber(value: unknown): number | null {
  if (typeof value !== 'number' || Number.isNaN(value)) return null;
  return value;
}

function toNullableBoolean(value: unknown): boolean | null {
  if (typeof value !== 'boolean') return null;
  return value;
}

function toNullableStringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const normalized = value
    .map((item) => (typeof item === 'string' ? item.trim() : ''))
    .filter((item) => item.length > 0);
  return normalized.length ? normalized : null;
}

/* ─── List Hook ─── */
export function useAgentList() {
  return useEntityList<Agent>({
    queryKey: qk.agents.list({}) as QueryKey,
    queryFn: () => agentsApi.list(),
    deleteFn: (id) => agentsApi.delete(id),
    invalidateKeys: [qk.agents.all() as QueryKey],
    searchFields: ['name', 'slug', 'description'],
    messages: { deleted: 'Агент удален' },
    basePath: '/admin/agents',
    idField: 'id',
  });
}

/* ─── Detail Hook ─── */
export function useAgentDetail(id: string) {
  return useEntityEditor<AgentDetail, AgentCreate, AgentUpdate>({
    entityType: 'agent',
    entityNameLabel: 'Агента',
    entityTypeLabel: 'агента',
    basePath: '/admin/agents',
    listPath: '/admin/agents',
    api: {
      get: agentsApi.get,
      create: (data: AgentCreate) => agentsApi.create(data) as Promise<AgentDetail>,
      update: (id, data) => agentsApi.update(id, data) as Promise<AgentDetail>,
      delete: agentsApi.delete,
    },
    queryKeys: {
      list: qk.agents.list({}) as QueryKey,
      detail: (id) => qk.agents.detail(id) as QueryKey,
    },
    getInitialFormData: (entity) => ({
      slug: entity?.slug ?? '',
      name: entity?.name ?? '',
      description: entity?.description ?? '',
      model: entity?.model ?? '',
      temperature: entity?.temperature ?? null,
      max_tokens: entity?.max_tokens ?? null,
      max_steps: entity?.max_steps ?? null,
      timeout_s: entity?.timeout_s ?? null,
      max_retries: entity?.max_retries ?? null,
      requires_confirmation_for_write: entity?.requires_confirmation_for_write ?? null,
      risk_level: entity?.risk_level ?? '',
      logging_level: entity?.logging_level ?? 'brief',
      tags: entity?.tags ?? [],
      allowed_collection_ids: entity?.allowed_collection_ids ?? [],
    }),
    validateCreate: (data) => {
      const slug = typeof data?.slug === 'string' ? data.slug.trim() : '';
      if (!slug) return 'Поле slug обязательно';
      return null;
    },
    messages: {
      create: 'Агент создан',
      update: 'Агент обновлен',
      delete: 'Агент удален',
    },
  });
}

/* ─── Version Editor Hook ─── */
export function useAgentVersionEditor(agentId: string, versionParam: string | undefined) {
  const [searchParams] = useSearchParams();
  const fromVersionParam = searchParams.get('from');

  return useVersionEditor<AgentDetail, AgentVersion, AgentVersionCreate>({
    slug: agentId,
    versionParam,
    fromVersionParam,
    queryKeys: {
      parentDetail: (id) => qk.agents.detail(id) as QueryKey,
      versionsList: (id) => qk.agents.versions(id) as QueryKey,
      versionDetail: (id, v) => qk.agents.version(id, v) as QueryKey,
    },
    api: {
      getParent: agentsApi.get,
      getVersion: agentsApi.getVersion,
      createVersion: agentsApi.createVersion,
      updateVersion: (id, v, data) => agentsApi.updateVersion(id, v, data),
      activateVersion: agentsApi.publishVersion,
      deactivateVersion: agentsApi.archiveVersion,
      setRecommendedVersion: agentsApi.setCurrentVersion,
      deleteVersion: agentsApi.deleteVersion,
    },
    getInitialFormData: (version) => ({
      // Prompt parts
      identity: version?.identity ?? '',
      mission: version?.mission ?? '',
      scope: version?.scope ?? '',
      planner_short_info: version?.planner_short_info ?? '',
      rules: version?.rules ?? '',
      tool_use_rules: version?.tool_use_rules ?? '',
      output_format: version?.output_format ?? '',
      examples: version?.examples ?? '',
      // Execution config
      model: version?.model ?? '',
      timeout_s: version?.timeout_s ?? null,
      max_steps: version?.max_steps ?? null,
      max_retries: version?.max_retries ?? null,
      max_tokens: version?.max_tokens ?? null,
      temperature: version?.temperature ?? null,
      // Safety knobs
      requires_confirmation_for_write: version?.requires_confirmation_for_write ?? false,
      risk_level: version?.risk_level ?? '',
      never_do: version?.never_do ?? '',
      allowed_ops: version?.allowed_ops ?? '',
      tags: version?.tags ?? [],
      notes: version?.notes ?? '',
    }),
    buildCreatePayload: (formData, sourceVersion) => ({
      identity: toNullableString(formData.identity),
      mission: toNullableString(formData.mission),
      scope: toNullableString(formData.scope),
      planner_short_info: toNullableString(formData.planner_short_info),
      rules: toNullableString(formData.rules),
      tool_use_rules: toNullableString(formData.tool_use_rules),
      output_format: toNullableString(formData.output_format),
      examples:
        typeof formData.examples === 'string'
          ? toNullableString(formData.examples)
          : (formData.examples ? JSON.stringify(formData.examples) : null),
      model: toNullableString(formData.model),
      timeout_s: toNullableNumber(formData.timeout_s),
      max_steps: toNullableNumber(formData.max_steps),
      max_retries: toNullableNumber(formData.max_retries),
      max_tokens: toNullableNumber(formData.max_tokens),
      temperature: toNullableNumber(formData.temperature),
      requires_confirmation_for_write: toNullableBoolean(formData.requires_confirmation_for_write),
      risk_level: toNullableString(formData.risk_level),
      never_do: toNullableString(formData.never_do),
      allowed_ops: toNullableString(formData.allowed_ops),
      tags: toNullableStringArray(formData.tags),
      notes: toNullableString(formData.notes),
      parent_version_id: sourceVersion?.id,
    }),
    basePath: '/admin/agents',
    messages: {
      created: 'Версия агента создана',
      updated: 'Версия агента обновлена',
      published: 'Версия агента опубликована',
      archived: 'Версия агента отправлена в архив',
      setRecommended: 'Версия сделана основной',
      deleted: 'Версия агента удалена',
    },
  });
}
