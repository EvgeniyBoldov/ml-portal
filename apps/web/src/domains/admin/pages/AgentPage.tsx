/**
 * AgentPage - Admin page for managing Agents
 * 
 * Uses Block + GridLayout system for structured layout.
 * Data flows: API types → formData state → Block fields.
 * No mappers, no intermediate interfaces.
 */
import { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  agentsApi,
  adminApi,
  collectionsApi,
  type Agent,
  type AgentDetail,
  type AgentCreate,
  type AgentUpdate,
  type AgentVersion,
  type AgentVersionInfo,
  type Collection,
  type Model,
} from '@/shared/api';
import { lifecycleApi } from '@/shared/api/lifecycle';
import { qk } from '@/shared/api/keys';
import { useAgentDetail } from '@/shared/api/hooks/useAgents';
import { useAgentExecutionLimits, useUpdateAgentExecutionLimits } from '@/shared/api/hooks/usePlatformSettings';
import type { QueryKey } from '@tanstack/react-query';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui';
import { buildEntityCrudActions } from '@/shared/ui/EntityPage/entityCrudActions';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { VersionsBlock } from '@/shared/ui/VersionsBlock';
import DataTable, { type DataTableColumn } from '@/shared/ui/DataTable';
import Button from '@/shared/ui/Button';
import LifecycleDeleteDialog from '@/shared/ui/LifecycleDeleteDialog';
import FormModal from '@/shared/ui/FormModal';
import { Select } from '@/shared/ui/Select';

/* ─── Field configs ─── */

// Prompt parts
const PROMPT_FIELDS: FieldConfig[] = [
  {
    key: 'identity',
    type: 'textarea',
    label: 'Identity',
    description: 'Роль/персона',
    placeholder: 'Ты — senior network engineer...',
    rows: 3,
  },
  {
    key: 'mission',
    type: 'textarea',
    label: 'Mission',
    description: 'Предназначение агента',
    placeholder: 'Помогаешь диагностировать и решать сетевые проблемы...',
    rows: 4,
  },
  {
    key: 'scope',
    type: 'textarea',
    label: 'Scope',
    description: 'Границы (что делает / что НЕ делает)',
    placeholder: 'Работаешь только с сетевым оборудованием. НЕ занимаешься серверами...',
    rows: 4,
  },
];

const RULES_FIELDS: FieldConfig[] = [
  {
    key: 'rules',
    type: 'textarea',
    label: 'Rules',
    description: 'Алгоритм/гайдлайны',
    placeholder: '1. Сначала уточни hostname или IP...',
    rows: 6,
  },
  {
    key: 'tool_use_rules',
    type: 'textarea',
    label: 'Tool Use Rules',
    description: 'Когда/как вызывать инструменты',
    placeholder: 'Всегда вызывай netbox_search перед изменениями...',
    rows: 6,
  },
];

const OUTPUT_FIELDS: FieldConfig[] = [
  {
    key: 'output_format',
    type: 'textarea',
    label: 'Output Format',
    description: 'Структура ответа',
    placeholder: 'Отвечай в формате:\n## Диагноз\n## Шаги\n## Результат',
    rows: 5,
  },
  {
    key: 'examples',
    type: 'textarea',
    label: 'Examples',
    description: 'Few-shot примеры ответов',
    placeholder: 'User: проверь статус свитча...\nAssistant: ...',
    rows: 5,
  },
];

// Agent-level execution config (editable on Overview tab)
const AGENT_EXEC_FIELDS: FieldConfig[] = [
  {
    key: 'model',
    type: 'select',
    label: 'Модель',
    description: 'LLM модель (override глобальной)',
    options: [],
  },
  {
    key: 'temperature',
    type: 'number',
    label: 'Temperature',
    description: 'Температура генерации (0.0–1.0)',
    placeholder: '0.7',
    step: 0.1,
    min: 0,
    max: 1,
  },
  {
    key: 'requires_confirmation_for_write',
    type: 'boolean',
    label: 'Подтверждение write-операций',
    description: 'Требует подтверждения перед изменением данных',
  },
  {
    key: 'risk_level',
    type: 'select',
    label: 'Уровень риска',
    description: 'Риск агента',
    options: [
      { value: 'low', label: 'Low' },
      { value: 'medium', label: 'Medium' },
      { value: 'high', label: 'High' },
    ],
  },
  {
    key: 'logging_level',
    type: 'select',
    label: 'Логирование',
    description: 'Уровень детализации трейса запуска',
    options: [
      { value: 'none', label: 'None — не логировать' },
      { value: 'errors', label: 'Errors — только ошибки' },
      { value: 'brief', label: 'Brief — метаданные (по умолчанию)' },
      { value: 'full', label: 'Full — всё включая промты и ответы' },
    ],
  },
];

