/**
 * ModelPage — просмотр/создание/редактирование/удаление модели.
 *
 * Использует useEntityEditor для стандартной CRUD логики.
 * vectorDim — отдельный стейт, т.к. хранится в extra_config.
 */
import { useEffect, useState } from 'react';
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
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { Badge, Button, ConfirmDialog, useToast } from '@/shared/ui';

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

const PROTOCOLS: { value: ModelConnector; label: string }[] = [
  { value: 'openai_http', label: 'OpenAI HTTP' },
  { value: 'azure_openai_http', label: 'Azure OpenAI' },
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
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    placeholder: 'Описание модели...',
    rows: 3,
  },
  {
    key: 'default_for_type',
    type: 'boolean',
    label: 'По умолчанию для типа',
    description: 'Используется по умолчанию для данного типа моделей',
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
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    placeholder: 'Описание модели...',
    rows: 3,
  },
  {
    key: 'default_for_type',
    type: 'boolean',
    label: 'По умолчанию для типа',
    description: 'Используется по умолчанию для данного типа моделей',
  },
];

const CONNECTOR_FIELDS: FieldConfig[] = [
  {
    key: 'connector',
    type: 'select',
    label: 'Протокол',
    required: true,
    description: 'Транспорт/протокол обращения к модели',
    options: PROTOCOLS.map(c => ({ value: c.value, label: c.label })),
  },
  {
    key: 'instance_id',
    type: 'select',
    label: 'Коннектор',
    description: 'Источник подключения: local или удаленный model-коннектор',
  },
  {
    key: 'base_url',
    type: 'text',
    label: 'URL',
    placeholder: 'http://emb:8001',
    description: 'Прямой URL локального сервиса (используется для local)',
  },
];

const PARAMS_FIELDS: FieldConfig[] = [
  {
    key: 'provider_model_name',
    type: 'text',
    label: 'Название модели',
    required: true,
    placeholder: 'text-embedding-3-small / all-MiniLM-L6-v2',
  },
  {
    key: 'model_version',
    type: 'text',
    label: 'Версия',
    placeholder: '1.0',
  },
  {
    key: 'type',
    type: 'select',
    label: 'Тип',
    editable: true,
    options: MODEL_TYPES.map(t => ({ value: t.value, label: t.label })),
  },
  {
    key: 'max_tokens',
    type: 'number',
    label: 'Макс. токенов',
    placeholder: '512',
  },
  {
    key: 'vector_dim',
    type: 'number',
    label: 'Размерность вектора (embedding)',
    placeholder: '1536',
  },
];

