/**
 * BaselineEditorPage - View/Edit baseline container with versions
 * 
 * Layout:
 * - Left column (1/2): Container info
 * - Right column (1/2): Selected version status
 * 
 * Features:
 * - View/Edit container (name, description, scope, is_active)
 * - View versions list with selection
 * - View selected version template
 * - Create new version
 * - Activate/Archive version
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { baselinesApi, type BaselineDetail, type BaselineVersion, type BaselineVersionInfo } from '@/shared/api/baselines';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';
import { Tabs, TabPanel } from '@/shared/ui/Tabs';
import { StatusBadgeCard, type StatusOption } from '@/shared/ui/StatusBadgeCard';
import Badge from '@/shared/ui/Badge';
import Button from '@/shared/ui/Button';
import DataTable from '@/shared/ui/DataTable/DataTable';
import styles from './PromptEditorPage.module.css';

const STATUS_LABELS: Record<string, string> = {
  draft: 'Черновик',
  active: 'Активна',
  archived: 'Архив',
};

const STATUS_TONES: Record<string, 'warn' | 'success' | 'neutral'> = {
  draft: 'warn',
  active: 'success',
  archived: 'neutral',
};

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
    queryFn: () => baselinesApi.getVersion(slug!, selectedVersionNum!),
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
        const activeVersion = baseline.versions.find(v => v.status === 'active');
        setSelectedVersionNum(activeVersion?.version || baseline.versions[0].version);
      }
    }
  }, [baseline]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: any) => baselinesApi.createContainer(data),
    onSuccess: (container) => {
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
    setFormData(prev => ({ ...prev, [key]: value }));
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
        <Badge tone={STATUS_TONES[v.status]}>{STATUS_LABELS[v.status]}</Badge>
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
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab}>
        <TabPanel id="overview" activeTab={activeTab}>
          <ContentGrid>
            {/* Left column: Info block - 1/2 */}
            <ContentBlock
              width="1/2"
              title="Основная информация"
              editable={isEditable}
              fields={containerFields}
              data={formData}
              onChange={handleFieldChange}
            />

            {/* Right column: Status badge (compact) - 1/2 */}
            <StatusBadgeCard
              label="Статус"
              status={formData.is_active ? 'active' : 'inactive'}
              statusOptions={[
                { value: 'active', label: 'Активен', tone: 'success' },
                { value: 'inactive', label: 'Неактивен', tone: 'neutral' },
              ]}
              editable={isEditable}
              onStatusChange={(s) => handleFieldChange('is_active', s === 'active')}
              width="1/2"
            />

            {/* Version block - under status, full width */}
            {baseline?.recommended_version ? (
              <ContentBlock
                width="full"
                title={`Основная версия (v${baseline.recommended_version.version})`}
                headerActions={
                  <Badge tone={STATUS_TONES[baseline.recommended_version.status]}>
                    {STATUS_LABELS[baseline.recommended_version.status]}
                  </Badge>
                }
              >
                <pre className={styles.templateBlock}>
                  {selectedVersion?.template.substring(0, 500)}
                  {selectedVersion && selectedVersion.template.length > 500 && '...'}
                </pre>
                <div className={styles.versionActions}>
                  <Button
                    size="small"
                    variant="outline"
                    onClick={() => navigate(`/admin/baselines/${slug}/versions/${baseline.recommended_version!.version}`)}
                  >
                    Подробнее
                  </Button>
                </div>
              </ContentBlock>
            ) : (
              <ContentBlock
                width="full"
                title="Основная версия"
              >
                <div className={styles.emptyVersion}>
                  <p>Нет версий</p>
                  <Button variant="primary" onClick={handleCreateVersion}>
                    Создать версию
                  </Button>
                </div>
              </ContentBlock>
            )}
          </ContentGrid>
        </TabPanel>

        <TabPanel id="versions" activeTab={activeTab}>
          <ContentBlock width="full" title="Версии">
            <DataTable
              columns={versionColumns}
              data={baseline?.versions || []}
              keyField="id"
              onRowClick={(v: BaselineVersionInfo) => navigate(`/admin/baselines/${slug}/versions/${v.version}`)}
            />
            <div style={{ marginTop: '1rem' }}>
              <Button variant="primary" onClick={handleCreateVersion}>
                Создать версию
              </Button>
            </div>
          </ContentBlock>
        </TabPanel>
      </Tabs>
    </EntityPage>
  );
}

export default BaselineEditorPage;
