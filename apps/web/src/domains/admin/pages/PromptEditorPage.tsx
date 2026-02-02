/**
 * PromptEditorPage - View/Edit prompt container with versions
 * 
 * Layout:
 * - Left column (1/2): Container info + Versions table
 * - Right column (1/2): Selected version template + status
 * 
 * Features:
 * - View/Edit container (name, description)
 * - View versions list with selection
 * - View selected version template
 * - Create new version via modal
 * - Activate/Archive version
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { promptsApi, type PromptDetail, type PromptVersion, type PromptVersionInfo } from '@/shared/api/prompts';
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

export function PromptEditorPage() {
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
    type: 'prompt' as 'prompt' | 'baseline',
  });

  // Selected version
  const [selectedVersionNum, setSelectedVersionNum] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  
  // Tab state
  const [activeTab, setActiveTab] = useState('overview');


  // Load prompt container
  const { data: prompt, isLoading, refetch } = useQuery({
    queryKey: qk.prompts.detail(slug!),
    queryFn: () => promptsApi.getPrompt(slug!),
    enabled: !!slug && !isNew,
  });

  // Load selected version details
  const { data: selectedVersion } = useQuery({
    queryKey: ['prompts', slug, 'versions', selectedVersionNum],
    queryFn: () => promptsApi.getVersion(slug!, selectedVersionNum!),
    enabled: !!slug && selectedVersionNum !== null,
  });

  // Sync form data
  useEffect(() => {
    if (prompt) {
      setFormData({
        slug: prompt.slug,
        name: prompt.name,
        description: prompt.description || '',
        type: prompt.type,
      });
      // Select active or latest version
      if (prompt.versions?.length > 0) {
        const activeVersion = prompt.versions.find(v => v.status === 'active');
        setSelectedVersionNum(activeVersion?.version || prompt.versions[0].version);
      }
    }
  }, [prompt]);

  // Mutations
  const createContainerMutation = useMutation({
    mutationFn: () => promptsApi.createContainer(formData),
    onSuccess: (container) => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.list() });
      showSuccess('Промпт создан');
      navigate(`/admin/prompts/${container.slug}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateContainerMutation = useMutation({
    mutationFn: () => promptsApi.updateContainer(slug!, {
      name: formData.name,
      description: formData.description,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      showSuccess('Промпт обновлён');
      setSearchParams({});
    },
    onError: (err: any) => showError(err?.message || 'Ошибка обновления'),
  });


  // Handlers
  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        await createContainerMutation.mutateAsync();
      } else {
        await updateContainerMutation.mutateAsync();
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isNew) {
      navigate('/admin/prompts');
    } else {
      if (prompt) {
        setFormData({
          slug: prompt.slug,
          name: prompt.name,
          description: prompt.description || '',
          type: prompt.type,
        });
      }
      setSearchParams({});
    }
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };


  // Field definitions
  const containerFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug (ID)',
      type: 'text',
      required: true,
      disabled: !isNew,
      placeholder: 'chat.rag.system',
      description: isNew ? 'Уникальный идентификатор (нельзя изменить после создания)' : undefined,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'RAG System Prompt',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Описание промпта...',
      rows: 2,
    },
    {
      key: 'type',
      label: 'Тип',
      type: 'select',
      disabled: !isNew,
      options: [
        { value: 'prompt', label: 'Prompt (инструкции)' },
        { value: 'baseline', label: 'Baseline (ограничения)' },
      ],
    },
  ];

  // Tabs config
  const tabs = [
    { id: 'overview', label: 'Обзор' },
    { id: 'versions', label: `Версии (${prompt?.versions?.length || 0})` },
  ];

  // Version columns for DataTable
  const versionColumns = [
    {
      key: 'version',
      label: 'Версия',
      render: (v: PromptVersionInfo) => `v${v.version}`,
    },
    {
      key: 'status',
      label: 'Статус',
      render: (v: PromptVersionInfo) => (
        <Badge tone={STATUS_TONES[v.status]}>{STATUS_LABELS[v.status]}</Badge>
      ),
    },
    {
      key: 'created_at',
      label: 'Создана',
      render: (v: PromptVersionInfo) => new Date(v.created_at).toLocaleDateString('ru'),
    },
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Промпты', href: '/admin/prompts' },
    { label: prompt?.name || 'Новый промпт' },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={prompt?.name || 'Новый промпт'}
      entityTypeLabel="промпта"
      backPath="/admin/prompts"
      breadcrumbs={breadcrumbs}
      loading={!isNew && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      showDelete={false}
    >
      {isNew ? (
        <ContentGrid>
          <ContentBlock
            width="1/2"
            title="Основная информация"
            editable={true}
            fields={containerFields}
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
                fields={containerFields}
                data={formData}
                onChange={handleFieldChange}
              />

              {/* Right column: Status badge (compact) - 1/2 */}
              <StatusBadgeCard
                label="Тип"
                status={formData.type}
                statusOptions={[
                  { value: 'prompt', label: 'Prompt', tone: 'info' },
                  { value: 'baseline', label: 'Baseline', tone: 'warn' },
                ]}
                editable={false}
                width="1/2"
              />

              {/* Active version preview - full width on new row */}
              {selectedVersion ? (
                <ContentBlock
                  width="full"
                  title={`Активная версия (v${selectedVersion.version})`}
                  headerActions={
                    <Badge tone={STATUS_TONES[selectedVersion.status]}>
                      {STATUS_LABELS[selectedVersion.status]}
                    </Badge>
                  }
                >
                  <pre className={styles.templateBlock}>
                    {selectedVersion.template.substring(0, 500)}
                    {selectedVersion.template.length > 500 && '...'}
                  </pre>
                  <div className={styles.versionActions}>
                    <Button
                      size="small"
                      variant="outline"
                      onClick={() => navigate(`/admin/prompts/${slug}/versions/${selectedVersion.version}`)}
                    >
                      Подробнее
                    </Button>
                  </div>
                </ContentBlock>
              ) : (
                <ContentBlock
                  width="full"
                  title="Активная версия"
                >
                  <div className={styles.emptyVersion}>
                    <p>Нет версий</p>
                    <Button variant="primary" onClick={() => navigate(`/admin/prompts/${slug}/versions/new`)}>
                      Создать версию
                    </Button>
                  </div>
                </ContentBlock>
              )}
            </ContentGrid>
          </TabPanel>

          <TabPanel id="versions" activeTab={activeTab}>
            <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'flex-end' }}>
              <Button variant="primary" onClick={() => navigate(`/admin/prompts/${slug}/versions/new`)}>
                Создать версию
              </Button>
            </div>
            <DataTable
              columns={versionColumns}
              data={prompt?.versions || []}
              onRowClick={(v: PromptVersionInfo) => navigate(`/admin/prompts/${slug}/versions/${v.version}`)}
              emptyMessage="Нет версий. Создайте первую версию промпта."
            />
          </TabPanel>
        </Tabs>
      )}

    </EntityPage>
  );
}

export default PromptEditorPage;