const AGENT_LIMIT_FIELDS: FieldConfig[] = [
  { key: 'llm_input_tokens_max', type: 'number', label: 'LLM input токены', description: 'Лимит токенов входного промпта для одного LLM-вызова.' },
  { key: 'llm_output_tokens_max', type: 'number', label: 'LLM output токены', description: 'Лимит токенов ответа для одного LLM-вызова.' },
  { key: 'llm_context_window_max', type: 'number', label: 'LLM context window', description: 'Лимит input+output токенов в одном LLM-вызове.' },
  { key: 'runtime_steps_max', type: 'number', label: 'Runtime шаги', description: 'Лимит шагов агентского рантайма.' },
  { key: 'runtime_tool_calls_max', type: 'number', label: 'Runtime вызовы инструментов', description: 'Лимит числа tool-вызовов за ран.' },
  { key: 'runtime_retries_max', type: 'number', label: 'Runtime ретраи', description: 'Лимит повторных попыток.' },
  { key: 'runtime_wall_time_ms_max', type: 'number', label: 'Runtime wall time (ms)', description: 'Лимит общего времени выполнения в мс.' },
  { key: 'runtime_tokens_total_max', type: 'number', label: 'Runtime total токены', description: 'Лимит суммарных токенов рантайма.' },
];

const INFO_FIELDS: FieldConfig[] = [
  {
    key: 'name',
    type: 'text',
    label: 'Название',
    required: true,
    placeholder: 'Network Engineer Helper',
  },
  {
    key: 'slug',
    type: 'text',
    label: 'Slug (ID)',
    required: true,
    editable: false,
    placeholder: 'network-assistant',
  },
  {
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    placeholder: 'Описание агента...',
    rows: 3,
  },
  {
    key: 'tags',
    type: 'tags',
    label: 'Теги',
    description: 'Категории для каталога и семантического роутинга',
    placeholder: 'network, netbox, diagnostics',
  },
  {
    key: 'provides_keys',
    type: 'tags',
    label: 'Provides Keys',
    description: 'Machine-readable ключи для needs-роутинга (например: lun_uuid, vlan_id)',
    placeholder: 'lun_uuid, vlan_id, ip_address',
  },
];


/* ─── Component ─── */

