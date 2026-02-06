/**
 * PromptEditorPage - View/Edit prompt container with versions
 * 
 * REFACTORED ARCHITECTURE:
 * - Uses EntityTabsPage for unified layout
 * - Uses PromptVersionCard for version preview
 * - Reduced from 355 lines to ~100 lines
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { promptsApi, type PromptDetail, type PromptVersionInfo } from '@/shared/api/prompts';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityTabsPage, PromptVersionCard, type FieldDefinition, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui';

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
  const [saving, setSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
    type: 'prompt' as 'prompt' | 'baseline',
  });

  // Load prompt container
  const { data: prompt, isLoading } = useQuery({
    queryKey: qk.prompts.detail(slug!),
    queryFn: () => promptsApi.getPrompt(slug!),
    enabled: !!slug && !isNew,
  });

  // Load active version for preview
  const activeVersion = prompt?.versions?.find(v => v.status === 'active') || prompt?.versions?.[0];
  const { data: selectedVersion } = useQuery({
    queryKey: ['prompts', slug, 'versions', activeVersion?.version],
    queryFn: () => promptsApi.getVersion(slug!, activeVersion!.version),
    enabled: !!slug && !!activeVersion,
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
    }
  }, [prompt]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: () => promptsApi.createContainer(formData),
    onSuccess: (container) => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.list() });
      showSuccess('Промпт создан');
      navigate(`/admin/prompts/${container.slug}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
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

  const setRecommendedMutation = useMutation({
    mutationFn: (version: PromptVersionInfo) => promptsApi.setRecommendedVersion(slug!, version.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      showSuccess('Основная версия установлена');
    },
    onError: (err: any) => showError(err?.message || 'Ошибка установки основной версии'),
  });

  // Handlers
  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        await createMutation.mutateAsync();
      } else {
        await updateMutation.mutateAsync();
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
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Промпты', href: '/admin/prompts' },
    { label: prompt?.name || 'Новый промпт' },
  ];

  return (
    <EntityTabsPage
      entityType="prompt"
      entityNameLabel="Промпт"
      entityTypeLabel="промпта"
      slug={slug!}
      basePath="/admin/prompts"
      listPath="/admin/prompts"
      container={prompt || null}
      versions={prompt?.versions || []}
      isLoading={isLoading}
      formData={formData}
      mode={mode}
      saving={saving}
      onFieldChange={handleFieldChange}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onCreateVersion={() => navigate(`/admin/prompts/${slug}/versions/new`)}
      onSelectVersion={(v: PromptVersionInfo) => navigate(`/admin/prompts/${slug}/versions/${v.version}`)}
      onSetRecommended={(v: PromptVersionInfo) => setRecommendedMutation.mutate(v)}
      containerFields={containerFields}
      breadcrumbs={breadcrumbs}
      renderVersionContent={() => (
        <PromptVersionCard
          version={selectedVersion || null}
          onCreateVersion={() => navigate(`/admin/prompts/${slug}/versions/new`)}
        />
      )}
    />
  );
}

export default PromptEditorPage;
