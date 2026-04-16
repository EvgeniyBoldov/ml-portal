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
import { qk } from '@/shared/api/keys';
import { useAgentDetail } from '@/shared/api/hooks/useAgents';
import type { QueryKey } from '@tanstack/react-query';
import Badge from '@/shared/ui/Badge';
import { EntityPageV2, Tab, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { VersionsBlock } from '@/shared/ui/VersionsBlock';
import DataTable, { type DataTableColumn } from '@/shared/ui/DataTable';
import Button from '@/shared/ui/Button';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
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

// Execution config
const EXEC_FIELDS: FieldConfig[] = [
  {
    key: 'timeout_s',
    type: 'number',
    label: 'Таймаут (сек)',
    placeholder: '120',
  },
  {
    key: 'max_steps',
    type: 'number',
    label: 'Макс. шагов',
    placeholder: '10',
  },
  {
    key: 'max_retries',
    type: 'number',
    label: 'Макс. ретраев',
    placeholder: '3',
  },
  {
    key: 'max_tokens',
    type: 'number',
    label: 'Макс. токенов',
    placeholder: '4096',
  },
  {
    key: 'temperature',
    type: 'number',
    label: 'Temperature',
    placeholder: '0.2',
  },
];

// Safety knobs
const SAFETY_FIELDS: FieldConfig[] = [
  {
    key: 'requires_confirmation_for_write',
    type: 'boolean',
    label: 'Write',
    description: 'Требует подтверждения для write-операций',
  },
  {
    key: 'risk_level',
    type: 'select',
    label: 'Risk Level',
    description: 'Уровень риска',
    options: [
      { value: 'low', label: 'Low' },
      { value: 'medium', label: 'Medium' },
      { value: 'high', label: 'High' },
    ],
  },
  {
    key: 'never_do',
    type: 'textarea',
    label: 'Never Do',
    description: 'Что нельзя делать',
    placeholder: 'Никогда не удаляй данные без бэкапа...',
    rows: 3,
  },
  {
    key: 'allowed_ops',
    type: 'textarea',
    label: 'Allowed Ops',
    description: 'Что можно делать',
    placeholder: 'read, search, create_ticket...',
    rows: 3,
  },
];

// Routing
const ROUTING_FIELDS: FieldConfig[] = [
  {
    key: 'short_info',
    type: 'textarea',
    label: 'Short Info',
    description: 'Краткое описание для роутера',
    placeholder: 'Одна фраза — что делает агент и когда его вызывать...',
    rows: 2,
  },
  {
    key: 'tags',
    type: 'tags',
    label: 'Теги',
    description: 'Теги для роутинга и фильтрации',
    placeholder: 'network security monitoring...',
  },
  {
    key: 'is_routable',
    type: 'boolean',
    label: 'Доступен для авто-роутинга',
    description: 'Может ли агент быть автоматически выбран роутером',
  },
  {
    key: 'routing_keywords',
    type: 'tags',
    label: 'Ключевые слова',
    description: 'Слова для поиска (5-30)',
    placeholder: 'тикет инцидент алерт падение...',
  },
  {
    key: 'routing_negative_keywords',
    type: 'tags',
    label: 'Стоп-слова',
    description: 'Слова которые должны исключить выбор агента',
    placeholder: 'продажи маркетинг аналитика...',
  },
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
    editable: false,
    placeholder: 'network-assistant',
  },
  {
    key: 'model',
    type: 'select',
    label: 'Модель',
    description: 'LLM модель для агента (override глобальной)',
    options: [],
  },
  {
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    placeholder: 'Описание агента...',
    rows: 3,
  },
];

const STATS_FIELDS: FieldConfig[] = [
  { key: 'versions_count', type: 'badge', label: 'Всего версий', badgeTone: 'neutral', editable: false },
  { key: 'primary_version', type: 'badge', label: 'Основная версия', badgeTone: 'success', editable: false },
];

/* ─── Component ─── */

