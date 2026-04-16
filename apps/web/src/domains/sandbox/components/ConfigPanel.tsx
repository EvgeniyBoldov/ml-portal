/**
 * ConfigPanel — right panel for managing overrides in a sandbox session.
 * Session-first architecture: overrides are persisted on server.
 */
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Select, type SelectOption } from '@/shared/ui/Select';
import Badge from '@/shared/ui/Badge';
import Button from '@/shared/ui/Button';
import { agentsApi, type AgentVersion } from '@/shared/api/agents';
import { qk } from '@/shared/api/keys';
import { platformSettingsApi } from '@/shared/api/admin';
import { sandboxApi } from '../api';
import type {
  SandboxCatalog,
  SandboxOverride,
  SandboxResolverBlueprint,
  SandboxResolverFieldSpec,
  SandboxResolverSectionSpec,
  SandboxSelectedItem,
} from '../types';
import ConfigDataField, { type SandboxConfigField, type SandboxConfigFieldType } from './ConfigDataField';
import ConfigTabs from './ConfigTabs';
import RunInspector from './RunInspector';
import type { RunStep } from '../hooks/useSandboxRun';
import { SandboxResolver } from '../lib/sandboxResolver';
import styles from './ConfigPanel.module.css';

interface SessionConfigPanelProps {
  sessionId: string;
  overrides: SandboxOverride[];
  isReadOnly: boolean;
  selectedItem: SandboxSelectedItem | null;
  activeBranchId: string;
  catalog?: SandboxCatalog;
  inspectorSteps?: RunStep[];
  selectedStepId?: string | null;
  inspectorRunId?: string | null;
  inspectorRunStatus?: string;
}

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function parseValue(raw: string, type: SandboxConfigFieldType): unknown {
  if (type === 'boolean') {
    return raw.trim().toLowerCase() === 'true';
  }
  if (type === 'integer') {
    return Number.parseInt(raw, 10);
  }
  if (type === 'float') {
    return Number.parseFloat(raw);
  }
  if (type === 'tags') {
    return raw
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  }
  if (type === 'json') {
    return JSON.parse(raw);
  }
  return raw;
}