const OTHER_PARAMS_FIELDS: FieldConfig[] = [
  { key: 'modality', type: 'text', label: 'Modality', editable: false },
  { key: 'description', type: 'text', label: 'Description', editable: false },
  { key: 'dimensions', type: 'text', label: 'Dimensions', editable: false },
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
  const [maxTokens, setMaxTokens] = useState<string>('');
  const [probingInfo, setProbingInfo] = useState(false);
  const [manifestRaw, setManifestRaw] = useState<Record<string, unknown>>({});
  const [healthBadge, setHealthBadge] = useState<string>('unknown');
  const LOCAL_CONNECTOR_SENTINEL = '__local__';
  const { showToast } = useToast();

  const resolveBackendConnector = (type: ModelType, instanceId: string, protocol: ModelConnector): ModelConnector => {
    if (instanceId !== LOCAL_CONNECTOR_SENTINEL) return protocol;
    if (type === 'embedding') return 'local_emb_http';
    if (type === 'reranker') return 'local_rerank_http';
    return 'local_llm_http';
  };

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
    validateCreate: (data) => {
      if (!String(data.provider_model_name || '').trim()) return 'Название модели обязательно';
      if (!String(data.model_version || '').trim()) return 'Версия модели обязательна';
      if (!String(data.type || '').trim()) return 'Тип модели обязателен';
      if (manifestRaw.max_tokens != null && maxTokens) {
        const limit = Number(manifestRaw.max_tokens);
        const current = Number(maxTokens);
        if (Number.isFinite(limit) && Number.isFinite(current) && current > limit) {
          return `Макс. токенов не должен превышать ${limit}`;
        }
      }
      return null;
    },
    validateUpdate: (data) => {
      if (!String(data.provider_model_name || '').trim()) return 'Название модели обязательно';
      if (!String(data.model_version || '').trim()) return 'Версия модели обязательна';
      if (!String(data.type || '').trim()) return 'Тип модели обязателен';
      if (manifestRaw.max_tokens != null && maxTokens) {
        const limit = Number(manifestRaw.max_tokens);
        const current = Number(maxTokens);
        if (Number.isFinite(limit) && Number.isFinite(current) && current > limit) {
          return `Макс. токенов не должен превышать ${limit}`;
        }
      }
      return null;
    },
    getInitialFormData: (m) => {
      if (m?.extra_config?.vector_dim) {
        setVectorDim(String(m.extra_config.vector_dim));
      }
      if (m?.extra_config?.max_tokens) {
        setMaxTokens(String(m.extra_config.max_tokens));
      }
      const connectorRaw = m?.connector ?? 'openai_http';
      const isLocalBackendConnector = String(connectorRaw).startsWith('local_');
      const uiProtocol: ModelConnector = isLocalBackendConnector ? 'openai_http' : connectorRaw;
      return {
        alias: m?.alias ?? '',
        name: m?.name ?? '',
        type: m?.type ?? 'llm_chat',
        connector: uiProtocol,
        provider: m?.provider ?? '',
        provider_model_name: m?.provider_model_name ?? '',
        base_url: m?.base_url ?? '',
        instance_id: m?.instance_id ?? (isLocalBackendConnector ? LOCAL_CONNECTOR_SENTINEL : ''),
        status: m?.status ?? 'available',
        enabled: m?.enabled ?? true,
        default_for_type: m?.default_for_type ?? false,
        model_version: m?.model_version ?? '',
        description: m?.description ?? '',
        extra_config: m?.extra_config ?? {},
      };
    },
    transformCreate: (data) => {
      const resolvedConnector = resolveBackendConnector(
        data.type,
        String(data.instance_id || ''),
        data.connector,
      );
      const extra_config: Record<string, unknown> = { ...(data.extra_config ?? {}) };
      if (data.type === 'embedding' && vectorDim) {
        extra_config.vector_dim = parseInt(vectorDim, 10);
      }
      if (maxTokens) extra_config.max_tokens = parseInt(maxTokens, 10);
      return {
        ...data,
        connector: resolvedConnector,
        base_url: String(data.instance_id || '') === LOCAL_CONNECTOR_SENTINEL ? (data.base_url || undefined) : undefined,
        instance_id: String(data.instance_id || '') === LOCAL_CONNECTOR_SENTINEL ? undefined : (data.instance_id || undefined),
        model_version: data.model_version || undefined,
        description: data.description || undefined,
        extra_config: Object.keys(extra_config).length > 0 ? extra_config : undefined,
      } as ModelCreate;
    },
    transformUpdate: (data) => {
      const resolvedConnector = resolveBackendConnector(
        data.type,
        String(data.instance_id || ''),
        data.connector,
      );
      const extra_config: Record<string, unknown> = { ...(data.extra_config ?? {}) };
      if (data.type === 'embedding' && vectorDim) {
        extra_config.vector_dim = parseInt(vectorDim, 10);
      }
      if (maxTokens) extra_config.max_tokens = parseInt(maxTokens, 10);
      return {
        name: data.name,
        connector: resolvedConnector,
        provider_model_name: data.provider_model_name,
        base_url: String(data.instance_id || '') === LOCAL_CONNECTOR_SENTINEL ? (data.base_url || undefined) : undefined,
        instance_id: String(data.instance_id || '') === LOCAL_CONNECTOR_SENTINEL ? undefined : (data.instance_id || undefined),
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
    queryKey: qk.toolInstances.list({ connector_type: 'model' }),
    queryFn: () => toolInstancesApi.list({ connector_type: 'model' }),
    staleTime: 60_000,
  });

  // ─── Derived ───
  const instanceOptions = [
    { value: LOCAL_CONNECTOR_SENTINEL, label: 'local' },
    ...instances.map((inst) => ({ value: inst.id, label: `${inst.name} (${inst.slug})` })),
  ];

  const viewData = {
    alias: model?.alias ?? '',
    name: model?.name ?? '',
    type: model?.type ?? 'llm_chat',
    description: model?.description ?? '',
    connector: String(model?.connector || '').startsWith('local_') ? 'openai_http' : (model?.connector ?? 'openai_http'),
    provider_model_name: model?.provider_model_name ?? '',
    base_url: model?.base_url ?? '',
    instance_id: model?.instance_id ?? (String(model?.connector || '').startsWith('local_') ? LOCAL_CONNECTOR_SENTINEL : ''),
    model_version: model?.model_version ?? '',
    status: model?.status ?? 'available',
    default_for_type: model?.default_for_type ?? false,
    id: model?.id ?? '',
    instance_name: model?.instance_name ?? '—',
    is_system: model?.is_system ? 'Да' : 'Нет',
    created_at: model?.created_at ?? '',
    updated_at: model?.updated_at ?? '',
  };

  const blockData = isEditable ? formData : viewData;
  const paramsData = {
    provider_model_name: blockData.provider_model_name,
    model_version: blockData.model_version,
    type: blockData.type,
    max_tokens: maxTokens,
    vector_dim: vectorDim,
  };
  const otherParamsData = {
    modality: String(manifestRaw.modality || '—'),
    description: String(manifestRaw.description || '—'),
    dimensions: String(manifestRaw.dimensions ?? '—'),
  };
  const isEmbedding = (isEditable ? formData.type : model?.type) === 'embedding';

  const healthData = {
    health_status: model?.health_status ?? 'unknown',
    health_latency_ms: model?.health_latency_ms != null ? String(model.health_latency_ms) : '—',
    health_error: model?.health_error ?? '—',
    last_health_check_at: model?.last_health_check_at ?? '',
  };

  useEffect(() => {
    setHealthBadge(String(model?.health_status || 'unknown'));
    const manifest = (model?.extra_config && typeof model.extra_config === 'object')
      ? (model.extra_config as Record<string, unknown>).manifest
      : undefined;
    if (manifest && typeof manifest === 'object') {
      setManifestRaw(manifest as Record<string, unknown>);
    } else {
      setManifestRaw({});
    }
  }, [model?.id, model?.health_status]);

  const currentInstanceId = String(isEditable ? formData.instance_id : (model?.instance_id || ''));
  const currentConnector = String(isEditable ? formData.connector : model?.connector || '');
  const isLocalConnector = currentInstanceId === LOCAL_CONNECTOR_SENTINEL || currentConnector.startsWith('local_');

  const connectorFieldsWithOptions = CONNECTOR_FIELDS
    .filter((f) => {
      if (f.key === 'base_url' && !isLocalConnector) return false;
      return true;
    })
    .map((f) => {
      if (f.key === 'instance_id') {
        return { ...f, options: instanceOptions };
      }
      if (f.key === 'provider_model_name' && isLocalConnector) {
        return { ...f, editable: false };
      }
      if (f.key === 'base_url' && isLocalConnector) {
        return {
          ...f,
          label: 'URL local-сервиса',
          placeholder: 'http://emb:8001 или http://rerank:8002',
          description: 'Базовый URL локального сервиса модели',
        };
      }
      return f;
    });

  const hasManifestMaxTokens = manifestRaw.max_tokens != null || !!maxTokens;
  const currentModelType = String(isEditable ? formData.type : (model?.type || viewData.type || ''));
  const paramsFields = PARAMS_FIELDS
    .filter((f) => {
      if (f.key === 'max_tokens') return hasManifestMaxTokens && currentModelType !== 'reranker';
      if (f.key === 'vector_dim') return isEmbedding;
      return true;
    })
    .map((f) => {
    if ((f.key === 'provider_model_name' || f.key === 'model_version') && isLocalConnector) {
      return { ...f, editable: false, description: 'Заполняется через кнопку "Проверить"' };
    }
    if (f.key === 'type' && isLocalConnector) {
      return { ...f, editable: false, description: 'Определяется автоматически из modality манифеста' };
    }
    if (f.key === 'max_tokens' && manifestRaw.max_tokens != null) {
      return { ...f, description: `Лимит по манифесту: ${String(manifestRaw.max_tokens)}` };
    }
    return f;
  });

  const handleProbeModelInfo = async () => {
    setProbingInfo(true);
    try {
      let info: { provider_model_name?: string; model_version?: string; model_type?: string; health_status?: string; raw?: Record<string, unknown> };
      if (!isNew && model?.id) {
        const verified = await adminApi.verifyModel(model.id);
        info = {
          provider_model_name: verified.provider_model_name,
          model_version: verified.model_version || '',
          model_type: (verified.resolved_type_from_manifest as string) || verified.type,
          health_status: verified.health_status || undefined,
          raw: (verified.manifest || {}) as Record<string, unknown>,
        };
      } else {
        const current = String((isEditable ? formData.base_url : viewData.base_url) || '').trim();
        if (!current) {
          showToast('Укажите URL local-сервиса', 'warning');
          return;
        }
        info = await adminApi.probeModelInfo(current);
      }

      if (info.provider_model_name) handleFieldChange('provider_model_name', info.provider_model_name);
      if (info.model_version) handleFieldChange('model_version', info.model_version);
      if (info.model_type) handleFieldChange('type', info.model_type);
      if (info.health_status) setHealthBadge(info.health_status);
      const raw = (info.raw || {}) as Record<string, unknown>;
      setManifestRaw(raw);
      const vector = raw.dimensions;
      const maxTok = raw.max_tokens;
      if (typeof vector === 'number' && Number.isFinite(vector)) setVectorDim(String(vector));
      if (typeof maxTok === 'number' && Number.isFinite(maxTok)) setMaxTokens(String(maxTok));
      showToast('Проверка выполнена', 'success');
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Не удалось выполнить проверку', 'error');
    } finally {
      setProbingInfo(false);
    }
  };

  // ─── Create mode ───
  if (isNew) {
    return (
      <EntityPageV2
        title="Новая модель"
        mode="create"
        saving={saving}
        headerActions={(
          <Button variant="outline" onClick={handleProbeModelInfo} disabled={probingInfo}>
            {probingInfo ? 'Проверяем...' : 'Проверить'}
          </Button>
        )}
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
            title="Параметры модели"
            icon="settings"
            iconVariant="warning"
            width="1/2"
            fields={paramsFields}
            data={paramsData}
            editable
            onChange={(key, value) => {
              if (key === 'max_tokens') setMaxTokens(String(value ?? ''));
              else if (key === 'vector_dim') setVectorDim(String(value ?? ''));
              else handleFieldChange(key, value);
            }}
          />
          <Block
            title="Остальные параметры"
            icon="database"
            iconVariant="info"
            width="1/2"
            fields={OTHER_PARAMS_FIELDS}
            data={otherParamsData}
          />
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
        headerActions={isEditable ? (
          <Button variant="outline" onClick={handleProbeModelInfo} disabled={probingInfo}>
            {probingInfo ? 'Проверяем...' : 'Проверить'}
          </Button>
        ) : undefined}
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
              healthBadge && healthBadge !== 'unknown' ? (
                <Badge tone={healthBadge === 'healthy' ? 'success' : healthBadge === 'degraded' ? 'warn' : 'danger'}>
                  {healthBadge}
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
            title="Параметры модели"
            icon="settings"
            iconVariant="warning"
            width="1/2"
            fields={paramsFields}
            data={paramsData}
            editable={isEditable}
            onChange={(key, value) => {
              if (key === 'max_tokens') setMaxTokens(String(value ?? ''));
              else if (key === 'vector_dim') setVectorDim(String(value ?? ''));
              else handleFieldChange(key, value);
            }}
          />
          <Block
            title="Остальные параметры"
            icon="database"
            iconVariant="info"
            width="1/2"
            fields={OTHER_PARAMS_FIELDS}
            data={otherParamsData}
          />
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
