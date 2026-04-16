/**
 * ModelPage — просмотр/создание/редактирование/удаление модели.
 *
 * Использует useEntityEditor для стандартной CRUD логики.
 * vectorDim — отдельный стейт, т.к. хранится в extra_config.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  adminApi,
  type Model,
  type ModelCreate,
  type ModelUpdate,
  type ModelType,
  type ModelStatus,
  type ModelConnector,
} from '@/shared/api/admin';
import { toolInstancesApi } from '@/shared/api/toolInstances';
import { qk } from '@/shared/api/keys';
import { useEntityEditor } from '@/shared/hooks/useEntityEditor';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { Badge, ConfirmDialog } from '@/shared/ui';

/* ─── Constants ─── */

const MODEL_TYPES: { value: ModelType; label: string }[] = [
  { value: 'llm_chat', label: 'LLM Chat' },
  { value: 'embedding', label: 'Embedding' },
  { value: 'reranker', label: 'Reranker' },
];

const MODEL_STATUSES: { value: ModelStatus; label: string }[] = [
  { value: 'available', label: 'Доступна' },
  { value: 'unavailable', label: 'Недоступна' },
  { value: 'deprecated', label: 'Устарела' },
  { value: 'maintenance', label: 'Обслуживание' },
];

const CONNECTORS: { value: ModelConnector; label: string }[] = [
  { value: 'openai_http', label: 'OpenAI HTTP' },
  { value: 'azure_openai_http', label: 'Azure OpenAI' },
  { value: 'local_emb_http', label: 'Local Embedding (HTTP)' },
  { value: 'local_rerank_http', label: 'Local Reranker (HTTP)' },
  { value: 'local_llm_http', label: 'Local LLM (HTTP)' },
  { value: 'grpc', label: 'gRPC' },
];

/* ─── Field configs ─── */

const INFO_FIELDS_VIEW: FieldConfig[] = [
  {
    key: 'alias',
    type: 'text',
    label: 'Алиас',
    description: 'Уникальный идентификатор модели',
    editable: false,
    placeholder: 'llm.chat.default',
  },
  {
    key: 'name',
    type: 'text',
    label: 'Название',
    required: true,
    placeholder: 'GPT-4 Turbo',
  },
  {
    key: 'type',
    type: 'select',
    label: 'Тип модели',
    description: 'LLM Chat или Embedding',
    editable: false,
    options: MODEL_TYPES.map(t => ({ value: t.value, label: t.label })),
  },
  {
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    placeholder: 'Описание модели...',
    rows: 3,
  },
];

const INFO_FIELDS_CREATE: FieldConfig[] = [
  {
    key: 'alias',
    type: 'text',
    label: 'Алиас',
    description: 'Уникальный идентификатор (напр. llm.chat.default)',
    required: true,
    placeholder: 'llm.chat.default',
  },
  {
    key: 'name',
    type: 'text',
    label: 'Название',
    required: true,
    placeholder: 'GPT-4 Turbo',
  },
  {
    key: 'type',
    type: 'select',
    label: 'Тип модели',
    description: 'LLM Chat или Embedding',
    required: true,
    options: MODEL_TYPES.map(t => ({ value: t.value, label: t.label })),
  },
  {
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    placeholder: 'Описание модели...',
    rows: 3,
  },
];

const CONNECTOR_FIELDS: FieldConfig[] = [
  {
    key: 'connector',
    type: 'select',
    label: 'Коннектор',
    required: true,
    description: 'Тип подключения к модели',
    options: CONNECTORS.map(c => ({ value: c.value, label: c.label })),
  },
  {
    key: 'provider_model_name',
    type: 'text',
    label: 'Имя модели / сервиса',
    required: true,
    placeholder: 'gpt-4-turbo-preview или all-MiniLM-L6-v2',
  },
  {
    key: 'base_url',
    type: 'text',
    label: 'Base URL',
    placeholder: 'http://emb:8001',
    description: 'Прямой URL для локальных или standalone моделей',
  },
  {
    key: 'instance_id',
    type: 'select',
    label: 'Коннектор (провайдер)',
    description: 'Подключение к провайдеру (URL + креды). Для local_* рекомендуется указывать именно коннектор.',
  },
  {
    key: 'model_version',
    type: 'text',
    label: 'Версия модели',
    placeholder: 'v1.0.0',
    description: 'Версия для отслеживания изменений',
  },
];

