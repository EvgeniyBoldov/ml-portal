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

export const TOOL_VERSION_PROFILE_FIELDS: FieldConfig[] = [
  {
    key: 'summary',
    type: 'textarea',
    label: 'Краткое описание',
    description: 'Что это за инструмент и зачем он нужен.',
    required: true,
    placeholder: 'Поиск устройств и получение их состояния.',
    rows: 4,
  },
  {
    key: 'when_to_use',
    type: 'textarea',
    label: 'Когда использовать',
    description: 'Какие задачи и запросы должны приводить к этому инструменту.',
    placeholder: 'Когда нужно найти устройство по имени, IP или серийному номеру.',
    rows: 4,
  },
  {
    key: 'limitations',
    type: 'textarea',
    label: 'Ограничения',
    description: 'Где инструмент плохо подходит или может дать неполный ответ.',
    placeholder: 'Не подходит для массовых изменений и сложных join-запросов.',
    rows: 4,
  },
  {
    key: 'examples',
    type: 'textarea',
    label: 'Примеры',
    description: 'По одному примеру на строку.',
    placeholder: 'Покажи все активные устройства в сегменте...\nНайди IP-адрес для устройства core-sw-01...',
    rows: 5,
  },
];

export const TOOL_VERSION_POLICY_FIELDS: FieldConfig[] = [
  {
    key: 'policy_dos',
    type: 'textarea',
    label: 'Что делать можно',
    description: 'Разрешённые и предпочтительные сценарии использования.',
    placeholder: 'Используй инструмент для чтения данных.\nПроверяй результат по нескольким полям.',
    rows: 4,
  },
  {
    key: 'policy_donts',
    type: 'textarea',
    label: 'Что делать нельзя',
    description: 'Запреты и явные анти-паттерны.',
    placeholder: 'Не делай массовые изменения без подтверждения.\nНе полагайся на этот инструмент для удаления.',
    rows: 4,
  },
  {
    key: 'policy_guardrails',
    type: 'textarea',
    label: 'Границы и стоп-факторы',
    description: 'Что должно остановить использование инструмента.',
    placeholder: 'Останавливайся, если не хватает прав доступа.\nЗапрашивай подтверждение перед write-операциями.',
    rows: 4,
  },
  {
    key: 'policy_sensitive_inputs',
    type: 'textarea',
    label: 'Чувствительные входы',
    description: 'Какие поля особенно опасны или требуют аккуратности.',
    placeholder: 'password\ntoken\nsecret',
    rows: 3,
  },
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

function toText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function toLines(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => toText(item)).filter((item) => item.length > 0);
  }
  if (typeof value === 'string') {
    return value.split(/\r?\n/).map((item) => item.trim()).filter((item) => item.length > 0);
  }
  return [];
}

function toMultiline(value: unknown): string {
  return toLines(value).join('\n');
}

export function buildToolReleaseVersionData(version: ToolReleaseResponse | null | undefined) {
  if (!version) return null;

  const semanticExamples = version.semantic_profile?.examples ?? [];
  const policyDos = version.policy_hints?.dos ?? [];
  const policyDonts = version.policy_hints?.donts ?? [];
  const policyGuardrails = version.policy_hints?.guardrails ?? [];
  const policySensitiveInputs = version.policy_hints?.sensitive_inputs ?? [];

  return {
    backend_release_id: version.backend_release_id ?? null,
    summary: toText(version.semantic_profile?.summary)
      || toText(version.backend_release?.description)
      || '',
    when_to_use: toText(version.semantic_profile?.when_to_use),
    limitations: toText(version.semantic_profile?.limitations),
    examples: toMultiline(semanticExamples),
    policy_dos: toMultiline(policyDos),
    policy_donts: toMultiline(policyDonts),
    policy_guardrails: toMultiline(policyGuardrails),
    policy_sensitive_inputs: toMultiline(policySensitiveInputs),
  };
}

export function buildToolReleasePayload(formData: Record<string, unknown>) {
  return {
    backend_release_id: toText(formData.backend_release_id) || undefined,
    semantic_profile: {
      summary: toText(formData.summary),
      when_to_use: toText(formData.when_to_use),
      limitations: toText(formData.limitations),
      examples: toLines(formData.examples),
    },
    policy_hints: {
      dos: toLines(formData.policy_dos),
      donts: toLines(formData.policy_donts),
      guardrails: toLines(formData.policy_guardrails),
      sensitive_inputs: toLines(formData.policy_sensitive_inputs),
    },
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
