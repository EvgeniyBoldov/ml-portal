/**
 * ModelPage - View/Edit/Create model with EntityPageV2
 * 
 * Unified page for all model operations:
 * - View: /admin/models/:id (readonly)
 * - Edit: /admin/models/:id?mode=edit
 * - Create: /admin/models/new
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminApi, type ModelCreate, type ModelUpdate, type ModelType, type ModelStatus } from '@/shared/api/admin';
import { toolInstancesApi } from '@/shared/api/toolInstances';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui/EntityPage/EntityPageV2';
import { ContentBlock, type FieldDefinition } from '@/shared/ui/ContentBlock';
import { Badge, ConfirmDialog } from '@/shared/ui';

type ApiErrorShape = {
  message?: string;
};

const MODEL_TYPES: { value: ModelType; label: string }[] = [
  { value: 'llm_chat', label: 'LLM Chat' },
  { value: 'embedding', label: 'Embedding' },
];

const MODEL_STATUSES: { value: ModelStatus; label: string }[] = [
  { value: 'available', label: 'Доступна' },
  { value: 'unavailable', label: 'Недоступна' },
  { value: 'deprecated', label: 'Устарела' },
  { value: 'maintenance', label: 'Обслуживание' },
];

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'groq', label: 'Groq' },
  { value: 'local', label: 'Local Container' },
  { value: 'azure', label: 'Azure OpenAI' },
];

export function ModelPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
  // Determine mode
  const isCreate = !id;
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  
  // Form state
  const [formData, setFormData] = useState<Partial<ModelCreate>>({
    alias: '',
    name: '',
    type: 'llm_chat',
    provider: 'openai',
    provider_model_name: '',
    instance_id: '',
    status: 'available',
    enabled: true,
    default_for_type: false,
    model_version: '',
    description: '',
    extra_config: {},
  });
  const [vectorDim, setVectorDim] = useState<string>('');
  
  // Load existing model
  const { data: model, isLoading, refetch } = useQuery({
    queryKey: qk.admin.models.detail(id || ''),
    queryFn: () => adminApi.getModel(id!),
    enabled: !isCreate && !!id,
  });

  // Load instances for select dropdown
  const { data: instances = [] } = useQuery({
    queryKey: qk.toolInstances.all(),
    queryFn: () => toolInstancesApi.list(),
  });

  // Build instance options for select
  const instanceOptions = [
    { value: '', label: '— Не выбран —' },
    ...instances.map((inst) => ({
      value: inst.id,
      label: `${inst.name} (${inst.slug})`,
    })),
  ];
  
  // Populate form when model loads
  useEffect(() => {
    if (model) {
      setFormData({
        alias: model.alias,
        name: model.name,
        type: model.type,
        provider: model.provider,
        provider_model_name: model.provider_model_name,
        instance_id: model.instance_id || '',
        status: model.status,
        enabled: model.enabled,
        default_for_type: model.default_for_type,
        model_version: model.model_version || '',
        description: model.description || '',
        extra_config: model.extra_config || {},
      });
      if (model.extra_config?.vector_dim) {
        setVectorDim(String(model.extra_config.vector_dim));
      }
    }
  }, [model]);
  
  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: ModelCreate) => adminApi.createModel(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.models.all() });
    },
  });
  
  const updateMutation = useMutation({
    mutationFn: (data: ModelUpdate) => adminApi.updateModel(id!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.models.all() });
      queryClient.invalidateQueries({ queryKey: qk.admin.models.detail(id!) });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => adminApi.deleteModel(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.models.all() });
      showSuccess('Модель удалена');
      navigate('/admin/models');
    },
    onError: (err: unknown) => showError((err as ApiErrorShape)?.message || 'Ошибка удаления'),
  });
  
  // Handlers
  const handleSave = async () => {
    setSaving(true);
    try {
      const extra_config: Record<string, unknown> = { ...formData.extra_config };
      if (formData.type === 'embedding' && vectorDim) {
        extra_config.vector_dim = parseInt(vectorDim, 10);
      }
      
      if (mode === 'create') {
        const data = {
          ...formData,
          extra_config: Object.keys(extra_config).length > 0 ? extra_config : undefined,
        } as ModelCreate;
        await createMutation.mutateAsync(data);
        showSuccess('Модель создана');
        navigate('/admin/models');
      } else {
        const updateData: ModelUpdate = {
          name: formData.name,
          provider: formData.provider,
          provider_model_name: formData.provider_model_name,
          instance_id: formData.instance_id || undefined,
          status: formData.status,
          enabled: formData.enabled,
          default_for_type: formData.default_for_type,
          model_version: formData.model_version,
          description: formData.description,
        };
        if (formData.type === 'embedding') {
          updateData.extra_config = extra_config;
        }
        await updateMutation.mutateAsync(updateData);
        showSuccess('Модель обновлена');
        setSearchParams({});
        refetch();
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };
  
  const handleEdit = () => setSearchParams({ mode: 'edit' });
  
  const handleCancel = () => {
    if (mode === 'edit' && model) {
      setFormData({
        alias: model.alias,
        name: model.name,
        type: model.type,
        provider: model.provider,
        provider_model_name: model.provider_model_name,
        instance_id: model.instance_id || '',
        status: model.status,
        enabled: model.enabled,
        default_for_type: model.default_for_type,
        model_version: model.model_version || '',
        description: model.description || '',
        extra_config: model.extra_config || {},
      });
      setSearchParams({});
    } else if (mode === 'create') {
      navigate('/admin/models');
    }
  };
  
  const handleDelete = () => setShowDeleteConfirm(true);

  const handleDeleteConfirm = async () => {
    setSaving(true);
    await deleteMutation.mutateAsync();
    setSaving(false);
    setShowDeleteConfirm(false);
  };
  
  const handleFieldChange = (key: string, value: unknown) => {
    setFormData((prev: Partial<ModelCreate>) => ({ ...prev, [key]: value }));
  };

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Модели', href: '/admin/models' },
    { label: model?.name || 'Новая модель' },
  ];

  // Field definitions
  const basicInfoFields: FieldDefinition[] = [
    {
      key: 'alias',
      label: 'Алиас',
      type: 'text',
      required: true,
      placeholder: 'llm.chat.default',
      disabled: mode !== 'create',
      description: mode === 'create' ? 'Уникальный идентификатор. Нельзя изменить после создания.' : undefined,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'GPT-4 Turbo',
    },
    {
      key: 'type',
      label: 'Тип',
      type: 'select',
      required: true,
      disabled: mode !== 'create',
      options: MODEL_TYPES.map(t => ({ value: t.value, label: t.label })),
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Описание модели...',
      rows: 3,
    },
  ];

  const providerFields: FieldDefinition[] = [
    {
      key: 'provider',
      label: 'Провайдер',
      type: 'select',
      required: true,
      options: PROVIDERS.map(p => ({ value: p.value, label: p.label })),
    },
    {
      key: 'provider_model_name',
      label: 'Имя модели у провайдера',
      type: 'text',
      required: true,
      placeholder: 'gpt-4-turbo-preview',
    },
    {
      key: 'instance_id',
      label: 'Инстанс (провайдер)',
      type: 'select',
      options: instanceOptions,
      description: 'Подключение к провайдеру (URL + креды)',
    },
  ];

  const statusFields: FieldDefinition[] = [
    {
      key: 'status',
      label: 'Статус',
      type: 'select',
      options: MODEL_STATUSES.map(s => ({ value: s.value, label: s.label })),
    },
    {
      key: 'enabled',
      label: 'Включена',
      type: 'boolean',
      description: 'Модель доступна для использования',
    },
    {
      key: 'default_for_type',
      label: 'По умолчанию для типа',
      type: 'boolean',
      description: 'Используется по умолчанию для данного типа моделей',
    },
  ];

  // Create mode — single tab
  if (isCreate) {
    return (
      <EntityPageV2
        title="Новая модель"
        mode={mode}
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/models"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="grid">
          <ContentBlock
            width="full"
            title="Основная информация"
            icon="info"
            editable={true}
            fields={basicInfoFields}
            data={formData}
            onChange={handleFieldChange}
          />
          <ContentBlock
            width="full"
            title="Провайдер"
            icon="server"
            editable={true}
            fields={providerFields}
            data={formData}
            onChange={handleFieldChange}
          />
          <ContentBlock
            width="full"
            title="Статус и флаги"
            icon="settings"
            editable={true}
            fields={statusFields}
            data={formData}
            onChange={handleFieldChange}
          />
          {formData.type === 'embedding' && (
            <ContentBlock
              width="full"
              title="Настройки эмбеддинга"
              icon="cpu"
              editable={true}
              fields={[{
                key: 'vector_dim',
                label: 'Размерность вектора',
                type: 'number',
                required: true,
                placeholder: '1536',
              }]}
              data={{ vector_dim: vectorDim }}
              onChange={(_key: string, value: unknown) => setVectorDim(String(value ?? ''))}
            />
          )}
        </Tab>
      </EntityPageV2>
    );
  }

  // View/Edit mode — tabs
  return (
    <>
      <EntityPageV2
        title={model?.name || 'Модель'}
        mode={mode}
        loading={isLoading}
        saving={saving}
        breadcrumbs={breadcrumbs}
        onEdit={handleEdit}
        onSave={handleSave}
        onCancel={handleCancel}
        showDelete={!model?.is_system}
        onDelete={handleDelete}
      >
        <Tab title="Обзор" layout="grid" id="overview">
          <ContentBlock
            width="1/2"
            title="Основная информация"
            icon="info"
            editable={isEditable}
            fields={basicInfoFields}
            data={isEditable ? formData : (model || formData)}
            onChange={handleFieldChange}
            headerActions={
              model?.health_status ? (
                <Badge tone={model.health_status === 'healthy' ? 'success' : model.health_status === 'degraded' ? 'warn' : 'danger'}>
                  {model.health_status}
                </Badge>
              ) : undefined
            }
          />
          <ContentBlock
            width="1/2"
            title="Провайдер и инстанс"
            icon="server"
            editable={isEditable}
            fields={providerFields}
            data={isEditable ? formData : {
              ...model,
              instance_id: model?.instance_id || '',
            }}
            onChange={handleFieldChange}
          />
          <ContentBlock
            width="1/2"
            title="Статус и флаги"
            icon="settings"
            editable={isEditable}
            fields={statusFields}
            data={isEditable ? formData : (model || formData)}
            onChange={handleFieldChange}
          />
          {(formData.type === 'embedding' || model?.type === 'embedding') && (
            <ContentBlock
              width="1/2"
              title="Настройки эмбеддинга"
              icon="cpu"
              editable={isEditable}
              fields={[{
                key: 'vector_dim',
                label: 'Размерность вектора',
                type: 'number',
                required: true,
                placeholder: '1536',
              }]}
              data={{ vector_dim: isEditable ? vectorDim : (model?.extra_config?.vector_dim || '—') }}
              onChange={(_key: string, value: unknown) => setVectorDim(String(value ?? ''))}
            />
          )}
        </Tab>

        <Tab title="Health" layout="full" id="health">
          <ContentBlock
            width="full"
            title="Состояние модели"
            icon="activity"
            fields={[
              { key: 'health_status', label: 'Статус', type: 'text' },
              { key: 'health_latency_ms', label: 'Задержка (мс)', type: 'text' },
              { key: 'health_error', label: 'Ошибка', type: 'text' },
              { key: 'last_health_check_at', label: 'Последняя проверка', type: 'text' },
            ]}
            data={{
              health_status: model?.health_status || '—',
              health_latency_ms: model?.health_latency_ms != null ? String(model.health_latency_ms) : '—',
              health_error: model?.health_error || '—',
              last_health_check_at: model?.last_health_check_at
                ? new Date(model.last_health_check_at).toLocaleString('ru-RU')
                : '—',
            }}
          />
        </Tab>
      </EntityPageV2>

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить модель?"
        message={`Вы уверены, что хотите удалить модель "${model?.name}"? Это действие нельзя отменить.`}
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
