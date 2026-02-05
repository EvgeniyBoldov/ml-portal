/**
 * BaselineEditorPage - View/Edit baseline container with versions
 * 
 * NEW ARCHITECTURE:
 * - Uses SplitLayout for container + versions
 * - EntityInfoBlock for container metadata
 * - VersionsBlock for versions list
 * - StatusBlock for status display
 * 
 * OLD ARCHITECTURE (deprecated):
 * - Manual ContentGrid layout
 * - Duplicated status constants
 * - Inline DataTable
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { baselinesApi, type BaselineDetail, type BaselineVersion, type BaselineVersionInfo } from '@/shared/api/baselines';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { ContentBlock, type FieldDefinition } from '@/shared/ui/ContentBlock';
import { Tabs, TabPanel } from '@/shared/ui/Tabs';
import { SplitLayout, TabsLayout } from '@/shared/ui/BaseLayout';
import { EntityInfoBlock, type EntityInfo } from '@/shared/ui/EntityInfoBlock/EntityInfoBlock';
import { VersionsBlock, type VersionInfo } from '@/shared/ui/VersionsBlock/VersionsBlock';
import { StatusBlock } from '@/shared/ui/StatusBlock/StatusBlock';
import Badge from '@/shared/ui/Badge';
import Button from '@/shared/ui/Button';
import { useStatusConfig } from '@/shared/hooks/useStatusConfig';
import styles from './BaselineEditorPage.module.css';

const SCOPE_CONFIG: Record<string, { label: string; tone: 'info' | 'warn' | 'success' }> = {
  default: { label: 'Default', tone: 'info' },
  tenant: { label: 'Tenant', tone: 'warn' },
  user: { label: 'User', tone: 'success' },
};

export function BaselineEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const statusConfig = useStatusConfig('baseline');

  const isNew = slug === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isNew ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  // Form state for container
  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
    scope: 'default' as 'default' | 'tenant' | 'user',
    is_active: true,
  });

  // Selected version
  const [selectedVersionNum, setSelectedVersionNum] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  
  // Tab state
  const [activeTab, setActiveTab] = useState('overview');

  // Load baseline container
  const { data: baseline, isLoading, refetch } = useQuery({
    queryKey: qk.baselines.detail(slug!),
    queryFn: () => baselinesApi.get(slug!),
    enabled: !!slug && !isNew,
  });

  // Load selected version details
  const { data: selectedVersion } = useQuery({
    queryKey: ['baselines', slug, 'versions', selectedVersionNum],
    queryFn: () => baselinesApi.getVersion(slug!, String(selectedVersionNum!)),
    enabled: !!slug && selectedVersionNum !== null,
  });

  // Sync form data
  useEffect(() => {
    if (baseline) {
      setFormData({
        slug: baseline.slug,
        name: baseline.name,
        description: baseline.description || '',
        scope: baseline.scope,
        is_active: baseline.is_active,
      });
      // Select active or latest version
      if (baseline.versions?.length > 0) {
        const activeVersion = baseline.versions.find((v: BaselineVersionInfo) => v.status === 'active');
        setSelectedVersionNum(activeVersion?.version || baseline.versions[0].version);
      }
    }
  }, [baseline]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: any) => baselinesApi.createContainer(data),
    onSuccess: (container: BaselineDetail) => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.list() });
      showSuccess('Бейслайн создан');
      // Инвалидируем detail query, чтобы он загрузился свежим
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(container.slug) });
      navigate(`/admin/baselines/${container.slug}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: (data: any) => baselinesApi.updateContainer(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.baselines.list() });
      showSuccess('Бейслайн обновлён');
      setSearchParams({});
      refetch();
    },
    onError: (err: any) => showError(err?.message || 'Ошибка обновления'),
  });

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isNew) {
      navigate('/admin/baselines');
    } else {
      if (baseline) {
        setFormData({
          slug: baseline.slug,
          name: baseline.name,
          description: baseline.description || '',
          scope: baseline.scope,
          is_active: baseline.is_active,
        });
      }
      setSearchParams({});
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        if (!formData.slug.trim() || !formData.name.trim()) {
          showError('Заполните все обязательные поля');
          return;
        }
        await createMutation.mutateAsync(formData);
      } else {
        await updateMutation.mutateAsync({
          name: formData.name,
          description: formData.description,
          is_active: formData.is_active,
        });
      }
    } finally {
      setSaving(false);
    }
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev: any) => ({ ...prev, [key]: value }));
  };

  const handleToggleVersion = async (version: BaselineVersionInfo) => {
    if (version.status === 'active') {
      // Archive version
      try {
        await baselinesApi.archiveVersion(slug!, String(version.version));
        showSuccess('Версия архивирована');
        queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      } catch (err: any) {
        showError(err?.message || 'Ошибка архивации');
      }
    } else if (version.status === 'draft') {
      // Activate version
      try {
        await baselinesApi.activateVersion(slug!, String(version.version));
        showSuccess('Версия активирована');
        queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      } catch (err: any) {
        showError(err?.message || 'Ошибка активации');
      }
    }
  };

  const handleCreateVersion = () => {
    navigate(`/admin/baselines/${slug}/versions/new`);
  };

  // Field definitions
  const containerFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug (ID)',
      type: 'text',
      required: true,
      disabled: !isNew,
      placeholder: 'security.no-code',
      description: isNew ? 'Уникальный идентификатор (нельзя изменить после создания)' : undefined,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'Запрет генерации кода',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Ограничения для агента...',
      rows: 2,
    },
    {
      key: 'scope',
      label: 'Scope',
      type: 'select',
      disabled: !isNew,
      options: [
        { value: 'default', label: 'Default (глобальный)' },
        { value: 'tenant', label: 'Tenant (для тенанта)' },
        { value: 'user', label: 'User (для пользователя)' },
      ],
    },
  ];

  // Tabs config
  const tabs = [
    { id: 'overview', label: 'Обзор' },
    { id: 'versions', label: `Версии (${baseline?.versions?.length || 0})` },
  ];

  // Version columns for DataTable
  const versionColumns = [
    {
      key: 'version',
      label: 'Версия',
      render: (v: BaselineVersionInfo) => `v${v.version}`,
    },
    {
      key: 'status',
      label: 'Статус',
      render: (v: BaselineVersionInfo) => (
        <Badge tone={statusConfig.tones[v.status]}>{statusConfig.labels[v.status]}</Badge>
      ),
    },
    {
      key: 'created_at',
      label: 'Создана',
      render: (v: BaselineVersionInfo) => new Date(v.created_at).toLocaleDateString('ru-RU'),
    },
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Бейслайны', href: '/admin/baselines' },
    { label: baseline?.name || 'Новый бейслайн' },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={baseline?.name || 'Новый бейслайн'}
      entityTypeLabel="бейслайна"
      backPath="/admin/baselines"
      breadcrumbs={breadcrumbs}
      loading={!isNew && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      showDelete={false}
    >
      {isNew ? (
        // NEW: Create mode - simple entity info
        <EntityInfoBlock
          entity={formData}
          entityType="baseline"
          editable={true}
          fields={containerFields}
          onFieldChange={handleFieldChange}
        />
      ) : (
        // EDIT & VIEW MODES: Use TabsLayout for consistency
        <TabsLayout
          tabs={[
            {
              id: 'overview',
              label: 'Обзор',
              content: (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
                  <SplitLayout
                    left={
                      <EntityInfoBlock
                        entity={formData}
                        entityType="baseline"
                        editable={isEditable}
                        fields={containerFields}
                        onFieldChange={handleFieldChange}
                        showStatus={false}
                      />
                    }
                    right={
                      selectedVersion ? (
                        <ContentBlock
                          width="full"
                          title={`Версия v${selectedVersion.version}`}
                          headerActions={
                            <Badge tone={statusConfig.tones[selectedVersion.status]}>
                              {statusConfig.labels[selectedVersion.status]}
                            </Badge>
                          }
                        >
                          <div className={styles.versionMeta} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                            <div>Создана: {new Date(selectedVersion.created_at).toLocaleDateString('ru-RU')}</div>
                            {selectedVersion.updated_at && (
                              <div>Обновлена: {new Date(selectedVersion.updated_at).toLocaleDateString('ru-RU')}</div>
                            )}
                            {selectedVersion.notes && (
                              <div style={{ marginTop: '0.5rem' }}>
                                <div style={{ fontWeight: 500, marginBottom: '0.25rem' }}>Заметки:</div>
                                <div>{selectedVersion.notes}</div>
                              </div>
                            )}
                          </div>
                        </ContentBlock>
                      ) : (
                        <ContentBlock
                          width="full"
                          title="Версия"
                        >
                          <div className={styles.emptyState}>
                            <p>Нет активной версии</p>
                            <Button
                              variant="primary"
                              onClick={() => navigate(`/admin/baselines/${slug}/versions/new`)}
                            >
                              Создать версию
                            </Button>
                          </div>
                        </ContentBlock>
                      )
                    }
                  />

                  {selectedVersion && (
                    <ContentBlock
                      width="full"
                      title="Шаблон бейслайна"
                    >
                      <pre className={styles.templateBlock}>
                        {selectedVersion.template}
                      </pre>
                    </ContentBlock>
                  )}
                </div>
              ),
            },
            {
              id: 'versions',
              label: `Версии (${baseline?.versions?.length || 0})`,
              content: (
                <div className={styles.versionsSection}>
                  <div className={styles.versionsHeader}>
                    <Button
                      variant="primary"
                      onClick={() => navigate(`/admin/baselines/${slug}/versions/new`)}
                    >
                      Создать версию
                    </Button>
                  </div>
                  <VersionsBlock
                    entityType="baseline"
                    versions={baseline?.versions || []}
                    onSelectVersion={(version) => {
                      navigate(`/admin/baselines/${slug}/versions/${version.version}`);
                    }}
                  />
                </div>
              ),
            },
          ]}
        />
      )}
    </EntityPage>
  );
}

export default BaselineEditorPage;
