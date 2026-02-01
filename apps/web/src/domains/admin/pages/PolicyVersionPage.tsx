/**
 * PolicyVersionPage - View/Edit/Create policy version
 * 
 * Routes:
 * - /admin/policies/:slug/versions/new - Create new version
 * - /admin/policies/:slug/versions/:version - View version
 * - /admin/policies/:slug/versions/:version?mode=edit - Edit version (only draft)
 */
import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { policiesApi, type PolicyVersionCreate, type PolicyVersionStatus } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { Badge, Button, FormField } from '@/shared/ui';
import styles from './PolicyVersionPage.module.css';

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

  // Calculate next version number for create mode
  const nextVersionNumber = useMemo(() => {
    if (!policy?.versions?.length) return 1;
    return Math.max(...policy.versions.map((v) => v.version)) + 1;
  }, [policy?.versions]);

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

  const breadcrumbs = [
    { label: 'Политики', href: '/admin/policies' },
    { label: policy?.name || slug || '', href: `/admin/policies/${slug}` },
    { label: isCreate ? 'Новая версия' : `Версия ${versionNumber}` },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={isCreate ? `Новая версия (v${nextVersionNumber})` : `Версия ${versionNumber}`}
      entityTypeLabel="версии"
      backPath={`/admin/policies/${slug}`}
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={existingVersion?.status === 'draft' ? handleEdit : undefined}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={existingVersion?.status !== 'active' ? handleDelete : undefined}
      showDelete={mode === 'view' && existingVersion?.status !== 'active'}
      breadcrumbs={breadcrumbs}
    >
      <div className={styles.grid}>
        <div className={styles.mainColumn}>
          {renderStatusActions()}

          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Лимиты выполнения</h3>
            <div className={styles.sectionContent}>
              <FormField
                label="Макс. шагов"
                value={formData.max_steps}
                type="number"
                editable={isEditable}
                placeholder="20"
                description="Максимальное количество шагов агента"
                onChange={(v) => handleFieldChange('max_steps', v)}
              />
              <FormField
                label="Макс. вызовов"
                value={formData.max_tool_calls}
                type="number"
                editable={isEditable}
                placeholder="50"
                description="Максимальное количество вызовов инструментов"
                onChange={(v) => handleFieldChange('max_tool_calls', v)}
              />
              <FormField
                label="Макс. повторов"
                value={formData.max_retries}
                type="number"
                editable={isEditable}
                placeholder="3"
                description="Количество повторных попыток при ошибке"
                onChange={(v) => handleFieldChange('max_retries', v)}
              />
            </div>
          </div>

          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Таймауты</h3>
            <div className={styles.sectionContent}>
              <FormField
                label="Общий таймаут (мс)"
                value={formData.max_wall_time_ms}
                type="number"
                editable={isEditable}
                placeholder="300000"
                description="Максимальное время выполнения в миллисекундах"
                onChange={(v) => handleFieldChange('max_wall_time_ms', v)}
              />
              <FormField
                label="Таймаут инструмента (мс)"
                value={formData.tool_timeout_ms}
                type="number"
                editable={isEditable}
                placeholder="30000"
                description="Таймаут для одного вызова инструмента"
                onChange={(v) => handleFieldChange('tool_timeout_ms', v)}
              />
            </div>
          </div>

          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Бюджет</h3>
            <div className={styles.sectionContent}>
              <FormField
                label="Лимит токенов"
                value={formData.budget_tokens}
                type="number"
                editable={isEditable}
                placeholder="Без лимита"
                description="Максимальное количество токенов"
                onChange={(v) => handleFieldChange('budget_tokens', v)}
              />
              <FormField
                label="Лимит стоимости (центы)"
                value={formData.budget_cost_cents}
                type="number"
                editable={isEditable}
                placeholder="Без лимита"
                description="Максимальная стоимость в центах"
                onChange={(v) => handleFieldChange('budget_cost_cents', v)}
              />
            </div>
          </div>

          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Заметки</h3>
            <div className={styles.sectionContent}>
              <FormField
                label="Заметки"
                value={formData.notes}
                type="textarea"
                editable={isEditable}
                placeholder="Что изменилось в этой версии..."
                description="Описание изменений"
                onChange={(v) => handleFieldChange('notes', v)}
              />
            </div>
          </div>
        </div>

        {!isCreate && (
          <div className={styles.sideColumn}>
            <div className={styles.section}>
              <h3 className={styles.sectionTitle}>Действия</h3>
              <div className={styles.sectionContent}>
                {existingVersion?.status === 'draft' && (
                  <Button
                    variant="primary"
                    onClick={() => activateMutation.mutate()}
                    disabled={activateMutation.isPending}
                  >
                    Активировать
                  </Button>
                )}
                {existingVersion?.status === 'active' && (
                  <Button
                    variant="secondary"
                    onClick={() => deactivateMutation.mutate()}
                    disabled={deactivateMutation.isPending}
                  >
                    Деактивировать
                  </Button>
                )}
                <Button
                  variant="secondary"
                  onClick={() => navigate(`/admin/policies/${slug}/versions/new`)}
                >
                  Создать новую версию
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </EntityPage>
  );
}

export default PolicyVersionPage;