const STATUS_FIELDS: FieldConfig[] = [
  {
    key: 'status',
    type: 'select',
    label: 'Статус',
    description: 'Доступность модели',
    options: MODEL_STATUSES.map(s => ({ value: s.value, label: s.label })),
  },
  {
    key: 'enabled',
    type: 'boolean',
    label: 'Включена',
    description: 'Модель доступна для использования',
  },
  {
    key: 'default_for_type',
    type: 'boolean',
    label: 'По умолчанию для типа',
    description: 'Используется по умолчанию для данного типа моделей',
  },
];

const EMBEDDING_FIELDS: FieldConfig[] = [
  {
    key: 'vector_dim',
    type: 'number',
    label: 'Размерность вектора',
    required: true,
    placeholder: '1536',
    description: 'Размерность векторного представления',
  },
];

const HEALTH_FIELDS: FieldConfig[] = [
  {
    key: 'health_status',
    type: 'badge',
    label: 'Health Status',
    badgeTone: 'success',
    editable: false,
  },
  {
    key: 'health_latency_ms',
    type: 'text',
    label: 'Задержка (мс)',
    editable: false,
  },
  {
    key: 'health_error',
    type: 'text',
    label: 'Ошибка',
    editable: false,
  },
  {
    key: 'last_health_check_at',
    type: 'date',
    label: 'Последняя проверка',
    editable: false,
  },
];

