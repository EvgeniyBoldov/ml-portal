/**
 * PolicyEditorPage - View/Edit/Create execution policy with versioning support
 * 
 * NEW ARCHITECTURE:
 * - Uses TabsLayout for all modes (policy naturally has tabs)
 * - EntityInfoBlock for container metadata
 * - VersionsBlock for versions list
 * - StatusBlock for status display
 * 
 * OLD ARCHITECTURE (deprecated):
 * - Manual Tabs with ContentGrid layout
 * - Duplicated status constants
 * - Inline DataTable
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { policiesApi, type PolicyCreate, type PolicyVersion, type PolicyVersionStatus } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { Tabs, TabPanel } from '@/shared/ui/Tabs';
import { TabsLayout } from '@/shared/ui/BaseLayout';
import { EntityInfoBlock, type EntityInfo } from '@/shared/ui/EntityInfoBlock/EntityInfoBlock';
import { VersionsBlock, type VersionInfo } from '@/shared/ui/VersionsBlock/VersionsBlock';
import { StatusBlock } from '@/shared/ui/StatusBlock/StatusBlock';
import { ContentBlock, type FieldDefinition } from '@/shared/ui';
import Badge from '@/shared/ui/Badge';
import Button from '@/shared/ui/Button';
import { useStatusConfig } from '@/shared/hooks/useStatusConfig';
import styles from './PolicyEditorPage.module.css';

interface FormData extends PolicyCreate {
  is_active?: boolean;
}

export function PolicyEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const statusConfig = useStatusConfig('policy');

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
        <Badge tone={statusConfig.tones[v.status]}>{statusConfig.labels[v.status]}</Badge>
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

  // Field definitions for ContentBlock
  const infoFields: FieldDefinition[] = [
    { key: 'name', label: 'Название', type: 'text', required: true, placeholder: 'Моя политика' },
    { key: 'slug', label: 'Slug', type: 'text', required: true, placeholder: 'my-policy', description: 'Уникальный идентификатор', disabled: !isCreate },
    { key: 'description', label: 'Описание', type: 'textarea', placeholder: 'Описание политики...', rows: 3 },
    { key: 'is_active', label: 'Статус', type: 'boolean', disabled: !isEditable },
  ];

  const infoFieldsWithoutStatus: FieldDefinition[] = [
    { key: 'name', label: 'Название', type: 'text', required: true, placeholder: 'Моя политика' },
    { key: 'slug', label: 'Slug', type: 'text', required: true, placeholder: 'my-policy', description: 'Уникальный идентификатор', disabled: true },
    { key: 'description', label: 'Описание', type: 'textarea', placeholder: 'Описание политики...', rows: 3 },
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
        // Create mode - simple entity info without tabs
        <EntityInfoBlock
          entity={formData}
          entityType="policy"
          editable={true}
          fields={infoFields}
          onFieldChange={handleFieldChange}
        />
      ) : (
        // Edit/View modes - tabs layout
        <TabsLayout
          tabs={[
            {
              id: 'overview',
              label: 'Обзор',
              content: (
                <EntityInfoBlock
                  entity={formData}
                  entityType="policy"
                  editable={isEditable}
                  fields={infoFields}
                  onFieldChange={handleFieldChange}
                  showStatus={true}
                  status={formData.is_active ? 'active' : 'inactive'}
                  statusVersion={undefined}
                />
              ),
            },
            {
              id: 'versions',
              label: `Версии (${policy?.versions?.length || 0})`,
              content: (
                <div className={styles.versionsSection}>
                  <div className={styles.versionsHeader}>
                    <Button
                      variant="primary"
                      onClick={() => navigate(`/admin/policies/${slug}/versions/new`)}
                      disabled={!isEditable}
                    >
                      Создать версию
                    </Button>
                  </div>
                  <VersionsBlock
                    entityType="policy"
                    versions={policy?.versions || []}
                    onSelectVersion={(version) => {
                      navigate(`/admin/policies/${slug}/versions/${version.version}`);
                    }}
                  />
                </div>
              ),
            },
          ]}
          activeTab={activeTab}
          onTabChange={setActiveTab}
        />
      )}
    </EntityPage>
  );
}

export default PolicyEditorPage;
