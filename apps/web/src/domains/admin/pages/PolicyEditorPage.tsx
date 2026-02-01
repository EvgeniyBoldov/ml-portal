/**
 * PolicyEditorPage - View/Edit/Create execution policy with versioning support
 * 
 * Architecture:
 * - Policy (container) - holds metadata: slug, name, description
 * - PolicyVersion - holds versioned data: limits, timeouts, budgets
 * - recommended_version_id - points to the version that should be used by default
 * 
 * Routes:
 * - /admin/policies/new - Create new policy container
 * - /admin/policies/:slug - View policy with tabs (Overview | Versions)
 * - /admin/policies/:slug?mode=edit - Edit policy metadata
 * - /admin/policies/:slug/versions/:version - View/Edit specific version
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { policiesApi, type PolicyCreate, type PolicyVersion, type PolicyVersionStatus } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { Tabs, TabPanel } from '@/shared/ui/Tabs';
import { Badge, Button, DataTable, FormField, ShortEntityBlock } from '@/shared/ui';
import styles from './PolicyEditorPage.module.css';

interface FormData extends PolicyCreate {
  is_active?: boolean;
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

export function PolicyEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // Determine mode
  const isCreate = slug === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  // Tab state
  const [activeTab, setActiveTab] = useState('overview');

  const [formData, setFormData] = useState<FormData>({
    slug: '',
    name: '',
    description: '',
    is_active: true,
  });
  const [saving, setSaving] = useState(false);

  // Load existing policy with versions
  const { data: policy, isLoading, refetch } = useQuery({
    queryKey: qk.policies.detail(slug!),
    queryFn: () => policiesApi.get(slug!),
    enabled: !isCreate && !!slug,
  });

  useEffect(() => {
    if (policy) {
      setFormData({
        slug: policy.slug,
        name: policy.name,
        description: policy.description || '',
        is_active: policy.is_active,
      });
    }
  }, [policy]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: PolicyCreate) => policiesApi.create(data),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: qk.policies.all() });
      showSuccess('Политика создана');
      navigate(`/admin/policies/${created.slug}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: (data: { name?: string; description?: string; is_active?: boolean }) =>
      policiesApi.update(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.all() });
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      showSuccess('Политика обновлена');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => policiesApi.delete(slug!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.all() });
      showSuccess('Политика удалена');
      navigate('/admin/policies');
    },
    onError: (err: Error) => showError(err.message),
  });

  const activateVersionMutation = useMutation({
    mutationFn: (version: number) => policiesApi.activateVersion(slug!, version),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      showSuccess('Версия активирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deactivateVersionMutation = useMutation({
    mutationFn: (version: number) => policiesApi.deactivateVersion(slug!, version),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      showSuccess('Версия деактивирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deleteVersionMutation = useMutation({
    mutationFn: (version: number) => policiesApi.deleteVersion(slug!, version),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      showSuccess('Версия удалена');
    },
    onError: (err: Error) => showError(err.message),
  });

  const handleSave = async () => {
    setSaving(true);
    try {
      if (mode === 'create') {
        await createMutation.mutateAsync({
          slug: formData.slug,
          name: formData.name,
          description: formData.description || undefined,
        });
      } else {
        await updateMutation.mutateAsync({
          name: formData.name,
          description: formData.description || undefined,
          is_active: formData.is_active,
        });
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (mode === 'edit' && policy) {
      setFormData({
        slug: policy.slug,
        name: policy.name,
        description: policy.description || '',
        is_active: policy.is_active,
      });
      setSearchParams({});
    } else if (mode === 'create') {
      navigate('/admin/policies');
    }
  };

  const handleDelete = async () => {
    if (!confirm('Удалить эту политику и все её версии?')) return;
    await deleteMutation.mutateAsync();
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const handleCreateVersion = () => {
    navigate(`/admin/policies/${slug}/versions/new`);
  };

  const handleVersionClick = (version: PolicyVersion) => {
    navigate(`/admin/policies/${slug}/versions/${version.version}`);
  };

  // Versions table columns
  const versionColumns = [
    {
      key: 'version',
      header: 'Версия',
      render: (v: PolicyVersion) => `v${v.version}`,
    },
    {
      key: 'status',
      header: 'Статус',
      render: (v: PolicyVersion) => (
        <Badge variant={STATUS_VARIANTS[v.status]}>{STATUS_LABELS[v.status]}</Badge>
      ),
    },
    {
      key: 'limits',
      header: 'Лимиты',
      render: (v: PolicyVersion) => (
        <span style={{ fontSize: '0.85em', color: 'var(--text-secondary)' }}>
          {v.max_steps ?? '∞'} шагов, {v.max_tool_calls ?? '∞'} вызовов
        </span>
      ),
    },
    {
      key: 'created_at',
      header: 'Создана',
      render: (v: PolicyVersion) => new Date(v.created_at).toLocaleDateString('ru'),
    },
    {
      key: 'actions',
      header: '',
      render: (v: PolicyVersion) => (
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {v.status === 'draft' && (
            <Button
              size="small"
              variant="primary"
              onClick={(e) => {
                e.stopPropagation();
                activateVersionMutation.mutate(v.version);
              }}
            >
              Активировать
            </Button>
          )}
          {v.status === 'active' && (
            <Button
              size="small"
              variant="secondary"
              onClick={(e) => {
                e.stopPropagation();
                deactivateVersionMutation.mutate(v.version);
              }}
            >
              Деактивировать
            </Button>
          )}
          {v.status !== 'active' && (
            <Button
              size="small"
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation();
                if (confirm('Удалить эту версию?')) {
                  deleteVersionMutation.mutate(v.version);
                }
              }}
            >
              Удалить
            </Button>
          )}
        </div>
      ),
    },
  ];

  const tabs = [
    { id: 'overview', label: 'Обзор' },
    { id: 'versions', label: `Версии (${policy?.versions?.length || 0})` },
  ];

  const breadcrumbs = isCreate
    ? [
        { label: 'Политики', href: '/admin/policies' },
        { label: 'Новая политика' },
      ]
    : [
        { label: 'Политики', href: '/admin/policies' },
        { label: policy?.name || slug || '' },
      ];

  return (
    <EntityPage
      mode={mode}
      entityName={policy ? policy.name : 'Новая политика'}
      entityTypeLabel="политики"
      backPath="/admin/policies"
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={handleDelete}
      showDelete={mode === 'view' && !!slug && policy?.slug !== 'default'}
      breadcrumbs={breadcrumbs}
    >

      {isCreate ? (
        <div className={styles.grid}>
          <div className={styles.mainColumn}>
            <div className={styles.section}>
              <div className={styles.sectionContent}>
                <FormField
                  label="Slug"
                  value={formData.slug}
                  editable={true}
                  required
                  placeholder="my-policy"
                  description="Уникальный идентификатор"
                  onChange={(v) => handleFieldChange('slug', v)}
                />
                <FormField
                  label="Название"
                  value={formData.name}
                  editable={true}
                  required
                  placeholder="Моя политика"
                  onChange={(v) => handleFieldChange('name', v)}
                />
                <FormField
                  label="Описание"
                  value={formData.description}
                  type="textarea"
                  editable={true}
                  placeholder="Описание политики..."
                  onChange={(v) => handleFieldChange('description', v)}
                />
              </div>
            </div>
          </div>
        </div>
      ) : (
        <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab}>
          <TabPanel id="overview" activeTab={activeTab}>
            <div className={styles.grid}>
              <div className={styles.mainColumn}>
                <div className={styles.section}>
                  <div className={styles.sectionContent}>
                    <FormField
                      label="Slug"
                      value={formData.slug}
                      editable={false}
                      required
                      description="Уникальный идентификатор"
                    />
                    <FormField
                      label="Название"
                      value={formData.name}
                      editable={isEditable}
                      required
                      onChange={(v) => handleFieldChange('name', v)}
                    />
                    <FormField
                      label="Описание"
                      value={formData.description}
                      type="textarea"
                      editable={isEditable}
                      onChange={(v) => handleFieldChange('description', v)}
                    />
                    <FormField
                      label="Активна"
                      value={formData.is_active}
                      type="switch"
                      editable={isEditable}
                      description="Политика доступна для использования"
                      onChange={(v) => handleFieldChange('is_active', v)}
                    />
                  </div>
                </div>
              </div>

              <div className={styles.sideColumn}>
                {policy?.recommended_version ? (
                  <ShortEntityBlock
                    title={`v${policy.recommended_version.version}`}
                    subtitle={
                      <Badge variant={STATUS_VARIANTS[policy.recommended_version.status]}>
                        {STATUS_LABELS[policy.recommended_version.status]}
                      </Badge>
                    }
                    items={[
                      { label: 'Шагов', value: policy.recommended_version.max_steps ?? '∞' },
                      { label: 'Вызовов', value: policy.recommended_version.max_tool_calls ?? '∞' },
                      { label: 'Таймаут', value: `${policy.recommended_version.max_wall_time_ms ?? '∞'} мс` },
                    ]}
                    actionLabel="Подробнее"
                    onAction={() => navigate(`/admin/policies/${slug}/versions/${policy.recommended_version!.version}`)}
                  />
                ) : (
                  <ShortEntityBlock title="Нет версии">
                    <Button size="small" variant="primary" onClick={handleCreateVersion}>
                      Создать версию
                    </Button>
                  </ShortEntityBlock>
                )}
              </div>
            </div>
          </TabPanel>

          <TabPanel id="versions" activeTab={activeTab}>
            <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'flex-end' }}>
              <Button variant="primary" onClick={handleCreateVersion}>
                Создать версию
              </Button>
            </div>
            <DataTable
              columns={versionColumns}
              data={policy?.versions || []}
              onRowClick={handleVersionClick}
              emptyMessage="Нет версий. Создайте первую версию политики."
            />
          </TabPanel>
        </Tabs>
      )}
    </EntityPage>
  );
}

export default PolicyEditorPage;
