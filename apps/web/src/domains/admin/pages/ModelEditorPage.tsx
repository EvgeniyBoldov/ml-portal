/**
 * ModelEditorPage - View/Edit/Create model with EntityPage
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
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';

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

export function ModelEditorPage() {
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
  
  // Form state
  const [formData, setFormData] = useState<Partial<ModelCreate>>({
    alias: '',
    name: '',
    type: 'llm_chat',
    provider: 'openai',
    provider_model_name: '',
    base_url: '',
    api_key_ref: '',
    status: 'available',
    enabled: true,
    default_for_type: false,
    model_version: '',
    description: '',
    extra_config: {},
  });
  const [vectorDim, setVectorDim] = useState<string>('');
  const [saving, setSaving] = useState(false);
  
  // Load existing model
  const { data: model, isLoading, refetch } = useQuery({
    queryKey: qk.admin.models.detail(id || ''),
    queryFn: () => adminApi.getModel(id!),
    enabled: !isCreate && !!id,
  });
  
  // Populate form when model loads
  useEffect(() => {
    if (model) {
      setFormData({
        alias: model.alias,
        name: model.name,
        type: model.type,
        provider: model.provider,
        provider_model_name: model.provider_model_name,
        base_url: model.base_url,
        api_key_ref: model.api_key_ref || '',
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
  
  // Create mutation
  const createMutation = useMutation({
    mutationFn: (data: ModelCreate) => adminApi.createModel(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.models.all() });
    },
  });
  
  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: ModelUpdate) => adminApi.updateModel(id!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.models.all() });
      queryClient.invalidateQueries({ queryKey: qk.admin.models.detail(id!) });
    },
  });
  
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
          base_url: formData.base_url,
          api_key_ref: formData.api_key_ref,
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
  
  const handleEdit = () => {
    setSearchParams({ mode: 'edit' });
  };
  
  const handleCancel = () => {
    if (mode === 'edit' && model) {
      setFormData({
        alias: model.alias,
        name: model.name,
        type: model.type,
        provider: model.provider,
        provider_model_name: model.provider_model_name,
        base_url: model.base_url,
        api_key_ref: model.api_key_ref || '',
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
  
  const handleDelete = async () => {
    if (!confirm('Удалить эту модель?')) return;
    try {
      await adminApi.deleteModel(id!);
      showSuccess('Модель удалена');
      queryClient.invalidateQueries({ queryKey: qk.admin.models.all() });
      navigate('/admin/models');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка удаления');
    }
  };
  
  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev: Partial<ModelCreate>) => ({ ...prev, [key]: value }));
  };

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
      key: 'base_url',
      label: 'Base URL',
      type: 'text',
      required: true,
      placeholder: 'https://api.openai.com/v1',
    },
    {
      key: 'api_key_ref',
      label: 'API Key Reference',
      type: 'text',
      placeholder: 'OPENAI_API_KEY',
      description: 'Имя переменной окружения (не сам ключ)',
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

  const embeddingFields: FieldDefinition[] = [
    {
      key: 'vector_dim',
      label: 'Размерность вектора',
      type: 'number',
      required: true,
      placeholder: '1536',
      render: (value, editable, onChange) => {
        if (!editable) return vectorDim || '—';
        return null; // Use default rendering
      },
    },
  ];
  
  return (
    <EntityPage
      mode={mode}
      entityName={model?.alias || 'Новая модель'}
      entityTypeLabel="модели"
      backPath="/admin/models"
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={handleDelete}
      showDelete={mode === 'view' && !!id && !model?.is_system}
    >
      <ContentGrid>
        {/* Basic Info - 1/2 (есть текстовые поля) */}
        <ContentBlock
          width="1/2"
          title="Основная информация"
          icon="info"
          editable={isEditable}
          fields={basicInfoFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Provider - 1/2 (есть текстовые поля) */}
        <ContentBlock
          width="1/2"
          title="Провайдер"
          icon="server"
          editable={isEditable}
          fields={providerFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Status - 1/3 (только переключатели и выпадашки) */}
        <ContentBlock
          width="1/3"
          title="Статус и флаги"
          icon="settings"
          editable={isEditable}
          fields={statusFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Embedding config - 1/3 (только для embedding) */}
        {formData.type === 'embedding' && (
          <ContentBlock
            width="1/3"
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
            data={{ vector_dim: vectorDim }}
            onChange={(key, value) => setVectorDim(value)}
          />
        )}
      </ContentGrid>
    </EntityPage>
  );
}

export default ModelEditorPage;
