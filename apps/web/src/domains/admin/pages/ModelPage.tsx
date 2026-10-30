/**
 * ModelPage — просмотр/создание/редактирование/удаление модели.
 *
 * Использует useEntityEditor для стандартной CRUD логики.
 * Encoder capabilities are typed registry fields.
 */
import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  adminApi,
  type Model,
  type ModelCreate,
  type ModelUpdate,
  type ModelType,
  type ModelConnector,
} from '@/shared/api/admin';
import { toolInstancesApi } from '@/shared/api/toolInstances';
import { qk } from '@/shared/api/keys';
import { useEntityEditor } from '@/shared/hooks/useEntityEditor';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { buildEntityCrudActions } from '@/shared/ui/EntityPage/entityCrudActions';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { Button, ConfirmDialog, Modal, Select, useToast } from '@/shared/ui';
import styles from './ModelPage.module.css';
import { modelCharacteristicFields } from './modelPageFields';
import { ModelConfigurationBlocks } from './ModelConfigurationBlocks';

/* ─── Constants ─── */

const MODEL_TYPES: { value: ModelType; label: string }[] = [
  { value: 'llm_chat', label: 'LLM Chat' },
  { value: 'embedding', label: 'Embedding' },
  { value: 'reranker', label: 'Reranker' },
];