const META_FIELDS: FieldConfig[] = [
  { key: 'id', type: 'code', label: 'ID', editable: false },
  { key: 'instance_name', type: 'text', label: 'Коннектор', editable: false },
  { key: 'is_system', type: 'badge', label: 'Системная', badgeTone: 'warn', editable: false },
  { key: 'created_at', type: 'date', label: 'Создана', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлена', editable: false },
];

/* ─── Component ─── */

export function ModelPage() {
  const [vectorDim, setVectorDim] = useState<string>('');

  const {
    mode,
    isNew,
    isEditable,
    entity: model,
    isLoading,
    formData,
    saving,
    showDeleteConfirm,
    setShowDeleteConfirm,
    breadcrumbs,
    handleFieldChange,
    handleSave,
    handleEdit,
    handleCancel,
    handleDelete,
    handleDeleteConfirm,
  } = useEntityEditor<Model, ModelCreate, ModelUpdate>({
    entityType: 'model',
    entityNameLabel: 'Модели',
    entityTypeLabel: 'модель',
    basePath: '/admin/platform/models',
    listPath: '/admin/platform',
    api: {
      get: (id) => adminApi.getModel(id),
      create: (data) => adminApi.createModel(data),
      update: (id, data) => adminApi.updateModel(id, data),
      delete: (id) => adminApi.deleteModel(id),
    },
    queryKeys: {
      list: qk.admin.models.list({}),
      detail: (id) => qk.admin.models.detail(id),
    },
    getInitialFormData: (m) => {
      if (m?.extra_config?.vector_dim) {
        setVectorDim(String(m.extra_config.vector_dim));
      }
      return {
        alias: m?.alias ?? '',
        name: m?.name ?? '',
        type: m?.type ?? 'llm_chat',
        connector: m?.connector ?? 'openai_http',
        provider: m?.provider ?? '',
        provider_model_name: m?.provider_model_name ?? '',
        base_url: m?.base_url ?? '',
        instance_id: m?.instance_id ?? '',
        status: m?.status ?? 'available',
        enabled: m?.enabled ?? true,
        default_for_type: m?.default_for_type ?? false,
        model_version: m?.model_version ?? '',
        description: m?.description ?? '',
        extra_config: m?.extra_config ?? {},
      };
    },
    transformCreate: (data) => {
      const extra_config: Record<string, unknown> = { ...(data.extra_config ?? {}) };
      if (data.type === 'embedding' && vectorDim) {
        extra_config.vector_dim = parseInt(vectorDim, 10);
      }
      return {
        ...data,
        base_url: data.base_url || undefined,
        instance_id: data.instance_id || undefined,
        model_version: data.model_version || undefined,
        description: data.description || undefined,
        extra_config: Object.keys(extra_config).length > 0 ? extra_config : undefined,
      } as ModelCreate;
    },
    transformUpdate: (data) => {
      const extra_config: Record<string, unknown> = { ...(data.extra_config ?? {}) };
      if (data.type === 'embedding' && vectorDim) {
        extra_config.vector_dim = parseInt(vectorDim, 10);
      }
      return {
        name: data.name,
        connector: data.connector,
        provider_model_name: data.provider_model_name,
        base_url: data.base_url || undefined,
        instance_id: data.instance_id || undefined,
        status: data.status,
        enabled: data.enabled,
        default_for_type: data.default_for_type,
        model_version: data.model_version,
        description: data.description,
        ...(data.type === 'embedding' ? { extra_config } : {}),
      } as ModelUpdate;
    },
    messages: {
      create: 'Модель создана',
      update: 'Модель обновлена',
      delete: 'Модель удалена',
    },
  });

  // ─── Коннекторы для select ───
  const { data: instances = [] } = useQuery({
    queryKey: qk.toolInstances.list({ connector_type: 'model', placement: 'remote' }),
    queryFn: () => toolInstancesApi.list({ connector_type: 'model', placement: 'remote' }),
    staleTime: 60_000,
  });

  // ─── Derived ───
  const instanceOptions = [
    { value: '', label: '— Не выбран —' },
    ...instances.map((inst) => ({ value: inst.id, label: `${inst.name} (${inst.slug})` })),
  ];

  const viewData = {
    alias: model?.alias ?? '',
    name: model?.name ?? '',
    type: model?.type ?? 'llm_chat',
    description: model?.description ?? '',
    connector: model?.connector ?? 'openai_http',
    provider_model_name: model?.provider_model_name ?? '',
    base_url: model?.base_url ?? '',
    instance_id: model?.instance_id ?? '',
    model_version: model?.model_version ?? '',
    status: model?.status ?? 'available',
    enabled: model?.enabled ?? false,
    default_for_type: model?.default_for_type ?? false,
    id: model?.id ?? '',
    instance_name: model?.instance_name ?? '—',
    is_system: model?.is_system ? 'Да' : 'Нет',
    created_at: model?.created_at ?? '',
    updated_at: model?.updated_at ?? '',
  };

  const blockData = isEditable ? formData : viewData;
  const embeddingData = { vector_dim: vectorDim };
  const isEmbedding = (isEditable ? formData.type : model?.type) === 'embedding';

  const healthData = {
    health_status: model?.health_status ?? 'unknown',
    health_latency_ms: model?.health_latency_ms != null ? String(model.health_latency_ms) : '—',
    health_error: model?.health_error ?? '—',
    last_health_check_at: model?.last_health_check_at ?? '',
  };

  const currentConnector = String(isEditable ? formData.connector : model?.connector || '');
  const isLocalConnector = currentConnector.startsWith('local_');

  const connectorFieldsWithOptions = CONNECTOR_FIELDS
    .filter((f) => {
      if (f.key === 'base_url' && !isLocalConnector) return false;
      return true;
    })
    .map((f) => {
      if (f.key === 'instance_id') {
        return { ...f, options: instanceOptions };
      }
      if (f.key === 'provider_model_name' && currentConnector === 'local_emb_http') {
        return {
          ...f,
          label: 'Алиас embedding модели',
          placeholder: 'all-MiniLM-L6-v2',
          description: 'Алиас модели в emb-gateway (должен быть в EMB_MODELS).',
        };
      }
      if (f.key === 'base_url' && currentConnector === 'local_emb_http') {
        return {
          ...f,
          label: 'URL emb-gateway',
          placeholder: 'http://emb:8001',
          description: 'Базовый URL emb-сервиса (эндпоинты /embed, /embed/query, /health).',
        };
      }
      if (f.key === 'base_url' && currentConnector === 'local_rerank_http') {
        return {
          ...f,
          label: 'URL rerank-сервиса',
          placeholder: 'http://rerank:8002',
        };
      }
      return f;
    });

  // ─── Create mode ───
  if (isNew) {
    return (
      <EntityPageV2
        title="Новая модель"
        mode="create"
        saving={saving}
        breadcrumbs={[
          { label: 'Платформа', href: '/admin/platform' },
          { label: 'Новая модель' },
        ]}
        backPath="/admin/platform"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="grid">
          <Block
            title="Основная информация"
            icon="cpu"
            iconVariant="info"
            width="1/2"
            fields={INFO_FIELDS_CREATE}
            data={formData}
            editable
            onChange={handleFieldChange}
          />
          <Block
            title="Подключение"
            icon="server"
            iconVariant="primary"
            width="1/2"
            height="stretch"
            fields={connectorFieldsWithOptions}
            data={formData}
            editable
            onChange={handleFieldChange}
          />
          <Block
            title="Статус и флаги"
            icon="settings"
            iconVariant="warning"
            width="1/2"
            fields={STATUS_FIELDS}
            data={formData}
            editable
            onChange={handleFieldChange}
          />
          {isEmbedding && (
            <Block
              title="Настройки эмбеддинга"
              icon="brain"
              iconVariant="info"
              width="1/2"
              fields={EMBEDDING_FIELDS}
              data={embeddingData}
              editable
              onChange={(_key, value) => setVectorDim(String(value))}
            />
          )}
        </Tab>
      </EntityPageV2>
    );
  }

  // ─── View / Edit mode ───
  return (
    <>
      <EntityPageV2
        title={model?.name ?? 'Модель'}
        mode={mode}
        loading={isLoading}
        saving={saving}
        breadcrumbs={[
          { label: 'Платформа', href: '/admin/platform' },
          { label: model?.name || 'Модель' },
        ]}
        onEdit={handleEdit}
        onSave={handleSave}
        onCancel={handleCancel}
        onDelete={!model?.is_system ? handleDelete : undefined}
        showDelete={!model?.is_system}
      >
        <Tab title="Обзор" layout="grid" id="overview">
          <Block
            title="Основная информация"
            icon="cpu"
            iconVariant="info"
            width="1/2"
            fields={INFO_FIELDS_VIEW}
            data={blockData}
            editable={isEditable}
            onChange={handleFieldChange}
            headerActions={
              model?.health_status ? (
                <Badge tone={model.health_status === 'healthy' ? 'success' : model.health_status === 'degraded' ? 'warn' : 'danger'}>
                  {model.health_status}
                </Badge>
              ) : undefined
            }
          />
          <Block
            title="Подключение"
            icon="server"
            iconVariant="primary"
            width="1/2"
            height="stretch"
            fields={connectorFieldsWithOptions}
            data={blockData}
            editable={isEditable}
            onChange={handleFieldChange}
          />
          <Block
            title="Статус и флаги"
            icon="settings"
            iconVariant="warning"
            width="1/2"
            fields={STATUS_FIELDS}
            data={blockData}
            editable={isEditable}
            onChange={handleFieldChange}
          />
          {isEmbedding && (
            <Block
              title="Настройки эмбеддинга"
              icon="brain"
              iconVariant="info"
              width="1/2"
              fields={EMBEDDING_FIELDS}
              data={embeddingData}
              editable={isEditable}
              onChange={(_key, value) => setVectorDim(String(value))}
            />
          )}
          <Block
            title="Метаданные"
            icon="database"
            iconVariant="info"
            width="full"
            fields={META_FIELDS}
            data={blockData}
          />
        </Tab>

        <Tab title="Health" layout="full" id="health">
          <Block
            title="Состояние модели"
            icon="activity"
            iconVariant="warning"
            width="full"
            fields={HEALTH_FIELDS}
            data={healthData}
          />
        </Tab>
      </EntityPageV2>

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить модель?"
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={handleDeleteConfirm}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}

export default ModelPage;
