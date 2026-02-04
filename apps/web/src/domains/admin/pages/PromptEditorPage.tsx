/**
 * PromptEditorPage - View/Edit prompt container with versions
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
import { promptsApi, type PromptDetail, type PromptVersion, type PromptVersionInfo } from '@/shared/api/prompts';
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
import styles from './PromptEditorPage.module.css';

export function PromptEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const statusConfig = useStatusConfig('prompt');

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

  const handleToggleVersion = async (version: PromptVersionInfo) => {
    if (version.status === 'active') {
      // Archive version
      try {
        await promptsApi.archiveVersion(version.id);
        showSuccess('Версия архивирована');
        queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      } catch (err: any) {
        showError(err?.message || 'Ошибка архивации');
      }
    } else if (version.status === 'draft') {
      // Activate version
      try {
        await promptsApi.activateVersion(version.id);
        showSuccess('Версия активирована');
        queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      } catch (err: any) {
        showError(err?.message || 'Ошибка активации');
      }
    }
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
        <Badge tone={statusConfig.tones[v.status]}>{statusConfig.labels[v.status]}</Badge>
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
        // NEW: Create mode - simple entity info
        <EntityInfoBlock
          entity={formData}
          entityType="prompt"
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
                        entityType="prompt"
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
                          </div>
                        </ContentBlock>
                      ) : (
                        <ContentBlock
                          width="full"
                          title="Версия"
                        >
                          <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                            Нет активной версии
                          </div>
                        </ContentBlock>
                      )
                    }
                  />
                  
                  {selectedVersion && (
                    <ContentBlock
                      width="full"
                      title="Шаблон промпта"
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
              label: `Версии (${prompt?.versions?.length || 0})`,
              content: (
                <div className={styles.versionsSection}>
                  <div className={styles.versionsHeader}>
                    <Button
                      variant="primary"
                      onClick={() => navigate(`/admin/prompts/${slug}/versions/new`)}
                    >
                      Создать версию
                    </Button>
                  </div>
                  <VersionsBlock
                    entityType="prompt"
                    versions={prompt?.versions || []}
                    onSelectVersion={(version) => {
                      navigate(`/admin/prompts/${slug}/versions/${version.version}`);
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

export default PromptEditorPage;
