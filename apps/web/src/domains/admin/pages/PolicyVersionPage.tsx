/**
 * PolicyVersionPage - View/Edit/Create policy version
 * 
 * Routes:
 * - /admin/policies/:slug/versions/new - Create new version
 * - /admin/policies/:slug/versions/:version - View version
 * - /admin/policies/:slug/versions/:version?mode=edit - Edit version (only draft)
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { policiesApi, type PolicyVersionCreate, type PolicyVersion, type PolicyVersionStatus } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';
import { Badge, Button } from '@/shared/ui';
import { Breadcrumbs } from '@/shared/ui/Breadcrumbs';

interface FormData extends PolicyVersionCreate {
  notes?: string;
}

const STATUS_LABELS: Record<PolicyVersionStatus, string> = {
  draft: 'Черновик',
  active: 'Активная',
  inactive: 'Неактивная',
};

const STATUS_VARIANTS: Record<PolicyVersionStatus, 'default' | 'success' | 'warning' | 'error'> = {
  draft: 'warning',
  active: 'success',
  inactive: 'default',
};

export function PolicyVersionPage() {
  const { slug, version: versionParam } = useParams<{ slug: string; version: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isCreate = versionParam === 'new';
  const versionNumber = isCreate ? 0 : parseInt(versionParam || '0', 10);
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const [formData, setFormData] = useState<FormData>({
    max_steps: 20,
    max_tool_calls: 50,
    max_wall_time_ms: 300000,
    tool_timeout_ms: 30000,
    max_retries: 3,
    budget_tokens: undefined,
    budget_cost_cents: undefined,
    extra_config: {},
    notes: '',
  });
  const [saving, setSaving] = useState(false);

  // Load policy for breadcrumbs
  const { data: policy } = useQuery({
    queryKey: qk.policies.detail(slug!),
    queryFn: () => policiesApi.get(slug!),
    enabled: !!slug,
  });

  // Load existing version
  const { data: existingVersion, isLoading } = useQuery({
    queryKey: qk.policies.version(slug!, versionNumber),
    queryFn: () => policiesApi.getVersion(slug!, versionNumber),
    enabled: !isCreate && !!slug && versionNumber > 0,
  });

  useEffect(() => {
    if (existingVersion) {
      setFormData({
        max_steps: existingVersion.max_steps ?? undefined,
        max_tool_calls: existingVersion.max_tool_calls ?? undefined,
        max_wall_time_ms: existingVersion.max_wall_time_ms ?? undefined,
        tool_timeout_ms: existingVersion.tool_timeout_ms ?? undefined,
        max_retries: existingVersion.max_retries ?? undefined,
        budget_tokens: existingVersion.budget_tokens ?? undefined,
        budget_cost_cents: existingVersion.budget_cost_cents ?? undefined,
        extra_config: existingVersion.extra_config || {},
        notes: existingVersion.notes || '',
      });
    }
  }, [existingVersion]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: PolicyVersionCreate) => policiesApi.createVersion(slug!, data),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      showSuccess('Версия создана');
      navigate(`/admin/policies/${slug}/versions/${created.version}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: (data: PolicyVersionCreate) => policiesApi.updateVersion(slug!, versionNumber, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.policies.version(slug!, versionNumber) });
      showSuccess('Версия обновлена');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const activateMutation = useMutation({
    mutationFn: () => policiesApi.activateVersion(slug!, versionNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.policies.version(slug!, versionNumber) });
      showSuccess('Версия активирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deactivateMutation = useMutation({
    mutationFn: () => policiesApi.deactivateVersion(slug!, versionNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.policies.version(slug!, versionNumber) });
      showSuccess('Версия деактивирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => policiesApi.deleteVersion(slug!, versionNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      showSuccess('Версия удалена');
      navigate(`/admin/policies/${slug}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const handleSave = async () => {
    setSaving(true);
    try {
      const data: PolicyVersionCreate = {
        max_steps: formData.max_steps,
        max_tool_calls: formData.max_tool_calls,
        max_wall_time_ms: formData.max_wall_time_ms,
        tool_timeout_ms: formData.tool_timeout_ms,
        max_retries: formData.max_retries,
        budget_tokens: formData.budget_tokens,
        budget_cost_cents: formData.budget_cost_cents,
        extra_config: formData.extra_config,
        notes: formData.notes || undefined,
      };

      if (mode === 'create') {
        // Copy from recommended version if exists
        if (policy?.recommended_version) {
          data.parent_version_id = policy.recommended_version.id;
        }
        await createMutation.mutateAsync(data);
      } else {
        await updateMutation.mutateAsync(data);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => {
    if (existingVersion?.status !== 'draft') {
      showError('Только черновики можно редактировать');
      return;
    }
    setSearchParams({ mode: 'edit' });
  };

  const handleCancel = () => {
    if (mode === 'edit' && existingVersion) {
      setFormData({
        max_steps: existingVersion.max_steps ?? undefined,
        max_tool_calls: existingVersion.max_tool_calls ?? undefined,
        max_wall_time_ms: existingVersion.max_wall_time_ms ?? undefined,
        tool_timeout_ms: existingVersion.tool_timeout_ms ?? undefined,
        max_retries: existingVersion.max_retries ?? undefined,
        budget_tokens: existingVersion.budget_tokens ?? undefined,
        budget_cost_cents: existingVersion.budget_cost_cents ?? undefined,
        extra_config: existingVersion.extra_config || {},
        notes: existingVersion.notes || '',
      });
      setSearchParams({});
    } else if (mode === 'create') {
      navigate(`/admin/policies/${slug}`);
    }
  };

  const handleDelete = async () => {
    if (existingVersion?.status === 'active') {
      showError('Нельзя удалить активную версию');
      return;
    }
    if (!confirm('Удалить эту версию?')) return;
    await deleteMutation.mutateAsync();
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  // Field definitions
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

  const notesFields: FieldDefinition[] = [
    {
      key: 'notes',
      label: 'Заметки',
      type: 'textarea',
      placeholder: 'Что изменилось в этой версии...',
      description: 'Описание изменений',
    },
  ];

  // Breadcrumbs
  const breadcrumbs = [
    { label: 'Политики', href: '/admin/policies' },
    { label: policy?.name || slug || '', href: `/admin/policies/${slug}` },
    { label: isCreate ? 'Новая версия' : `Версия ${versionNumber}` },
  ];

  // Custom actions based on version status
  const renderStatusActions = () => {
    if (isCreate || !existingVersion) return null;

    return (
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <Badge variant={STATUS_VARIANTS[existingVersion.status]}>
          {STATUS_LABELS[existingVersion.status]}
        </Badge>
        
        {existingVersion.status === 'draft' && (
          <Button size="small" variant="primary" onClick={() => activateMutation.mutate()}>
            Активировать
          </Button>
        )}
        {existingVersion.status === 'active' && (
          <Button size="small" variant="secondary" onClick={() => deactivateMutation.mutate()}>
            Деактивировать
          </Button>
        )}
      </div>
    );
  };

  return (
    <EntityPage
      mode={mode}
      entityName={isCreate ? 'Новая версия' : `Версия ${versionNumber}`}
      entityTypeLabel="версии"
      backPath={`/admin/policies/${slug}`}
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={existingVersion?.status === 'draft' ? handleEdit : undefined}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={existingVersion?.status !== 'active' ? handleDelete : undefined}
      showDelete={mode === 'view' && existingVersion?.status !== 'active'}
    >
      <Breadcrumbs items={breadcrumbs} />
      
      {renderStatusActions()}

      <ContentGrid>
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

        <ContentBlock
          width="1/2"
          title="Заметки"
          icon="file"
          editable={isEditable}
          fields={notesFields}
          data={formData}
          onChange={handleFieldChange}
        />
      </ContentGrid>
    </EntityPage>
  );
}

export default PolicyVersionPage;
