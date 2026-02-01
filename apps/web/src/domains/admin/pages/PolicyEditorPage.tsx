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
import { Badge, Button, DataTable, ContentBlock, ContentGrid, StatusBadgeCard, type FieldDefinition, type StatusOption } from '@/shared/ui';

interface FormData extends PolicyCreate {
  is_active?: boolean;
}

const STATUS_LABELS: Record<PolicyVersionStatus, string> = {
  draft: 'Черновик',
  active: 'Активная',
  inactive: 'Неактивная',
};

const STATUS_TONES: Record<PolicyVersionStatus, 'neutral' | 'success' | 'warn' | 'danger' | 'info'> = {
  draft: 'warn',
  active: 'success',
  inactive: 'neutral',
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
        <Badge tone={STATUS_TONES[v.status]}>{STATUS_LABELS[v.status]}</Badge>
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
  ];

  const infoFieldsWithoutStatus: FieldDefinition[] = [
    { key: 'name', label: 'Название', type: 'text', required: true, placeholder: 'Моя политика' },
    { key: 'slug', label: 'Slug', type: 'text', required: true, placeholder: 'my-policy', description: 'Уникальный идентификатор', disabled: true },
    { key: 'description', label: 'Описание', type: 'textarea', placeholder: 'Описание политики...', rows: 3 },
  ];

  // Status options for policy
  const policyStatusOptions: StatusOption[] = [
    { value: 'active', label: 'Активна', tone: 'success' },
    { value: 'inactive', label: 'Неактивна', tone: 'neutral' },
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
        <ContentGrid>
          <ContentBlock
            width="1/2"
            title="Основная информация"
            editable={true}
            fields={infoFields}
            data={formData}
            onChange={handleFieldChange}
          />
        </ContentGrid>
      ) : (
        <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab}>
          <TabPanel id="overview" activeTab={activeTab}>
            <ContentGrid>
              {/* Left column: Info block - 1/2 */}
              <ContentBlock
                width="1/2"
                title="Основная информация"
                editable={isEditable}
                fields={infoFieldsWithoutStatus}
                data={formData}
                onChange={handleFieldChange}
              />

              {/* Right column: Status block (compact) */}
              <StatusBadgeCard
                status={formData.is_active ? 'active' : 'inactive'}
                statusOptions={policyStatusOptions}
                editable={isEditable}
                onStatusChange={(s) => handleFieldChange('is_active', s === 'active')}
              />

              {/* Right column: Version block - 1/2 (below status) */}
              {policy?.recommended_version ? (
                <ContentBlock
                  width="1/2"
                  title={`Основная версия (v${policy.recommended_version.version})`}
                  headerActions={
                    <Badge tone={STATUS_TONES[policy.recommended_version.status]}>
                      {STATUS_LABELS[policy.recommended_version.status]}
                    </Badge>
                  }
                >
                  <ContentGrid gap="sm">
                    <ContentBlock
                      width="1/2"
                      title="Лимиты"
                      compact
                    >
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <div><strong>Шагов:</strong> {policy.recommended_version.max_steps ?? '∞'}</div>
                        <div><strong>Вызовов:</strong> {policy.recommended_version.max_tool_calls ?? '∞'}</div>
                        <div><strong>Повторов:</strong> {policy.recommended_version.max_retries ?? '∞'}</div>
                      </div>
                    </ContentBlock>
                    <ContentBlock
                      width="1/2"
                      title="Таймауты"
                      compact
                    >
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <div><strong>Общий:</strong> {policy.recommended_version.max_wall_time_ms ?? '∞'} мс</div>
                        <div><strong>Инструмент:</strong> {policy.recommended_version.tool_timeout_ms ?? '∞'} мс</div>
                      </div>
                    </ContentBlock>
                  </ContentGrid>
                  <div style={{ marginTop: '1rem' }}>
                    <Button
                      size="small"
                      variant="outline"
                      onClick={() => navigate(`/admin/policies/${slug}/versions/${policy.recommended_version!.version}`)}
                    >
                      Подробнее
                    </Button>
                  </div>
                </ContentBlock>
              ) : (
                <ContentBlock
                  width="1/2"
                  title="Основная версия"
                >
                  <div style={{ textAlign: 'center', padding: '2rem' }}>
                    <p style={{ marginBottom: '1rem', color: 'var(--text-secondary)' }}>Нет версии</p>
                    <Button variant="primary" onClick={handleCreateVersion}>
                      Создать версию
                    </Button>
                  </div>
                </ContentBlock>
              )}
            </ContentGrid>
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