export function AgentPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isAddDataModalOpen, setIsAddDataModalOpen] = useState(false);
  const [selectedCollectionId, setSelectedCollectionId] = useState('');
  const [selectedCollectionIds, setSelectedCollectionIds] = useState<Set<string>>(new Set());

  const {
    mode, isNew, entity: agent, isLoading, saving,
    formData, handleFieldChange, handleSave, handleEdit, handleCancel, handleDeleteConfirm,
    breadcrumbs,
  } = useAgentDetail(id ?? 'new');

  const handleDelete = () => setShowDeleteConfirm(true);

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

  // Update INFO_FIELDS with dynamic model options
  const infoFieldsWithModels = INFO_FIELDS.map((field) => {
    if (field.key === 'model') {
      return { ...field, options: modelOptions };
    }
    if (field.key === 'slug') {
      return { ...field, editable: mode === 'create' };
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
    queryKey: qk.collections.list({}),
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
    model: agent?.model || '',
    tags: agent?.tags || [],
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
    // Execution config
    model: currentVersion.model ?? '',
    timeout_s: currentVersion.timeout_s ?? null,
    max_steps: currentVersion.max_steps ?? null,
    max_retries: currentVersion.max_retries ?? null,
    max_tokens: currentVersion.max_tokens ?? null,
    temperature: currentVersion.temperature ?? null,
    // Safety knobs
    requires_confirmation_for_write: currentVersion.requires_confirmation_for_write ?? false,
    risk_level: currentVersion.risk_level ?? '',
    never_do: currentVersion.never_do ?? '',
    allowed_ops: currentVersion.allowed_ops ?? '',
    // Routing
    short_info: currentVersion.short_info ?? '',
    tags: currentVersion.tags ?? [],
    is_routable: currentVersion.is_routable ?? false,
    routing_keywords: currentVersion.routing_keywords ?? [],
    routing_negative_keywords: currentVersion.routing_negative_keywords ?? [],
    notes: currentVersion.notes ?? '',
  } : {
    // Default empty data when loading
    identity: '', mission: '', scope: '', rules: '', tool_use_rules: '', 
    output_format: '', examples: '', model: '', timeout_s: null, max_steps: null, 
    max_retries: null, max_tokens: null, temperature: null, 
    requires_confirmation_for_write: false, risk_level: '', never_do: '', 
    allowed_ops: '', short_info: '', tags: [], is_routable: false, 
    routing_keywords: [], routing_negative_keywords: [], notes: ''
  };

  const statsData = {
    versions_count: `${versions.length}`,
    primary_version: primaryVersion ? `v${primaryVersion.version}` : 'Нет',
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
          actions={
            mode === 'view' ? [
              <Button key="edit" onClick={handleEdit}>Редактировать</Button>,
              <Button key="delete" variant="danger" onClick={() => setShowDeleteConfirm(true)}>
                Удалить
              </Button>,
            ] : mode === 'edit' ? [
              <Button key="save" onClick={handleSave} disabled={saving}>
                {saving ? 'Сохранение...' : 'Сохранить'}
              </Button>,
              <Button key="cancel" variant="outline" onClick={handleCancel}>Отмена</Button>,
            ] : mode === 'create' ? [
              <Button key="cancel" variant="outline" onClick={handleCancel} disabled={saving}>
                Отмена
              </Button>,
              <Button key="create" onClick={handleSave} disabled={saving}>
                {saving ? 'Создание...' : 'Создать'}
              </Button>,
            ] : []
          }
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

          {/* Row 2: Stats (1/2) + Empty (1/2) */}
          <Block
            title="Статистика"
            icon="chart"
            iconVariant="success"
            width="1/2"
            fields={STATS_FIELDS}
            data={statsData}
          />
        </Tab>

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

        {/* ── Tab 3: Выполнение (только для просмотра) ── */}
        {!isNew && currentVersionInfo && (
          <Tab title="Выполнение" layout="grid" id="execution" actions={undefined}>
            <Block
              title="Execution Config"
              icon="settings"
              iconVariant="primary"
              width="1/2"
              fields={EXEC_FIELDS}
              data={versionData}
              editable={false}
            />
            <Block
              title="Safety Knobs"
              icon="shield"
              iconVariant="info"
              width="1/2"
              fields={SAFETY_FIELDS}
              data={versionData}
              editable={false}
            />
          </Tab>
        )}

        {/* ── Tab 4: Роутинг (только для просмотра) ── */}
        {!isNew && currentVersionInfo && (
          <Tab title="Роутинг" layout="grid" id="routing" actions={undefined}>
            <Block
              title="Настройки роутинга"
              icon="route"
              iconVariant="primary"
              width="1/2"
              fields={ROUTING_FIELDS.slice(0, 3)} // short_info, tags, is_routable
              data={versionData}
              editable={false}
            />
            <Block
              title="Ключевые слова"
              icon="search"
              iconVariant="info"
              width="1/2"
              fields={ROUTING_FIELDS.slice(3)} // routing_keywords, routing_negative_keywords
              data={versionData}
              editable={false}
            />
          </Tab>
        )}

        {!isNew && (
          <Tab
            title="Доступные данные"
            layout="full"
            id="available-data"
            badge={dataBindingRows.length}
            actions={[
            <Button
              key="add-data-binding"
              onClick={openAddDataModal}
              disabled={availableCollectionOptions.length === 0 || updateBindingsMutation.isPending}
            >
                Добавить
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

      {/* Delete confirmation dialog */}
      {showDeleteConfirm && (
        <ConfirmDialog
          open={true}
          title="Удалить агента?"
          message={`Вы уверены, что хотите удалить агента "${agent?.name}"? Это действие нельзя отменить.`}
          confirmLabel="Удалить"
          cancelLabel="Отмена"
          onConfirm={() => {
            handleDeleteConfirm();
            setShowDeleteConfirm(false);
          }}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      )}

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
