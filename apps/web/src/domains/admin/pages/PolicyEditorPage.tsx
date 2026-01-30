/**
 * PolicyEditorPage - View/Edit/Create execution policy with EntityPage
 * 
 * Unified page for all policy operations:
 * - View: /admin/policies/:id (readonly)
 * - Edit: /admin/policies/:id?mode=edit
 * - Create: /admin/policies/new
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { policiesApi, type PolicyCreate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';

interface FormData extends PolicyCreate {
  is_active?: boolean;
}

export function PolicyEditorPage() {
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

  const [formData, setFormData] = useState<FormData>({
    slug: '',
    name: '',
    description: '',
    max_steps: 20,
    max_tool_calls: 50,
    max_wall_time_ms: 300000,
    tool_timeout_ms: 30000,
    max_retries: 3,
    budget_tokens: undefined,
    budget_cost_cents: undefined,
    extra_config: {},
    is_active: true,
  });
  const [saving, setSaving] = useState(false);

  // Load existing policy
  const { data: existingPolicy, isLoading, refetch } = useQuery({
    queryKey: qk.policies.detail(id!),
    queryFn: () => policiesApi.get(id!),
    enabled: !isCreate,
  });

  useEffect(() => {
    if (existingPolicy) {
      setFormData({
        slug: existingPolicy.slug,
        name: existingPolicy.name,
        description: existingPolicy.description || '',
        max_steps: existingPolicy.max_steps ?? undefined,
        max_tool_calls: existingPolicy.max_tool_calls ?? undefined,
        max_wall_time_ms: existingPolicy.max_wall_time_ms ?? undefined,
        tool_timeout_ms: existingPolicy.tool_timeout_ms ?? undefined,
        max_retries: existingPolicy.max_retries ?? undefined,
        budget_tokens: existingPolicy.budget_tokens ?? undefined,
        budget_cost_cents: existingPolicy.budget_cost_cents ?? undefined,
        extra_config: existingPolicy.extra_config || {},
        is_active: existingPolicy.is_active,
      });
    }
  }, [existingPolicy]);

  const handleSave = async () => {
    setSaving(true);
    try {
      if (mode === 'create') {
        await policiesApi.create({
          slug: formData.slug,
          name: formData.name,
          description: formData.description || undefined,
          max_steps: formData.max_steps,
          max_tool_calls: formData.max_tool_calls,
          max_wall_time_ms: formData.max_wall_time_ms,
          tool_timeout_ms: formData.tool_timeout_ms,
          max_retries: formData.max_retries,
          budget_tokens: formData.budget_tokens,
          budget_cost_cents: formData.budget_cost_cents,
          extra_config: formData.extra_config,
        });
        showSuccess('Политика создана');
        queryClient.invalidateQueries({ queryKey: qk.policies.all() });
        navigate('/admin/policies');
      } else {
        await policiesApi.update(id!, {
          name: formData.name,
          description: formData.description || undefined,
          max_steps: formData.max_steps,
          max_tool_calls: formData.max_tool_calls,
          max_wall_time_ms: formData.max_wall_time_ms,
          tool_timeout_ms: formData.tool_timeout_ms,
          max_retries: formData.max_retries,
          budget_tokens: formData.budget_tokens,
          budget_cost_cents: formData.budget_cost_cents,
          extra_config: formData.extra_config,
          is_active: formData.is_active,
        });
        showSuccess('Политика обновлена');
        queryClient.invalidateQueries({ queryKey: qk.policies.all() });
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
    if (mode === 'edit' && existingPolicy) {
      setFormData({
        slug: existingPolicy.slug,
        name: existingPolicy.name,
        description: existingPolicy.description || '',
        max_steps: existingPolicy.max_steps ?? undefined,
        max_tool_calls: existingPolicy.max_tool_calls ?? undefined,
        max_wall_time_ms: existingPolicy.max_wall_time_ms ?? undefined,
        tool_timeout_ms: existingPolicy.tool_timeout_ms ?? undefined,
        max_retries: existingPolicy.max_retries ?? undefined,
        budget_tokens: existingPolicy.budget_tokens ?? undefined,
        budget_cost_cents: existingPolicy.budget_cost_cents ?? undefined,
        extra_config: existingPolicy.extra_config || {},
        is_active: existingPolicy.is_active,
      });
      setSearchParams({});
    } else if (mode === 'create') {
      navigate('/admin/policies');
    }
  };

  const handleDelete = async () => {
    if (!confirm('Удалить эту политику?')) return;
    try {
      await policiesApi.delete(id!);
      showSuccess('Политика удалена');
      queryClient.invalidateQueries({ queryKey: qk.policies.all() });
      navigate('/admin/policies');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка удаления');
    }
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  // Field definitions
  const basicFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug',
      type: 'text',
      required: true,
      disabled: mode !== 'create',
      placeholder: 'my-policy',
      description: 'Уникальный идентификатор',
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'Моя политика',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Описание политики...',
    },
    {
      key: 'is_active',
      label: 'Активна',
      type: 'boolean',
      description: 'Политика доступна для использования',
    },
  ];

  const limitsFields: FieldDefinition[] = [
    {
      key: 'max_steps',
      label: 'Макс. шагов',
      type: 'number',
      placeholder: '20',
      description: 'Максимальное количество шагов агента',
    },
    {
      key: 'max_tool_calls',
      label: 'Макс. вызовов',
      type: 'number',
      placeholder: '50',
      description: 'Максимальное количество вызовов инструментов',
    },
    {
      key: 'max_retries',
      label: 'Макс. повторов',
      type: 'number',
      placeholder: '3',
      description: 'Количество повторных попыток при ошибке',
    },
  ];

  const timeoutFields: FieldDefinition[] = [
    {
      key: 'max_wall_time_ms',
      label: 'Общий таймаут (мс)',
      type: 'number',
      placeholder: '300000',
      description: 'Максимальное время выполнения в миллисекундах',
    },
    {
      key: 'tool_timeout_ms',
      label: 'Таймаут инструмента (мс)',
      type: 'number',
      placeholder: '30000',
      description: 'Таймаут для одного вызова инструмента',
    },
  ];

  const budgetFields: FieldDefinition[] = [
    {
      key: 'budget_tokens',
      label: 'Лимит токенов',
      type: 'number',
      placeholder: 'Без лимита',
      description: 'Максимальное количество токенов',
    },
    {
      key: 'budget_cost_cents',
      label: 'Лимит стоимости (центы)',
      type: 'number',
      placeholder: 'Без лимита',
      description: 'Максимальная стоимость в центах',
    },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={existingPolicy ? existingPolicy.name : 'Новая политика'}
      entityTypeLabel="политики"
      backPath="/admin/policies"
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={handleDelete}
      showDelete={mode === 'view' && !!id && existingPolicy?.slug !== 'default'}
    >
      <ContentGrid>
        <ContentBlock
          width="1/2"
          title="Основное"
          icon="file"
          editable={isEditable}
          fields={basicFields}
          data={formData}
          onChange={handleFieldChange}
        />

        <ContentBlock
          width="1/2"
          title="Лимиты выполнения"
          icon="shield"
          editable={isEditable}
          fields={limitsFields}
          data={formData}
          onChange={handleFieldChange}
        />

        <ContentBlock
          width="1/2"
          title="Таймауты"
          icon="clock"
          editable={isEditable}
          fields={timeoutFields}
          data={formData}
          onChange={handleFieldChange}
        />

        <ContentBlock
          width="1/2"
          title="Бюджет"
          icon="dollar"
          editable={isEditable}
          fields={budgetFields}
          data={formData}
          onChange={handleFieldChange}
        />
      </ContentGrid>
    </EntityPage>
  );
}

export default PolicyEditorPage;