const PROTOCOLS: { value: ModelConnector; label: string }[] = [
  { value: 'openai_http', label: 'OpenAI HTTP' },
  { value: 'litellm_http', label: 'LiteLLM' },
  { value: 'azure_openai_http', label: 'Azure OpenAI' },
  { value: 'grpc', label: 'gRPC' },
  { value: 'local_emb_http', label: 'Embedding Gateway' },
  { value: 'local_rerank_http', label: 'Reranker Gateway' },
  { value: 'local_llm_http', label: 'Локальный LLM' },
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
    label: 'Задержка проверки (мс)',
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
  {
    key: 'is_system',
    type: 'badge',
    label: 'Системная',
    badgeTone: 'warn',
    editable: false,
  },
  { key: 'created_at', type: 'date', label: 'Создана', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлена', editable: false },
];

/* ─── Component ─── */

export function ModelPage() {
  const [vectorDim, setVectorDim] = useState<string>('');
  const [contextWindow, setContextWindow] = useState<string>('');
  const [requestTimeout, setRequestTimeout] = useState<string>('');
  const [maxRetries, setMaxRetries] = useState<string>('');
  const [probingInfo, setProbingInfo] = useState(false);
  const [manifestRaw, setManifestRaw] = useState<Record<string, unknown>>({});
  const [maxInputTokens, setMaxInputTokens] = useState('');
  const [healthBadge, setHealthBadge] = useState<string>('unknown');
  const [showMigrationModal, setShowMigrationModal] = useState(false);
  const [migrationTargetModelId, setMigrationTargetModelId] =
    useState<string>('');
  const LOCAL_CONNECTOR_SENTINEL = '__local__';
  const { showToast } = useToast();
  const queryClient = useQueryClient();

  const resolveBackendConnector = (
    type: ModelType,
    instanceId: string,
    protocol: ModelConnector
  ): ModelConnector => {
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
      get: id => adminApi.getModel(id),
      create: data => adminApi.createModel(data),
      update: (id, data) => adminApi.updateModel(id, data),
      delete: id => adminApi.deleteModel(id),
    },
    queryKeys: {
      list: qk.admin.models.list({}),
      detail: id => qk.admin.models.detail(id),
    },
    validateCreate: data => {
      if (!String(data.provider_model_name || '').trim())
        return 'Название модели обязательно';
      if (!String(data.type || '').trim()) return 'Тип модели обязателен';

      return null;
    },
    validateUpdate: data => {
      if (!String(data.provider_model_name || '').trim())
        return 'Название модели обязательно';
      if (!String(data.type || '').trim()) return 'Тип модели обязателен';

      return null;
    },
    getInitialFormData: m => {
      setVectorDim(String(m?.embedding_dimensions ?? ''));
      setMaxInputTokens(String(m?.max_input_tokens ?? ''));
      setContextWindow(String(m?.context_window_tokens ?? ''));
      setRequestTimeout(String(m?.request_timeout_s ?? ''));
      setMaxRetries(String(m?.max_retries ?? ''));
      const connectorRaw = m?.connector ?? 'openai_http';
      const isLocalBackendConnector = String(connectorRaw).startsWith('local_');
      const uiProtocol: ModelConnector = connectorRaw;
      return {
        alias: m?.alias ?? '',
        name: m?.name ?? '',
        type: m?.type ?? 'llm_chat',
        connector: uiProtocol,
        provider: m?.provider ?? '',
        provider_model_name: m?.provider_model_name ?? '',
        base_url: m?.base_url ?? '',
        instance_id:
          m?.instance_id ??
          (isLocalBackendConnector ? LOCAL_CONNECTOR_SENTINEL : ''),
        status: m?.status ?? 'available',
        enabled: m?.enabled ?? true,
        default_for_type: m?.default_for_type ?? false,
        use_for_long_memory: m?.use_for_long_memory ?? false,
        model_version: m?.model_version ?? '',
        description: m?.description ?? '',
        extra_config: m?.extra_config ?? {},
        vector_normalized: m?.vector_normalized ?? null,
      };
    },
    transformCreate: data => {
      const resolvedConnector = resolveBackendConnector(
        data.type,
        String(data.instance_id || ''),
        data.connector
      );
      const extra_config: Record<string, unknown> = {
        ...(data.extra_config ?? {}),
      };
      delete extra_config.vector_dim;
      delete extra_config.dimensions;
      return {
        ...data,
        use_for_long_memory:
          data.type === 'embedding' ? data.use_for_long_memory : false,
        connector: resolvedConnector,
        base_url:
          String(data.instance_id || '') === LOCAL_CONNECTOR_SENTINEL
            ? data.base_url || undefined
            : undefined,
        instance_id:
          String(data.instance_id || '') === LOCAL_CONNECTOR_SENTINEL
            ? undefined
            : data.instance_id || undefined,
        model_version: data.model_version || undefined,
        description: data.description || undefined,
        extra_config:
          Object.keys(extra_config).length > 0 ? extra_config : undefined,
        ...(data.type === 'embedding'
          ? {
              embedding_dimensions: vectorDim ? Number(vectorDim) : null,
              vector_normalized: data.vector_normalized ?? null,
            }
          : {}),
        ...(['embedding', 'reranker'].includes(data.type)
          ? { max_input_tokens: maxInputTokens ? Number(maxInputTokens) : null }
          : {}),
        ...(data.type === 'llm_chat' && contextWindow
          ? { context_window_tokens: Number(contextWindow) }
          : {}),
        ...(requestTimeout
          ? { request_timeout_s: parseInt(requestTimeout, 10) }
          : {}),
        ...(data.type === 'llm_chat' && maxRetries
          ? { max_retries: Number(maxRetries) }
          : {}),
      } as ModelCreate;
    },
    transformUpdate: data => {
      const resolvedConnector = resolveBackendConnector(
        data.type,
        String(data.instance_id || ''),
        data.connector
      );
      const extra_config: Record<string, unknown> = {
        ...(data.extra_config ?? {}),
      };
      delete extra_config.vector_dim;
      delete extra_config.dimensions;
      return {
        name: data.name,
        connector: resolvedConnector,
        provider_model_name: data.provider_model_name,
        base_url:
          String(data.instance_id || '') === LOCAL_CONNECTOR_SENTINEL
            ? data.base_url || null
            : null,
        instance_id:
          String(data.instance_id || '') === LOCAL_CONNECTOR_SENTINEL
            ? null
            : data.instance_id || null,
        status: data.status,
        enabled: data.enabled,
        default_for_type: data.default_for_type,
        use_for_long_memory:
          data.type === 'embedding' ? data.use_for_long_memory : false,
        model_version: data.model_version,
        description: data.description,
        ...(data.type === 'embedding'
          ? {
              embedding_dimensions: vectorDim ? Number(vectorDim) : null,
              vector_normalized: data.vector_normalized ?? null,
            }
          : {}),
        ...(['embedding', 'reranker'].includes(data.type)
          ? { max_input_tokens: maxInputTokens ? Number(maxInputTokens) : null }
          : {}),
        ...(data.type === 'llm_chat' && contextWindow
          ? { context_window_tokens: Number(contextWindow) }
          : {}),
        ...(requestTimeout
          ? { request_timeout_s: parseInt(requestTimeout, 10) }
          : {}),
        ...(data.type === 'llm_chat' && maxRetries
          ? { max_retries: Number(maxRetries) }
          : {}),
        extra_config,
      } as ModelUpdate;
    },
    messages: {
      create: 'Модель создана',
      update: 'Модель обновлена',
      delete: 'Модель удалена',
    },
  });

  const [showLongMemoryConfirm, setShowLongMemoryConfirm] = useState(false);
  const [longMemoryConfirmAction, setLongMemoryConfirmAction] = useState<
    'select' | 'save'
  >('select');
  const handleInfoChange = (key: string, value: unknown) => {
    if (key === 'use_for_long_memory' && value === true) {
      setLongMemoryConfirmAction('select');
      setShowLongMemoryConfirm(true);
      return;
    }
    if (
      key === 'use_for_long_memory' &&
      model?.use_for_long_memory &&
      value === false
    ) {
      showToast('Выберите другую embedding-модель для LongMemory', 'info');
      return;
    }
    if (key === 'type') setManifestRaw({});
    handleFieldChange(key, value);
  };
  const handleSaveWithLongMemoryConfirm = () => {
    const encoderChanged =
      model?.use_for_long_memory &&
      (formData.provider_model_name !== model.provider_model_name ||
        formData.model_version !== (model.model_version ?? '') ||
        formData.base_url !== (model.base_url ?? '') ||
        vectorDim !== String(model.embedding_dimensions ?? '') ||
        maxInputTokens !== String(model.max_input_tokens ?? ''));
    if (encoderChanged) {
      setLongMemoryConfirmAction('save');
      setShowLongMemoryConfirm(true);
      return;
    }
    void handleSave();
  };
  const longMemoryConfirmation = (
    <ConfirmDialog
      open={showLongMemoryConfirm}
      title="Сменить модель LongMemory?"
      message="После сохранения начнётся длительная переиндексация всей LongMemory. Поиск будет временно недоступен. Сохранённые чанки и факты будут использованы повторно, без LLM-извлечения."
      confirmLabel="Продолжить"
      cancelLabel="Отмена"
      variant="warning"
      onConfirm={() => {
        setShowLongMemoryConfirm(false);
        if (longMemoryConfirmAction === 'save') void handleSave();
        else handleFieldChange('use_for_long_memory', true);
      }}
      onCancel={() => setShowLongMemoryConfirm(false)}
    />
  );

  // ─── Коннекторы для select ───
  const { data: instances = [] } = useQuery({
    queryKey: qk.toolInstances.list({ connector_type: 'model' }),
    queryFn: () => toolInstancesApi.list({ connector_type: 'model' }),
    staleTime: 60_000,
  });
  const { data: embeddingUsage } = useQuery({
    queryKey: model?.id
      ? qk.admin.models.embeddingUsage(model.id)
      : ['admin', 'models', 'embedding-usage', 'none'],
    queryFn: () => adminApi.getEmbeddingUsage(model!.id),
    enabled: Boolean(model?.id) && model?.type === 'embedding',
    staleTime: 30_000,
  });
  const { data: embeddingModelsData } = useQuery({
    queryKey: qk.admin.models.list({
      type: 'embedding',
      enabled_only: true,
      size: 100,
    }),
    queryFn: () =>
      adminApi.getModels({ type: 'embedding', enabled_only: true, size: 100 }),
    enabled: Boolean(model?.id) && model?.type === 'embedding',
    staleTime: 30_000,
  });

  // ─── Derived ───
  const instanceOptions = [
    { value: LOCAL_CONNECTOR_SENTINEL, label: 'local' },
    ...instances.map(inst => ({
      value: inst.id,
      label: `${inst.name} (${inst.slug})`,
    })),
  ];

  const viewData = {
    alias: model?.alias ?? '',
    name: model?.name ?? '',
    type: model?.type ?? 'llm_chat',
    description: model?.description ?? '',
    connector: model?.connector ?? 'openai_http',
    provider_model_name: model?.provider_model_name ?? '',
    base_url: model?.base_url ?? '',
    instance_id:
      model?.instance_id ??
      (String(model?.connector || '').startsWith('local_')
        ? LOCAL_CONNECTOR_SENTINEL
        : ''),
    model_version: model?.model_version ?? '',
    vector_normalized: model?.vector_normalized ?? null,
    status: model?.status ?? 'available',
    enabled: model?.enabled ?? false,
    default_for_type: model?.default_for_type ?? false,
    use_for_long_memory: model?.use_for_long_memory ?? false,
    capabilities_checked_at: model?.capabilities_checked_at ?? '—',
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
    context_window_tokens: contextWindow,
    request_timeout_s: requestTimeout,
    max_retries: maxRetries,
    capabilities_source: model?.capabilities_checked_at
      ? 'Description сервиса'
      : 'Настройки реестра',
    embedding_dimensions: vectorDim,
    max_input_tokens: maxInputTokens,
    vector_normalized: blockData.vector_normalized,
  };
  const isEmbedding =
    (isEditable ? formData.type : model?.type) === 'embedding';
  const longMemoryFields: FieldConfig[] = isEmbedding
    ? [
        {
          key: 'use_for_long_memory',
          type: 'boolean',
          label: 'Использовать для LongMemory',
          description:
            'Отдельный энкодер памяти. Смена запускает фоновую переиндексацию.',
        },
      ]
    : [];
  const migrationModelOptions = (embeddingModelsData?.items || [])
    .filter(m => m.id !== model?.id)
    .map(m => ({ value: m.id, label: `${m.name} (${m.alias})` }));

  const healthData = {
    health_status: model?.health_status ?? 'unknown',
    health_latency_ms:
      model?.health_latency_ms != null ? String(model.health_latency_ms) : '—',
    health_error: model?.health_error ?? '—',
    last_health_check_at: model?.last_health_check_at ?? '',
  };

  useEffect(() => {
    setHealthBadge(String(model?.health_status || 'unknown'));
    const manifest =
      model?.extra_config && typeof model.extra_config === 'object'
        ? (model.extra_config as Record<string, unknown>).manifest
        : undefined;
    if (manifest && typeof manifest === 'object') {
      setManifestRaw(manifest as Record<string, unknown>);
    } else {
      setManifestRaw({});
    }
  }, [model?.id, model?.health_status, model?.extra_config]);

  const currentInstanceId = String(
    isEditable ? formData.instance_id : model?.instance_id || ''
  );
  const currentConnector = String(
    isEditable ? formData.connector : model?.connector || ''
  );
  const isLocalConnector =
    currentInstanceId === LOCAL_CONNECTOR_SENTINEL ||
    currentConnector.startsWith('local_');

  const connectorFieldsWithOptions = CONNECTOR_FIELDS.filter(f => {
    if (f.key === 'base_url' && !isLocalConnector) return false;
    return true;
  }).map(f => {
    if (f.key === 'instance_id') {
      return { ...f, options: instanceOptions };
    }
    if (f.key === 'connector' && isLocalConnector) {
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

  const currentModelType = String(
    isEditable ? formData.type : model?.type || viewData.type || ''
  );
  const paramsFields = modelCharacteristicFields(currentModelType, manifestRaw);
  const characteristicTitle =
    currentModelType === 'embedding'
      ? 'Характеристики Embedding'
      : currentModelType === 'reranker'
        ? 'Характеристики Reranker'
        : 'Характеристики LLM';
  const connectionFields = [
    ...connectorFieldsWithOptions.map(f => ({ ...f, description: undefined })),
    {
      key: 'provider_model_name',
      type: 'text' as const,
      label: 'Модель у провайдера',
      required: true,
    },
  ];
  const identityFields = [
    ...(isNew ? INFO_FIELDS_CREATE : INFO_FIELDS_VIEW)
      .filter(f => f.key !== 'default_for_type')
      .map(f => ({ ...f, description: undefined })),
    {
      key: 'type',
      type: 'select' as const,
      label: 'Тип модели',
      editable:
        isNew &&
        !/(embed|rerank|llm|chat)/i.test(String(manifestRaw.modality || '')),
      options: MODEL_TYPES.map(t => ({ value: t.value, label: t.label })),
    },
  ];
  const usageFields: FieldConfig[] = [
    {
      key: 'enabled',
      type: 'boolean',
      label: 'Включена',
      description:
        'Разрешает использование модели платформой. Сам сервис этот переключатель не останавливает.',
    },
    {
      key: 'default_for_type',
      type: 'boolean',
      label: 'По умолчанию для типа',
    },
    ...longMemoryFields,
  ];
  const handleParameterChange = (key: string, value: unknown) => {
    if (key === 'context_window_tokens') setContextWindow(String(value ?? ''));
    else if (key === 'request_timeout_s')
      setRequestTimeout(String(value ?? ''));
    else if (key === 'max_retries') setMaxRetries(String(value ?? ''));
    else if (key === 'embedding_dimensions') setVectorDim(String(value ?? ''));
    else if (key === 'max_input_tokens') setMaxInputTokens(String(value ?? ''));
    else handleFieldChange(key, value);
  };
  const handleConnectionChange = (key: string, value: unknown) => {
    setManifestRaw({});
    if (key === 'instance_id' && value !== LOCAL_CONNECTOR_SENTINEL)
      handleFieldChange('base_url', '');
    if (key === 'instance_id')
      handleFieldChange(
        'connector',
        value === LOCAL_CONNECTOR_SENTINEL
          ? resolveBackendConnector(
              currentModelType as ModelType,
              LOCAL_CONNECTOR_SENTINEL,
              'openai_http'
            )
          : 'openai_http'
      );
    handleFieldChange(key, value);
  };

  const handleProbeModelInfo = async () => {
    setProbingInfo(true);
    try {
      let info: {
        provider_model_name?: string;
        model_version?: string;
        model_type?: string;
        health_status?: string;
        raw?: Record<string, unknown>;
      };
      if (!isEditable && !isNew && model?.id) {
        const verified = await adminApi.verifyModel(model.id);
        await queryClient.invalidateQueries({
          queryKey: qk.admin.models.detail(model.id),
        });
        info = {
          provider_model_name: verified.provider_model_name,
          model_version: verified.model_version || '',
          model_type:
            (verified.resolved_type_from_manifest as string) || verified.type,
          health_status: verified.health_status || undefined,
          raw: (verified.manifest || {}) as Record<string, unknown>,
        };
      } else {
        const current = String(
          (isEditable ? formData.base_url : viewData.base_url) || ''
        ).trim();
        const currentConnector = ((isEditable
          ? formData.connector
          : viewData.connector) || 'openai_http') as ModelConnector;
        const currentInstanceId = String(
          (isEditable ? formData.instance_id : viewData.instance_id) || ''
        ).trim();
        const currentExtraConfig = (
          isEditable ? formData.extra_config : undefined
        ) as Record<string, unknown> | undefined;
        if (
          !current &&
          (!currentInstanceId || currentInstanceId === LOCAL_CONNECTOR_SENTINEL)
        ) {
          showToast('Укажите URL или выберите коннектор с URL', 'warning');
          return;
        }
        info = await adminApi.probeModelInfo({
          base_url: current || undefined,
          connector: resolveBackendConnector(
            currentModelType as ModelType,
            currentInstanceId,
            currentConnector
          ),
          provider_model_name:
            String(blockData.provider_model_name || '') || undefined,
          instance_id:
            currentInstanceId === LOCAL_CONNECTOR_SENTINEL
              ? undefined
              : currentInstanceId || undefined,
          extra_config: currentExtraConfig,
        });
      }

      if (info.provider_model_name)
        handleFieldChange('provider_model_name', info.provider_model_name);
      if (info.model_version)
        handleFieldChange('model_version', info.model_version);
      if (isNew && info.model_type) handleFieldChange('type', info.model_type);
      if (info.health_status) setHealthBadge(info.health_status);
      const raw = (info.raw || {}) as Record<string, unknown>;
      setManifestRaw(raw);
      if (isEditable)
        handleFieldChange('extra_config', {
          ...((blockData.extra_config as Record<string, unknown>) || {}),
          manifest: raw,
        });
      const vector = raw.dimensions;
      const maxTok = raw.context_window_tokens;
      if (typeof raw.max_tokens === 'number')
        setMaxInputTokens(String(raw.max_tokens));
      if (typeof raw.normalized === 'boolean')
        handleFieldChange('vector_normalized', raw.normalized);
      if (typeof vector === 'number' && Number.isFinite(vector) && vector > 0)
        setVectorDim(String(vector));
      if (typeof maxTok === 'number' && Number.isFinite(maxTok))
        setContextWindow(String(maxTok));
      showToast(
        Object.keys(raw).length
          ? 'Проверка выполнена. Отсутствующие характеристики можно заполнить вручную.'
          : 'Сервис не сообщил характеристики. Заполните их вручную.',
        Object.keys(raw).length ? 'success' : 'warning'
      );
    } catch (e) {
      showToast(
        e instanceof Error ? e.message : 'Не удалось выполнить проверку',
        'error'
      );
    } finally {
      setProbingInfo(false);
    }
  };

  const renderDocCounters = (
    total: number,
    vectorized: number,
    notVectorized: number
  ) => (
    <span className={styles.counterCell}>
      <span className={styles.counterTotal}>{total}</span>
      <span className={styles.counterSep}>/</span>
      <span className={styles.counterVectorized}>{vectorized}</span>
      <span className={styles.counterSep}>/</span>
      <span className={styles.counterNotVectorized}>{notVectorized}</span>
    </span>
  );

  // ─── Create mode ───
  if (isNew) {
    return (
      <>
        <EntityPageV2
          title="Новая модель"
          mode="create"
          saving={saving}
          headerActions={
            <Button
              variant="outline"
              onClick={handleProbeModelInfo}
              disabled={probingInfo}
            >
              {probingInfo ? 'Проверяем...' : 'Проверить'}
            </Button>
          }
          breadcrumbs={[
            { label: 'Настройки платформы', href: '/admin/platform' },
            { label: 'Новая модель' },
          ]}
          backPath="/admin/platform"
          onSave={handleSaveWithLongMemoryConfirm}
          onCancel={handleCancel}
        >
          <Tab title="Создание" layout="grid">
            <ModelConfigurationBlocks
              identityFields={identityFields}
              connectionFields={connectionFields}
              characteristicFields={paramsFields}
              usageFields={usageFields}
              characteristicTitle={characteristicTitle}
              modelType={currentModelType}
              data={blockData}
              characteristicData={paramsData}
              editable={isEditable}
              health={healthBadge}
              onInfoChange={handleInfoChange}
              onConnectionChange={handleConnectionChange}
              onParameterChange={handleParameterChange}
            />
          </Tab>
        </EntityPageV2>
        {longMemoryConfirmation}
      </>
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
        headerActions={
          <div className={styles.headerActions}>
            {model?.type === 'embedding' && (
              <Button
                variant="success"
                onClick={() => setShowMigrationModal(true)}
              >
                Миграции
              </Button>
            )}
            {
              <Button
                variant="success"
                onClick={handleProbeModelInfo}
                disabled={probingInfo}
              >
                {probingInfo ? 'Проверяем...' : 'Проверить'}
              </Button>
            }
          </div>
        }
        breadcrumbs={[
          { label: 'Настройки платформы', href: '/admin/platform' },
          { label: model?.name || 'Модель' },
        ]}
        onEdit={handleEdit}
        onSave={handleSaveWithLongMemoryConfirm}
        onCancel={handleCancel}
        onDelete={!model?.is_system ? handleDelete : undefined}
        showDelete={!model?.is_system}
      >
        <Tab
          title="Обзор"
          layout="grid"
          id="overview"
          actions={buildEntityCrudActions({
            mode,
            saving,
            tone: 'default',
            onEdit: handleEdit,
            onSave: handleSaveWithLongMemoryConfirm,
            onCancel: handleCancel,
            onDelete: !model?.is_system ? handleDelete : undefined,
            showDeleteInView: !model?.is_system,
          })}
        >
          <ModelConfigurationBlocks
            identityFields={identityFields}
            connectionFields={connectionFields}
            characteristicFields={paramsFields}
            usageFields={usageFields}
            characteristicTitle={characteristicTitle}
            modelType={currentModelType}
            data={blockData}
            characteristicData={paramsData}
            editable={isEditable}
            health={healthBadge}
            onInfoChange={handleInfoChange}
            onConnectionChange={handleConnectionChange}
            onParameterChange={handleParameterChange}
          />
        </Tab>

        <Tab title="Служебное" layout="grid" id="metadata">
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
        {model?.type === 'embedding' && (
          <Tab title="Индексация" layout="grid" id="embeddings">
            <Block title="Рабочие группы" icon="users" iconVariant="info" width="1/2">
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Рабочая группа</th>
                      <th>Статус</th>
                      <th>Коллекции (doc)</th>
                      <th>Документы (всего/вектор/не вектор)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(embeddingUsage?.tenants || []).map(row => (
                      <tr key={row.tenant_id}>
                        <td>
                          <a href={`/admin/tenants/${row.tenant_id}`}>
                            {row.tenant_name}
                          </a>
                        </td>
                        <td>{row.tenant_active ? 'active' : 'inactive'}</td>
                        <td>{row.collection_count}</td>
                        <td>
                          {renderDocCounters(
                            row.total_docs,
                            row.vectorized_docs,
                            row.not_vectorized_docs
                          )}
                        </td>
                      </tr>
                    ))}
                    {(!embeddingUsage?.tenants ||
                      embeddingUsage.tenants.length === 0) && (
                      <tr>
                        <td colSpan={4} className={styles.emptyCell}>
                          Нет данных
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Block>
            <Block
              title="Коллекции"
              icon="database"
              iconVariant="primary"
              width="full"
            >
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Коллекция</th>
                      <th>Рабочая группа</th>
                      <th>Документы (всего/вектор/не вектор)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(embeddingUsage?.collections || []).map(row => (
                      <tr key={row.collection_id}>
                        <td>
                          {row.collection_name}{' '}
                          <span className={styles.slug}>
                            ({row.collection_slug})
                          </span>
                        </td>
                        <td>{row.tenant_name}</td>
                        <td>
                          {renderDocCounters(
                            row.total_docs,
                            row.vectorized_docs,
                            row.not_vectorized_docs
                          )}
                        </td>
                      </tr>
                    ))}
                    {(!embeddingUsage?.collections ||
                      embeddingUsage.collections.length === 0) && (
                      <tr>
                        <td colSpan={3} className={styles.emptyCell}>
                          Нет данных
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Block>
          </Tab>
        )}
      </EntityPageV2>

      {longMemoryConfirmation}
      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить модель?"
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={handleDeleteConfirm}
        onCancel={() => setShowDeleteConfirm(false)}
      />
      <Modal
        open={showMigrationModal}
        title="Миграция эмбендингов"
        onClose={() => setShowMigrationModal(false)}
        footer={
          <div className={styles.modalFooter}>
            <Button
              variant="outline"
              onClick={() => setShowMigrationModal(false)}
            >
              Отмена
            </Button>
            <Button
              variant="primary"
              onClick={() =>
                showToast('Миграции будут подключены следующим шагом', 'info')
              }
              disabled={!migrationTargetModelId}
            >
              Запустить
            </Button>
          </div>
        }
      >
        <div className={styles.modalBody}>
          <div className={styles.modalHint}>
            Выберите целевую embedding-модель (без текущей).
          </div>
          <Select
            value={migrationTargetModelId}
            options={migrationModelOptions}
            onChange={v => setMigrationTargetModelId(String(v || ''))}
            placeholder="Выберите модель"
          />
        </div>
      </Modal>
    </>
  );
}

export default ModelPage;
