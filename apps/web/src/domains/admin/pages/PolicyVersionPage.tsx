/**
 * PolicyVersionPage - View/Edit/Create policy version
 * 
 * REFACTORED: Simplified with shared components
 * Routes:
 * - /admin/policies/:slug/versions/new - Create new version
 * - /admin/policies/:slug/versions/:version - View version
 * - /admin/policies/:slug/versions/:version?mode=edit - Edit version (only draft)
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { policiesApi, type PolicyVersionCreate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, ContentBlock, Input, Textarea, Badge, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui';
import { useVersionActions } from '@/shared/hooks/useVersionActions';

interface FormData extends PolicyVersionCreate {
  notes?: string;
}

export function PolicyVersionPage() {
  const { slug, version: versionParam } = useParams<{ slug: string; version: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isCreate = !versionParam;
  const versionNumber = isCreate ? 0 : parseInt(versionParam, 10);
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const [formData, setFormData] = useState<FormData>({
    max_steps: isCreate ? undefined : 20,
    max_tool_calls: isCreate ? undefined : 50,
    max_wall_time_ms: isCreate ? undefined : 300000,
    tool_timeout_ms: isCreate ? undefined : 30000,
    max_retries: isCreate ? undefined : 3,
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
    if (isCreate) {
      // Reset form for create mode
      setFormData({
        max_steps: undefined,
        max_tool_calls: undefined,
        max_wall_time_ms: undefined,
        tool_timeout_ms: undefined,
        max_retries: undefined,
        budget_tokens: undefined,
        budget_cost_cents: undefined,
        extra_config: {},
        notes: '',
      });
    } else if (existingVersion) {
      // Load existing version data
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
  }, [existingVersion, isCreate]);

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

  const setRecommendedMutation = useMutation({
    mutationFn: () => policiesApi.setRecommendedVersion(slug!, existingVersion!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      showSuccess('Основная версия установлена');
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

  const handleEdit = () => setSearchParams({ mode: 'edit' });
  
  const handleCancel = () => {
    if (isCreate) {
      navigate(`/admin/policies/${slug}`);
    } else {
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
      setSearchParams({});
    }
  };

  
  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Политики', href: '/admin/policies' },
    { label: policy?.name || slug || '', href: `/admin/policies/${slug}` },
    { label: isCreate ? 'Новая версия' : `Версия ${versionNumber}` },
  ];

  const isRecommended = !!(policy?.recommended_version?.id && existingVersion?.id && policy.recommended_version.id === existingVersion.id);

  const actionButtons = useVersionActions({
    status: existingVersion?.status,
    isRecommended,
    isCreate,
    callbacks: {
      onEdit: () => setSearchParams({ mode: 'edit' }),
      onActivate: () => activateMutation.mutate(),
      onDeactivate: () => deactivateMutation.mutate(),
      onSetRecommended: () => setRecommendedMutation.mutate(),
    },
    loading: {
      activate: activateMutation.isPending,
      deactivate: deactivateMutation.isPending,
      setRecommended: setRecommendedMutation.isPending,
    },
  });

  return (
    <EntityPage
      mode={mode}
      entityName={isCreate ? 'Новая версия' : `Версия ${versionNumber}`}
      entityTypeLabel="версии"
      backPath={`/admin/policies/${slug}`}
      breadcrumbs={breadcrumbs}
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      actionButtons={actionButtons}
    >
      <ContentBlock
        title="Лимиты"
        icon="settings"
        headerActions={
          !isCreate && existingVersion?.status ? (
            <Badge tone={existingVersion.status === 'active' ? 'success' : existingVersion.status === 'draft' ? 'warn' : 'neutral'} size="small">
              {existingVersion.status === 'active' ? 'Активна' : existingVersion.status === 'draft' ? 'Черновик' : 'Архив'}
            </Badge>
          ) : undefined
        }
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>Макс. шагов</label>
            <Input
              type="number"
              value={formData.max_steps ?? ''}
              onChange={(e) => handleFieldChange('max_steps', e.target.value ? parseInt(e.target.value) : undefined)}
              disabled={!isEditable}
              placeholder="Без лимита"
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>Макс. вызовов</label>
            <Input
              type="number"
              value={formData.max_tool_calls ?? ''}
              onChange={(e) => handleFieldChange('max_tool_calls', e.target.value ? parseInt(e.target.value) : undefined)}
              disabled={!isEditable}
              placeholder="Без лимита"
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>Макс. повторов</label>
            <Input
              type="number"
              value={formData.max_retries ?? ''}
              onChange={(e) => handleFieldChange('max_retries', e.target.value ? parseInt(e.target.value) : undefined)}
              disabled={!isEditable}
              placeholder="Без лимита"
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>Таймаут (мс)</label>
            <Input
              type="number"
              value={formData.max_wall_time_ms ?? ''}
              onChange={(e) => handleFieldChange('max_wall_time_ms', e.target.value ? parseInt(e.target.value) : undefined)}
              disabled={!isEditable}
              placeholder="Без лимита"
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>Таймаут инструмента (мс)</label>
            <Input
              type="number"
              value={formData.tool_timeout_ms ?? ''}
              onChange={(e) => handleFieldChange('tool_timeout_ms', e.target.value ? parseInt(e.target.value) : undefined)}
              disabled={!isEditable}
              placeholder="Без лимита"
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>Лимит токенов</label>
            <Input
              type="number"
              value={formData.budget_tokens ?? ''}
              onChange={(e) => handleFieldChange('budget_tokens', e.target.value ? parseInt(e.target.value) : undefined)}
              disabled={!isEditable}
              placeholder="Без лимита"
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>Лимит стоимости (центы)</label>
            <Input
              type="number"
              value={formData.budget_cost_cents ?? ''}
              onChange={(e) => handleFieldChange('budget_cost_cents', e.target.value ? parseInt(e.target.value) : undefined)}
              disabled={!isEditable}
              placeholder="Без лимита"
            />
          </div>
        </div>
      </ContentBlock>

      <ContentBlock title="Заметки" icon="file-text">
        {isEditable ? (
          <Textarea
            value={formData.notes || ''}
            onChange={(e) => handleFieldChange('notes', e.target.value)}
            placeholder="Описание изменений..."
            rows={6}
            style={{ fontFamily: 'monospace', fontSize: '0.875rem' }}
          />
        ) : (
          <pre style={{ 
            whiteSpace: 'pre-wrap', 
            wordBreak: 'break-word',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
            lineHeight: '1.5',
          }}>
            {formData.notes || 'Нет заметок'}
          </pre>
        )}
      </ContentBlock>
    </EntityPage>
  );
}

export default PolicyVersionPage;