function toDisplayFieldName(raw: string): string {
  const withoutPrefix = raw.startsWith('routing_') ? raw.slice('routing_'.length) : raw;
  return withoutPrefix
    .split('_')
    .filter((part) => part.length > 0)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

const TYPE_LABELS: Record<string, string> = {
  agent_version: 'Версия агента',
  tool_release: 'Релиз инструмента',
  discovered_tool: 'Инструмент',
  orchestration: 'Оркестрация',
  policy: 'Политика',
  limit: 'Лимиты',
  model: 'Модель',
};

interface FieldsSection {
  title: string;
  fields: SandboxConfigField[];
}

const AGENT_SECTIONS: Array<{ title: string; keys: string[] }> = [
  { title: 'Prompt', keys: ['identity', 'mission', 'scope', 'rules', 'tool_use_rules', 'output_format', 'examples'] },
  { title: 'Execution', keys: ['model', 'timeout_s', 'max_steps', 'max_retries', 'max_tokens', 'temperature'] },
  { title: 'Safety', keys: ['requires_confirmation_for_write', 'risk_level', 'never_do', 'allowed_ops'] },
  { title: 'Routing', keys: ['short_info', 'tags', 'is_routable', 'routing_keywords', 'routing_negative_keywords', 'bindings'] },
];

const LONG_TEXT_KEYS = new Set([
  'identity',
  'mission',
  'scope',
  'rules',
  'tool_use_rules',
  'output_format',
  'examples',
  'never_do',
  'description_for_llm',
  'return_summary',
  'routing_side_effects',
]);

const TAGS_KEYS = new Set([
  'tags',
  'routing_keywords',
  'routing_negative_keywords',
  'routing_ops',
  'routing_systems',
  'exec_retry_on',
  'allowed_ops',
]);

const SELECT_KEYS = new Set(['model', 'risk_level', 'exec_priority', 'default_model']);

const ORCHESTRATOR_PROMPT_KEYS = new Set([
  'identity',
  'mission',
  'scope',
  'rules',
  'tool_use_rules',
  'output_format',
  'examples',
  'short_info',
  'safety',
  'output_requirements',
]);

const PLATFORM_LIMIT_KEYS = [
  'abs_max_timeout_s',
  'abs_max_retries',
  'abs_max_steps',
  'abs_max_plan_steps',
  'abs_max_concurrency',
  'abs_max_task_runtime_s',
  'abs_max_tool_calls_per_step',
] as const;

const RISK_LEVEL_OPTIONS: SelectOption[] = [
  { value: 'low', label: 'low' },
  { value: 'medium', label: 'medium' },
  { value: 'high', label: 'high' },
];

function detectFieldType(key: string, value: unknown): SandboxConfigFieldType {
  if (SELECT_KEYS.has(key)) {
    return 'select';
  }
  if (Array.isArray(value) && TAGS_KEYS.has(key)) {
    return 'tags';
  }
  if (value === null || value === undefined) {
    return LONG_TEXT_KEYS.has(key) ? 'text' : 'text';
  }
  if (value !== null && typeof value === 'object') {
    return 'json';
  }
  if (typeof value === 'boolean') {
    return 'boolean';
  }
  if (typeof value === 'number') {
    return Number.isInteger(value) ? 'integer' : 'float';
  }
  if (typeof value === 'string') {
    if (LONG_TEXT_KEYS.has(key) || value.length > 100 || value.includes('\n')) {
      return 'text';
    }
    return 'text';
  }
  return 'text';
}

function toField(
  name: string,
  value: unknown,
  explicitType?: SandboxConfigFieldType,
  label?: string,
  editable?: boolean,
): SandboxConfigField {
  return {
    name,
    type: explicitType ?? detectFieldType(name, value),
    value,
    label,
    editable,
  };
}

function getNestedValue(source: Record<string, unknown>, path: string): unknown {
  if (path.includes('.')) {
    return path.split('.').reduce<unknown>((acc, part) => {
      if (!acc || typeof acc !== 'object') return undefined;
      return (acc as Record<string, unknown>)[part];
    }, source);
  }
  return source[path];
}

function resolveBlueprintFieldValue(
  source: Record<string, unknown>,
  field: SandboxResolverFieldSpec,
): unknown {
  const sourceKey = field.source_key ?? field.key;
  const directValue = getNestedValue(source, sourceKey);
  if (directValue !== undefined) {
    return directValue;
  }
  return getNestedValue(source, field.field_path);
}

function buildSectionsFromBlueprint(
  source: Record<string, unknown>,
  blueprint: SandboxResolverBlueprint | null,
): FieldsSection[] {
  if (!blueprint) return [];

  return blueprint.sections
    .map((section: SandboxResolverSectionSpec) => {
      const fields = section.fields.map((field) =>
        toField(
          field.field_path,
          resolveBlueprintFieldValue(source, field),
          field.field_type,
          field.label,
          field.editable,
        ),
      );
      fields.forEach((item, index) => {
        item.options = section.fields[index]?.options ?? [];
      });
      return { title: section.title, fields };
    })
    .filter((section) => section.fields.length > 0);
}

export function ConfigPanel({
  ...props
}: SessionConfigPanelProps) {
  const { overrides, selectedItem, catalog, sessionId, isReadOnly, activeBranchId, inspectorSteps, selectedStepId, inspectorRunId, inspectorRunStatus } = props;
  const queryClient = useQueryClient();
  const [activeSectionTab, setActiveSectionTab] = useState<string>('');
  const [activeParameterTab, setActiveParameterTab] = useState<'platform'>('platform');
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [selectedAgentVersionId, setSelectedAgentVersionId] = useState<string>('');
  const [selectedToolVersionId, setSelectedToolVersionId] = useState<string>('');

  const selectedAgent = selectedItem?.type === 'agent'
    ? catalog?.agents.find((agent) => agent.id === selectedItem.id)
    : undefined;
  const selectedRouter = selectedItem?.type === 'router'
    ? catalog?.system_routers.find((router) => router.id === selectedItem.id)
    : undefined;
  const selectedTool = selectedItem?.type === 'tool'
    ? catalog?.tools.find((tool) => tool.id === selectedItem.id)
    : undefined;

  const selectedBaseAgentVersion = selectedAgent?.versions.find((v) => v.id === selectedAgentVersionId);

  const { data: platformSettings } = useQuery({
    queryKey: qk.platform.settings(),
    queryFn: () => platformSettingsApi.get(),
    staleTime: 30_000,
  });

  const { data: agentVersions } = useQuery({
    queryKey: qk.agents.versions(selectedAgent?.id ?? ''),
    queryFn: () => agentsApi.listVersions(selectedAgent!.id),
    enabled: !!selectedAgent,
    staleTime: 30_000,
  });

  const selectedAgentVersionData = useMemo(() => {
    if (!agentVersions || !selectedBaseAgentVersion) return null;
    return agentVersions.find((v: AgentVersion) => v.id === selectedBaseAgentVersion.id) ?? null;
  }, [agentVersions, selectedBaseAgentVersion]);

  const { data: branchOverrides = [] } = useQuery({
    queryKey: qk.sandbox.branchOverrides.list(sessionId, activeBranchId),
    queryFn: () => sandboxApi.listBranchOverrides(sessionId, activeBranchId),
    enabled: activeBranchId.length > 0,
    staleTime: 15_000,
  });

  const selectedBlueprintKey = useMemo(() => {
    if (!selectedItem) return '';
    if (selectedItem.type === 'parameter') {
      return activeParameterTab;
    }
    if (selectedItem.type === 'tool') {
      return 'discovered_tool';
    }
    return selectedItem.type;
  }, [activeParameterTab, selectedItem]);

  const selectedBlueprint = useMemo(
    () => catalog?.resolver_blueprints.find((item) => item.key === selectedBlueprintKey) ?? null,
    [catalog?.resolver_blueprints, selectedBlueprintKey],
  );

  const upsertMutation = useMutation({
    mutationFn: (payload: { entity_type: string; entity_id?: string | null; field_path: string; value_json: unknown; value_type?: string }) =>
      sandboxApi.upsertBranchOverride(sessionId, activeBranchId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: qk.sandbox.sessions.detail(sessionId) });
      await queryClient.invalidateQueries({ queryKey: qk.sandbox.branchOverrides.list(sessionId, activeBranchId) });
    },
  });

  const clearMutation = useMutation({
    mutationFn: (params?: { entity_type?: string; entity_id?: string | null; field_path?: string }) =>
      sandboxApi.deleteBranchOverrides(sessionId, activeBranchId, params),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: qk.sandbox.sessions.detail(sessionId) });
      await queryClient.invalidateQueries({ queryKey: qk.sandbox.branchOverrides.list(sessionId, activeBranchId) });
    },
  });

  const selectedEntityMeta = useMemo(() => {
    if (!selectedItem) return null;
    if (selectedItem.type === 'agent') {
      return { entityType: selectedBlueprint?.entity_type ?? 'agent_version', entityId: selectedAgentVersionId || null };
    }
    if (selectedItem.type === 'tool') {
      return { entityType: selectedBlueprint?.entity_type ?? 'discovered_tool', entityId: selectedTool?.id ?? null };
    }
    if (selectedItem.type === 'router') {
      return { entityType: selectedBlueprint?.entity_type ?? 'orchestration', entityId: selectedRouter?.id ?? null };
    }
    return { entityType: selectedBlueprint?.entity_type ?? 'orchestration', entityId: null };
  }, [selectedAgentVersionId, selectedBlueprint?.entity_type, selectedItem, selectedRouter?.id, selectedTool?.id]);

  const overrideMap = useMemo(() => {
    return new SandboxResolver(branchOverrides);
  }, [branchOverrides]);

  useEffect(() => {
    if (!selectedAgent || selectedItem?.type !== 'agent') {
      setSelectedAgentVersionId('');
      return;
    }
    const overrideValue = overrideMap.getOverride('orchestration', null, 'agent.version_id')?.value_json;
    const overrideVersionId = typeof overrideValue === 'string' ? overrideValue : '';
    const hasOverrideVersion = overrideVersionId.length > 0 && selectedAgent.versions.some((version) => version.id === overrideVersionId);
    const nextVersionId =
      (hasOverrideVersion ? overrideVersionId : undefined) ??
      selectedItem.versionId ??
      selectedAgent.current_version_id ??
      selectedAgent.versions[0]?.id ??
      '';
    setSelectedAgentVersionId(nextVersionId);
  }, [overrideMap, selectedAgent, selectedItem?.id, selectedItem?.type, selectedItem?.versionId]);

  useEffect(() => {
    if (!selectedTool || selectedItem?.type !== 'tool') {
      setSelectedToolVersionId('');
      return;
    }
    const overrideValue = overrideMap.getOverride('discovered_tool', selectedTool.id, 'tool_release_id')?.value_json;
    const overrideVersionId = typeof overrideValue === 'string' ? overrideValue : '';
    const hasOverrideVersion = overrideVersionId.length > 0 && selectedTool.versions.some((version) => version.id === overrideVersionId);
    const nextVersionId =
      (hasOverrideVersion ? overrideVersionId : undefined) ??
      selectedItem.versionId ??
      selectedTool.current_version_id ??
      selectedTool.versions[0]?.id ??
      '';
    setSelectedToolVersionId(nextVersionId);
  }, [overrideMap, selectedItem?.id, selectedItem?.type, selectedItem?.versionId, selectedTool]);

  const agentVersionOptions = useMemo<SelectOption[]>(
    () =>
      (selectedAgent?.versions ?? []).map((version) => ({
        value: version.id,
        label: `v${version.version} · ${version.status}`,
      })),
    [selectedAgent],
  );

  const toolVersionOptions = useMemo<SelectOption[]>(
    () =>
      (selectedTool?.versions ?? []).map((version) => ({
        value: version.id,
        label: `v${version.version} · ${version.status}`,
      })),
    [selectedTool],
  );

  const fieldsSections = useMemo((): FieldsSection[] => {
    if (!selectedBlueprint) return [];

    const selectedToolBase =
      selectedTool == null
        ? {}
        : {
            ...selectedTool,
            current_version_id: selectedToolVersionId || selectedTool.current_version_id,
          };

    const sourceByKey: Record<string, Record<string, unknown>> = {
      agent: (selectedAgentVersionData ?? {}) as Record<string, unknown>,
      discovered_tool: selectedToolBase as Record<string, unknown>,
      router: ((selectedRouter?.config ?? {}) as Record<string, unknown>),
      platform: (platformSettings ?? {}) as Record<string, unknown>,
    };

    const source = sourceByKey[selectedBlueprint.key] ?? {};
    return buildSectionsFromBlueprint(source, selectedBlueprint);
  }, [
    activeParameterTab,
    platformSettings,
    selectedItem,
    selectedAgentVersionData,
    selectedBlueprint,
    selectedRouter,
    selectedToolVersionId,
    selectedTool,
  ]);

  const sectionTabs = useMemo(
    () => fieldsSections.map((section) => ({ id: section.title, label: section.title })),
    [fieldsSections],
  );

  useEffect(() => {
    setActiveSectionTab(sectionTabs[0]?.id ?? '');
  }, [sectionTabs]);

  useEffect(() => {
    if (selectedItem?.type === 'parameter') {
      if (selectedItem.id === 'platform') {
        setActiveParameterTab('platform');
      }
    }
  }, [selectedItem]);

  const visibleSections = useMemo(() => {
    if (selectedItem?.type === 'parameter') {
      return fieldsSections;
    }
    if (!activeSectionTab) {
      return [];
    }
    return fieldsSections.filter((section) => section.title === activeSectionTab);
  }, [activeSectionTab, fieldsSections, selectedItem]);

  useEffect(() => {
    setDrafts({});
  }, [selectedItem?.id, selectedItem?.type, selectedItem?.versionId, selectedAgentVersionId, selectedToolVersionId, activeParameterTab]);

  const getFieldPath = (fieldName: string): string => fieldName;

  const getFieldKey = (fieldName: string): string => {
    if (!selectedEntityMeta) return '';
    return `${selectedEntityMeta.entityType}:${selectedEntityMeta.entityId ?? ''}:${getFieldPath(fieldName)}`;
  };

  const getFieldInputValue = (fieldName: string): string => {
    const key = getFieldKey(fieldName);
    if (key in drafts) {
      return drafts[key];
    }
    return getCommittedValue(fieldName);
  };

  const getFieldSelectOptions = (field: SandboxConfigField): SelectOption[] => {
    if (field.type !== 'select') {
      return [];
    }

    if (field.options && field.options.length > 0) {
      return field.options.map((value) => ({ value, label: value }));
    }

    if (field.name.endsWith('default_agent_slug')) {
      const agentOptions = catalog?.agents.map((agent) => ({ value: agent.slug, label: agent.name })) ?? [];
      if (agentOptions.length > 0) {
        return agentOptions;
      }
    }

    if (field.name.endsWith('risk_level')) {
      return RISK_LEVEL_OPTIONS;
    }

    if (field.name.endsWith('tool_release_id')) {
      return toolVersionOptions;
    }

    const currentValue = getFieldInputValue(field.name).trim();
    if (currentValue.length > 0) {
      return [{ value: currentValue, label: currentValue }];
    }

    const defaultValue = stringifyValue(field.value).trim();
    if (defaultValue.length > 0) {
      return [{ value: defaultValue, label: defaultValue }];
    }

    return [];
  };

  const getCommittedValue = (fieldName: string): string => {
    if (!selectedEntityMeta) return '';
    const item = overrideMap.getOverride(
      selectedEntityMeta.entityType,
      selectedEntityMeta.entityId,
      getFieldPath(fieldName),
    );
    return item ? stringifyValue(item.value_json) : '';
  };

  const isDirty = (fieldName: string): boolean => {
    const key = getFieldKey(fieldName);
    if (!(key in drafts)) return false;
    return drafts[key] !== getCommittedValue(fieldName);
  };

  const isOverridden = (fieldName: string): boolean => {
    if (!selectedEntityMeta) return false;
    return overrideMap.hasFieldOverride(
      selectedEntityMeta.entityType,
      selectedEntityMeta.entityId,
      getFieldPath(fieldName),
    );
  };

  const canClearEntity = useMemo(() => {
    if (!selectedEntityMeta) return false;
    return overrideMap.hasEntityOverrides(
      selectedEntityMeta.entityType,
      selectedEntityMeta.entityId,
    );
  }, [overrideMap, selectedEntityMeta]);

  const handleSaveFieldValue = async (field: SandboxConfigField, rawValue: string): Promise<void> => {
    if (!selectedEntityMeta || !activeBranchId) return;
    if (field.editable === false) return;
    if (rawValue.trim().length === 0) return;
    const key = getFieldKey(field.name);
    const parsedValue = parseValue(rawValue, field.type);
    await upsertMutation.mutateAsync({
      entity_type: selectedEntityMeta.entityType,
      entity_id: selectedEntityMeta.entityId,
      field_path: getFieldPath(field.name),
      value_json: parsedValue,
      value_type: field.type,
    });
    setDrafts((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const handleCommitField = async (field: SandboxConfigField, rawValue: string): Promise<void> => {
    const key = getFieldKey(field.name);
    setDrafts((prev) => ({ ...prev, [key]: rawValue }));
    await handleSaveFieldValue(field, rawValue);
  };

  const handleClearField = async (fieldName: string): Promise<void> => {
    const key = getFieldKey(fieldName);
    const hasCommittedOverride = isOverridden(fieldName);

    if (!selectedEntityMeta || !activeBranchId) return;

    if (hasCommittedOverride) {
      await clearMutation.mutateAsync({
        entity_type: selectedEntityMeta.entityType,
        entity_id: selectedEntityMeta.entityId,
        field_path: getFieldPath(fieldName),
      });
    }

    setDrafts((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const handleUseDefaultFieldValue = (field: SandboxConfigField): void => {
    if (field.editable === false) return;
    const key = getFieldKey(field.name);
    const defaultValue = stringifyValue(field.value);
    setDrafts((prev) => ({
      ...prev,
      [key]: defaultValue,
    }));
  };

  const handleClearEntity = async (): Promise<void> => {
    if (!selectedEntityMeta || !activeBranchId) return;
    await clearMutation.mutateAsync({
      entity_type: selectedEntityMeta.entityType,
      entity_id: selectedEntityMeta.entityId,
    });
    setDrafts({});
  };

  const handleAgentVersionChange = async (versionId: string): Promise<void> => {
    setSelectedAgentVersionId(versionId);
    if (!activeBranchId || !selectedAgent) return;
    if (!versionId || versionId === selectedAgent.current_version_id) {
      await clearMutation.mutateAsync({
        entity_type: 'orchestration',
        entity_id: null,
        field_path: 'agent.version_id',
      });
      return;
    }
    await upsertMutation.mutateAsync({
      entity_type: 'orchestration',
      entity_id: null,
      field_path: 'agent.version_id',
      value_json: versionId,
      value_type: 'select',
    });
  };

  const handleToolVersionChange = async (versionId: string): Promise<void> => {
    setSelectedToolVersionId(versionId);
    if (!activeBranchId || !selectedTool) return;
    if (!versionId || versionId === selectedTool.current_version_id) {
      await clearMutation.mutateAsync({
        entity_type: 'discovered_tool',
        entity_id: selectedTool.id,
        field_path: 'tool_release_id',
      });
      return;
    }
    await upsertMutation.mutateAsync({
      entity_type: 'discovered_tool',
      entity_id: selectedTool.id,
      field_path: 'tool_release_id',
      value_json: versionId,
      value_type: 'select',
    });
  };

  // Run inspector mode: show selected step detail
  if (selectedItem?.type === 'run' && inspectorSteps) {
    return (
      <RunInspector
        steps={inspectorSteps}
        selectedStepId={selectedStepId ?? null}
        runStatus={inspectorRunStatus}
        runId={inspectorRunId}
      />
    );
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles['header-main']}>
          <span className={styles.title}>
            {selectedItem ? selectedItem.name : 'Конфигурация'}
          </span>
          {selectedItem?.type === 'agent' && agentVersionOptions.length > 0 ? (
            <Select
              className={styles['version-select']}
              value={selectedAgentVersionId}
              options={agentVersionOptions}
              placeholder="Версия агента"
              disabled={isReadOnly}
              onChange={(value) => {
                void handleAgentVersionChange(value);
              }}
            />
          ) : null}
          {selectedItem?.type === 'tool' && toolVersionOptions.length > 0 ? (
            <Select
              className={styles['version-select']}
              value={selectedToolVersionId}
              options={toolVersionOptions}
              placeholder="Релиз инструмента"
              disabled={isReadOnly}
              onChange={(value) => {
                void handleToolVersionChange(value);
              }}
            />
          ) : null}
          {selectedItem ? (
            <div className={styles['header-actions-row']}>
              {overrides.length > 0 && <Badge tone="warn">{overrides.length}</Badge>}
              <Button className={styles['header-btn']} size="sm" variant="outline" onClick={handleClearEntity} disabled={isReadOnly || !canClearEntity}>
                Очистить
              </Button>
            </div>
          ) : (
            <span className={styles['empty-hint']}>Выбери элемент слева</span>
          )}
        </div>
      </div>

      {selectedItem?.type === 'parameter' ? (
        <ConfigTabs
          items={[
            { id: 'platform', label: 'Платформа' },
          ]}
          activeId={activeParameterTab}
          onChange={() => setActiveParameterTab('platform')}
        />
      ) : (
        <ConfigTabs items={sectionTabs} activeId={activeSectionTab} onChange={setActiveSectionTab} />
      )}

      <div className={styles.body}>
        {selectedItem && visibleSections.length > 0 ? (
          <div className={styles['sections-list']}>
            {visibleSections.map((section) => (
              <div key={section.title} className={styles.section}>
                <div className={styles['section-title']}>{section.title}</div>
                <div className={styles['fields-list']}>
                  {section.fields.map((field) => (
                    <ConfigDataField
                      key={field.name}
                      field={field}
                      displayName={field.label ?? toDisplayFieldName(field.name)}
                      tooltipText={field.name}
                      inputValue={getFieldInputValue(field.name)}
                      defaultValue={stringifyValue(field.value)}
                      selectOptions={getFieldSelectOptions(field)}
                      status={isDirty(field.name) ? 'dirty' : isOverridden(field.name) ? 'overridden' : 'default'}
                      readOnly={isReadOnly || field.editable === false}
                      onChange={(value) => setDrafts((prev) => ({ ...prev, [getFieldKey(field.name)]: value }))}
                      onCommitValue={(value) => {
                        void handleCommitField(field, value);
                      }}
                      onClear={() => {
                        void handleClearField(field.name);
                      }}
                      onUseDefault={() => {
                        handleUseDefaultFieldValue(field);
                      }}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className={styles['empty-state']}>
            <span>{selectedItem ? 'Нет данных для выбранной сущности' : 'Ничего не выбрано'}</span>
            <span className={styles['empty-hint']}>
              {selectedItem?.type === 'parameter'
                ? 'Раздел параметров пока пустой'
                : selectedItem
                  ? 'Версия не содержит полей или еще не загружена'
                  : 'Выбери агент, инструмент или оркестратор слева'}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export default ConfigPanel;