export function AgentPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [limitsMode, setLimitsMode] = useState<'view' | 'edit'>('view');
  const [limitsForm, setLimitsForm] = useState<Record<string, unknown>>({});
  const [isAddDataModalOpen, setIsAddDataModalOpen] = useState(false);
  const [selectedCollectionId, setSelectedCollectionId] = useState('');
  const [selectedCollectionIds, setSelectedCollectionIds] = useState<Set<string>>(new Set());

  const {
    mode, isNew, entity: agent, isLoading, saving,
    formData, handleFieldChange, handleSave, handleEdit, handleCancel,
    breadcrumbs,
  } = useAgentDetail(id ?? 'new');

  const handleDelete = () => setShowDeleteConfirm(true);
  const restoreMutation = useMutation({
    mutationFn: () => lifecycleApi.restoreEntity('agent', id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.list({}) });
      if (id) {
        queryClient.invalidateQueries({ queryKey: qk.agents.detail(id) });
      }
    },
  });

  // Load LLM models for dropdown
  const { data: modelsData } = useQuery({
    queryKey: qk.admin.models.list({}),
    queryFn: () => adminApi.getModels({ type: 'llm_chat', enabled_only: true }),
  });
  const models: Model[] = modelsData?.items ?? [];

  // Filter only LLM models and create options
  const modelOptions = [
    { value: '', label: '— по умолчанию —' },
    ...models
      .filter(m => m.type === 'llm_chat' && m.enabled)
      .map(m => ({ value: m.alias, label: `${m.name} (${m.alias})` })),
  ];

  const { data: agentLimits } = useAgentExecutionLimits(agent?.slug);
  const updateAgentLimits = useUpdateAgentExecutionLimits(agent?.slug);

  // Update INFO_FIELDS: slug editable only on create
  const infoFieldsWithModels = INFO_FIELDS.map((field) => {
    if (field.key === 'slug') {
      return { ...field, editable: mode === 'create' };
    }
    return field;
  });

  // Update AGENT_EXEC_FIELDS with dynamic model options
  const execFieldsWithModels = AGENT_EXEC_FIELDS.map((field) => {
    if (field.key === 'model') {
      return { ...field, options: modelOptions };
    }
    return field;
  });

  // Load current version data (by version number)
  const currentVersionInfo =
    agent?.versions?.find(v => v.id === agent?.current_version_id) ||
    agent?.versions?.find(v => v.status === 'published');
  const { data: currentVersion } = useQuery({
    queryKey: ['agents', 'version', id!, currentVersionInfo?.version || 1] as QueryKey,
    queryFn: () => agentsApi.getVersion(id!, currentVersionInfo?.version || 1),
    enabled: !isNew && !!currentVersionInfo,
  });

  const { data: collectionsData } = useQuery({
    queryKey: qk.collections.adminList({ page: 1, size: 100 }),
    queryFn: () => collectionsApi.listAll({ page: 1, size: 100 }),
    enabled: !isNew,
    staleTime: 30_000,
  });

  const versions = agent?.versions ?? [];
  const primaryVersion = agent?.versions?.find((v: AgentVersionInfo) => v.status === 'published') || agent?.versions?.[0];

  // ─── Derived data for blocks ───
  const infoData = mode === 'edit' || mode === 'create' ? formData : {
    slug: agent?.slug || '',
    name: agent?.name || '',
    description: agent?.description || '',
    tags: agent?.tags || [],
    provides_keys: agent?.provides_keys || [],
  };

  const execData = mode === 'edit' || mode === 'create' ? formData : {
    model: agent?.model || '',
    temperature: agent?.temperature ?? null,
    requires_confirmation_for_write: agent?.requires_confirmation_for_write ?? false,
    risk_level: agent?.risk_level || '',
    logging_level: agent?.logging_level || 'brief',
  };

  // Version data (read-only from current version)
  const versionData = currentVersion ? {
    // Prompt parts
    identity: currentVersion.identity ?? '',
    mission: currentVersion.mission ?? '',
    scope: currentVersion.scope ?? '',
    rules: currentVersion.rules ?? '',
    tool_use_rules: currentVersion.tool_use_rules ?? '',
    output_format: currentVersion.output_format ?? '',
    examples: currentVersion.examples ?? '',
    // Safety prompt constraints
    never_do: currentVersion.never_do ?? '',
    allowed_ops: currentVersion.allowed_ops ?? '',
    tags: currentVersion.tags ?? [],
    notes: currentVersion.notes ?? '',
  } : {
    identity: '', mission: '', scope: '', rules: '', tool_use_rules: '',
    output_format: '', examples: '', never_do: '', allowed_ops: '',
    tags: [], notes: ''
  };

  const allowedCollectionIds = useMemo(
    () => Array.isArray(agent?.allowed_collection_ids) ? agent.allowed_collection_ids : [],
    [agent?.allowed_collection_ids],
  );

  const collectionsWithBindings = useMemo(() => {
    const source = collectionsData?.items ?? [];
    return source.filter((collection) => !!collection.data_instance_id);
  }, [collectionsData?.items]);

  const availableCollectionOptions = useMemo(() => {
    return collectionsWithBindings
      .filter((collection) => !allowedCollectionIds.includes(collection.id))
      .map((collection) => ({
        value: collection.id,
        label: `${collection.name} (${collection.slug})`,
      }));
  }, [collectionsWithBindings, allowedCollectionIds]);

  const dataBindingRows = useMemo(() => {
    const collectionById = new Map<string, Collection>(
      collectionsWithBindings.map((collection) => [collection.id, collection]),
    );
    return allowedCollectionIds.map((collectionId) => {
      const collection = collectionById.get(collectionId);
      return {
        id: collectionId,
        collection_name: collection?.name ?? '—',
        collection_slug: collection?.slug ?? '—',
        collection_type: collection?.collection_type ?? '—',
        collection_id: collectionId,
      };
    });
  }, [allowedCollectionIds, collectionsWithBindings]);

  const dataBindingColumns: DataTableColumn<{
    id: string;
    collection_name: string;
    collection_slug: string;
    collection_type: string;
    collection_id: string;
  }>[] = [
    { key: 'collection_name', label: 'Коллекция', render: (row) => row.collection_name },
    { key: 'collection_slug', label: 'Slug коллекции', render: (row) => <code>{row.collection_slug}</code> },
    { key: 'collection_type', label: 'Тип', render: (row) => row.collection_type },
    { key: 'collection_id', label: 'ID коллекции', render: (row) => <code>{row.collection_id}</code> },
  ];

  const updateBindingsMutation = useMutation({
    mutationFn: async (nextCollectionIds: string[]) => {
      if (!id) return;
      await agentsApi.update(id, {
        allowed_collection_ids: nextCollectionIds,
      });
    },
    onSuccess: async () => {
      if (!id) return;
      await queryClient.invalidateQueries({ queryKey: qk.agents.detail(id) });
      setSelectedCollectionIds(new Set());
    },
  });

  const openAddDataModal = () => {
    setSelectedCollectionId(availableCollectionOptions[0]?.value ?? '');
    setIsAddDataModalOpen(true);
  };

  const handleAddDataBinding = async () => {
    const selectedCollection = collectionsWithBindings.find((collection) => collection.id === selectedCollectionId);
    if (!selectedCollection) return;
    const next = Array.from(new Set([...allowedCollectionIds, selectedCollection.id]));
    await updateBindingsMutation.mutateAsync(next);
    setIsAddDataModalOpen(false);
  };

  const handleRemoveSelectedBindings = async () => {
    const toRemove = selectedCollectionIds;
    if (toRemove.size === 0) return;
    const next = allowedCollectionIds.filter((collectionId) => !toRemove.has(collectionId));
    await updateBindingsMutation.mutateAsync(next);
  };

  // ─── Render ───
  return (
    <>
      <EntityPageV2
        title={isNew ? 'Новый агент' : agent?.name || 'Агент'}
        mode={mode}
        breadcrumbs={breadcrumbs}
        loading={!isNew && isLoading}
        saving={saving}
        backPath="/admin/agents"
        onSave={handleSave}
        onCancel={handleCancel}
        onDelete={handleDelete}
      >
      <Tab
        title="Обзор"
          layout="grid"
          id="overview"
          actions={buildEntityCrudActions({
            mode,
            saving,
            tone: 'default',
            lifecycleStatus: agent?.lifecycle_status,
            onEdit: handleEdit,
            onSave: handleSave,
            onCancel: handleCancel,
            onDelete: () => setShowDeleteConfirm(true),
            onRestore: () => restoreMutation.mutate(),
            restorePending: restoreMutation.isPending,
          })}
        >
          {/* Row 1: Basic Info (1/2) + Routing (1/2) */}
          <Block
            title="Основная информация"
            icon="agent"
            iconVariant="info"
            width="1/2"
            fields={infoFieldsWithModels}
            data={infoData}
            editable={mode === 'edit' || mode === 'create'}
            onChange={handleFieldChange}
          />

          {/* Row 1 right: Execution config */}
          <Block
            title="Конфигурация исполнения"
            icon="settings"
            iconVariant="primary"
            width="1/2"
            fields={execFieldsWithModels}
            data={execData}
            editable={mode === 'edit' || mode === 'create'}
            onChange={handleFieldChange}
        />
      </Tab>

      {!isNew && (
        <Tab
          title="Лимиты"
          layout="grid"
          actions={buildEntityCrudActions({
            mode: limitsMode,
            saving: updateAgentLimits.isPending,
            tone: 'default',
            onEdit: () => {
              setLimitsForm({ ...(agentLimits || {}) });
              setLimitsMode('edit');
            },
            onSave: async () => {
              await updateAgentLimits.mutateAsync(limitsForm);
              setLimitsMode('view');
            },
            onCancel: () => {
              setLimitsMode('view');
              setLimitsForm({});
            },
          })}
        >
          <Block
            title="Лимиты агента"
            icon="gauge"
            iconVariant="warning"
            width="full"
            fields={AGENT_LIMIT_FIELDS}
            data={limitsMode === 'edit' ? limitsForm : (agentLimits || {})}
            editable={limitsMode === 'edit'}
            onChange={limitsMode === 'edit' ? (key, value) => setLimitsForm((prev) => ({ ...prev, [key]: value })) : undefined}
          />
        </Tab>
      )}

        {/* ── Tab 2: Промпт (только для просмотра) ── */}
        {!isNew && currentVersionInfo && (
          <Tab title="Промпт" layout="grid" id="prompt" actions={undefined}>
            <Block
              title="Identity & Mission"
              icon="user"
              iconVariant="primary"
              width="1/2"
              fields={PROMPT_FIELDS}
              data={versionData}
              editable={false}
            />
            <Block
              title="Rules & Tool Use"
              icon="list"
              iconVariant="primary"
              width="1/2"
              fields={RULES_FIELDS}
              data={versionData}
              editable={false}
            />
            <Block
              title="Output Format & Examples"
              icon="file-text"
              iconVariant="info"
              width="full"
              fields={OUTPUT_FIELDS}
              data={versionData}
              editable={false}
            />
          </Tab>
        )}

        {/* ── Tab 3: Выполнение — только safety prompt constraints ── */}
        {!isNew && currentVersionInfo && (
          <Tab title="Выполнение" layout="grid" id="execution" actions={undefined}>
            <Block
              title="Safety Constraints"
              icon="shield"
              iconVariant="info"
              width="full"
              fields={[
                { key: 'never_do', type: 'textarea', label: 'Never Do', description: 'Что нельзя делать', rows: 4 },
                { key: 'allowed_ops', type: 'textarea', label: 'Allowed Ops', description: 'Что можно делать', rows: 4 },
              ]}
              data={versionData}
              editable={false}
            />
          </Tab>
        )}

        {!isNew && (
          <Tab
            title="Допустимые коллекции"
            layout="full"
            id="available-data"
            badge={dataBindingRows.length}
            actions={[
            <Button
              key="add-data-binding"
              onClick={openAddDataModal}
              disabled={availableCollectionOptions.length === 0 || updateBindingsMutation.isPending}
            >
                Добавить коллекцию
              </Button>,
              <Button
                key="remove-data-binding"
                variant="danger"
                onClick={handleRemoveSelectedBindings}
                disabled={selectedCollectionIds.size === 0 || updateBindingsMutation.isPending}
              >
                Удалить
              </Button>,
            ]}
          >
            <div style={{ marginBottom: 12, color: 'var(--text-secondary)', fontSize: 13 }}>
              Пустой список означает, что агент может работать с любыми коллекциями,
              разрешёнными через `permission_set`. Итоговый набор всегда вычисляется как
              пересечение прав пользователя и списка агента.
            </div>
            <DataTable
              columns={dataBindingColumns}
              data={dataBindingRows}
              keyField="id"
              emptyText="Нет связанных данных. Добавьте связь с коллекцией."
              selectable
              selectedKeys={selectedCollectionIds}
              onSelectionChange={(keys) => setSelectedCollectionIds(new Set(Array.from(keys).map(String)))}
            />
          </Tab>
        )}

        <Tab title="Версии" layout="full" badge={versions.length} actions={[
          <Button key="create" onClick={() => navigate(`/admin/agents/${id}/versions/new`)}>
            Создать версию
          </Button>
        ]}>
          <VersionsBlock
            entityType="agent"
            versions={versions}
            recommendedVersionId={agent?.current_version_id ?? undefined}
            onSelectVersion={(v) => navigate(`/admin/agents/${id}/versions/${v.version}`)}
          />
        </Tab>

      </EntityPageV2>

      <LifecycleDeleteDialog
        open={showDeleteConfirm}
        kind="agent"
        entityId={id || ''}
        entityLabel={agent?.name || 'Агент'}
        onCancel={() => setShowDeleteConfirm(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: qk.agents.list({}) });
          if (id) {
            queryClient.invalidateQueries({ queryKey: qk.agents.detail(id) });
          }
          setShowDeleteConfirm(false);
          navigate('/admin/agents');
        }}
      />

      <FormModal
        open={isAddDataModalOpen}
        title="Добавить доступные данные"
        onClose={() => setIsAddDataModalOpen(false)}
        onSubmit={handleAddDataBinding}
        saving={updateBindingsMutation.isPending}
        submitDisabled={!selectedCollectionId}
        submitLabel="Добавить"
      >
        <div style={{ display: 'grid', gap: 8 }}>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Коллекция</div>
          <Select
            value={selectedCollectionId}
            onChange={setSelectedCollectionId}
            options={availableCollectionOptions}
            placeholder="Выберите коллекцию"
          />
        </div>
      </FormModal>
    </>
  );
}

export default AgentPage;
