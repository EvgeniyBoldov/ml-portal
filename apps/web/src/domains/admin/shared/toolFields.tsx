import React from 'react';
import type { DataTableColumn, GridFieldConfig as FieldConfig } from '@/shared/ui';
import Badge from '@/shared/ui/Badge';
import type {
  ToolBackendReleaseDetail,
  ToolBackendReleaseListItem,
  ToolDetail,
  ToolReleaseResponse,
} from '@/shared/api/toolReleases';

export const TOOL_INFO_FIELDS: FieldConfig[] = [
  {
    key: 'name',
    type: 'text',
    label: 'Название',
    required: true,
    placeholder: 'My Tool',
  },
  {
    key: 'domains',
    type: 'tags',
    label: 'Домены',
    placeholder: 'jira, netbox, collection...',
    editable: false,
  },
  {
    key: 'tags',
    type: 'tags',
    label: 'Теги',
    placeholder: 'netbox, inventory, поиск...',
  },
];

export const TOOL_STATS_FIELDS: FieldConfig[] = [
  { key: 'releases_count', type: 'badge', label: 'Версий релиза', badgeTone: 'neutral', editable: false },
  { key: 'backend_releases_count', type: 'badge', label: 'Схем', badgeTone: 'info', editable: false },
  { key: 'has_current_version', type: 'badge', label: 'Активный релиз', badgeTone: 'success', editable: false },
];

export const TOOL_META_FIELDS: FieldConfig[] = [
  { key: 'version', type: 'code', label: 'Версия релиза', editable: false },
  { key: 'status', type: 'badge', label: 'Статус', badgeTone: 'neutral', editable: false },
  { key: 'is_primary', type: 'badge', label: 'Основная версия', badgeTone: 'info', editable: false },
  { key: 'created_at', type: 'date', label: 'Создан', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлён', editable: false },
];

export const TOOL_BACKEND_RELEASE_INFO_FIELDS: FieldConfig[] = [
  { key: 'version', type: 'code', label: 'Версия', editable: false },
  { key: 'method_name', type: 'code', label: 'Метод', editable: false },
  { key: 'description', type: 'text', label: 'Описание', editable: false },
  { key: 'worker_build_id', type: 'code', label: 'Worker Build ID', editable: false },
];

export const TOOL_BACKEND_RELEASE_META_FIELDS: FieldConfig[] = [
  { key: 'schema_hash', type: 'code', label: 'Хеш схемы', editable: false },
  { key: 'last_seen_at', type: 'date', label: 'Последний seen', editable: false },
  { key: 'synced_at', type: 'date', label: 'Синхронизировано', editable: false },
];

export const TOOL_BACKEND_COLUMNS: DataTableColumn<ToolBackendReleaseListItem>[] = [
  { key: 'version', label: 'ВЕРСИЯ', render: (row) => <strong>{row.version}</strong> },
  { key: 'description', label: 'ОПИСАНИЕ', render: (row) => row.description || '—' },
  { key: 'schema_hash', label: 'СХЕМА', render: (row) => row.schema_hash ? row.schema_hash.slice(0, 8) : '—' },
  {
    key: 'deprecated',
    label: 'СТАТУС',
    render: (row) => <Badge tone={row.deprecated ? 'warn' : 'success'}>{row.deprecated ? 'Устарела' : 'Актуальна'}</Badge>,
  },
];

export function buildToolReleaseVersionData(version: ToolReleaseResponse | null | undefined) {
  if (!version) return null;
  return {
    backend_release_id: version.backend_release_id ?? null,
  };
}

export function buildToolReleasePayload(formData: Record<string, unknown>) {
  const backendReleaseId = typeof formData.backend_release_id === 'string'
    ? formData.backend_release_id.trim()
    : '';
  return {
    backend_release_id: backendReleaseId || undefined,
  };
}

export function buildJsonFieldConfig(key: string, label: string): FieldConfig {
  return {
    key,
    type: 'json',
    label,
    editable: false,
  };
}

export function buildToolBackendReleaseInfoData(
  release: ToolBackendReleaseListItem | ToolBackendReleaseDetail | null | undefined,
) {
  if (!release) return {};

  return {
    version: release.version,
    method_name: 'method_name' in release ? release.method_name : '—',
    description: release.description || '—',
    worker_build_id: release.worker_build_id || '—',
  };
}

export function buildToolBackendReleaseMetaData(
  release: ToolBackendReleaseListItem | ToolBackendReleaseDetail | null | undefined,
) {
  if (!release) return {};

  return {
    schema_hash: release.schema_hash || '—',
    last_seen_at: release.last_seen_at || '',
    synced_at: release.synced_at || '',
  };
}

export function buildToolVersionMetaData(tool: ToolDetail) {
  return {
    version: tool.current_version?.version ? `v${tool.current_version.version}` : '—',
    status: tool.current_version?.status || '—',
    is_primary: tool.current_version ? 'Да' : 'Нет',
    created_at: tool.current_version?.created_at || '',
    updated_at: tool.current_version?.updated_at || '',
  };
}
