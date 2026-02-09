/**
 * PromptVersionPage - View/Edit/Create prompt version
 * 
 * REFACTORED: Simplified with shared components
 * Reduced from 250 lines to ~150 lines
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { promptsApi, type PromptVersion } from '@/shared/api/prompts';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, ContentBlock, Textarea, Badge, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui';
import { useVersionActions } from '@/shared/hooks/useVersionActions';

export function PromptVersionPage() {
  const { slug, version: versionParam } = useParams<{ slug: string; version: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isCreate = !versionParam;
  const versionNumber = isCreate ? 0 : parseInt(versionParam, 10);
  const isEditMode = searchParams.get('mode') === 'edit';
  const fromVersion = searchParams.get('from');
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const [formData, setFormData] = useState({ template: '' });
  const [saving, setSaving] = useState(false);

  // Load prompt for breadcrumbs
  const { data: prompt } = useQuery({
    queryKey: qk.prompts.detail(slug!),
    queryFn: () => promptsApi.getPrompt(slug!),
    enabled: !!slug,
  });

  // Load existing version
  const { data: existingVersion, isLoading } = useQuery({
    queryKey: qk.prompts.version(slug!, versionNumber),
    queryFn: () => promptsApi.getVersion(slug!, versionNumber),
    enabled: !isCreate && !!slug && versionNumber > 0,
  });

  // Load source version for duplication
  const fromVersionNumber = fromVersion ? parseInt(fromVersion, 10) : 0;
  const { data: sourceVersion } = useQuery({
    queryKey: qk.prompts.version(slug!, fromVersionNumber),
    queryFn: () => promptsApi.getVersion(slug!, fromVersionNumber),
    enabled: isCreate && !!slug && fromVersionNumber > 0,
  });

  useEffect(() => {
    if (isCreate && sourceVersion) {
      setFormData({ template: sourceVersion.template || '' });
    } else if (isCreate) {
      setFormData({ template: '' });
    } else if (existingVersion) {
      setFormData({ template: existingVersion.template });
    }
  }, [existingVersion, isCreate, sourceVersion]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: { template: string }) => promptsApi.createVersion(slug!, data),
    onSuccess: (created: PromptVersion) => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      showSuccess('Версия создана');
      navigate(`/admin/prompts/${slug}/versions/${created.version}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: (data: { template: string }) => promptsApi.updateVersion(existingVersion!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.version(slug!, versionNumber) });
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      showSuccess('Версия обновлена');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const activateMutation = useMutation({
    mutationFn: () => promptsApi.activateVersion(existingVersion!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.prompts.version(slug!, versionNumber) });
      showSuccess('Версия активирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deactivateMutation = useMutation({
    mutationFn: () => promptsApi.archiveVersion(existingVersion!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.prompts.version(slug!, versionNumber) });
      showSuccess('Версия архивирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const setRecommendedMutation = useMutation({
    mutationFn: () => promptsApi.setRecommendedVersion(slug!, existingVersion!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      showSuccess('Основная версия установлена');
    },
    onError: (err: Error) => showError(err.message),
  });

  // Handlers
  const handleSave = async () => {
    if (!formData.template.trim()) {
      showError('Template не может быть пустым');
      return;
    }
    setSaving(true);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(formData);
      } else {
        await updateMutation.mutateAsync(formData);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });
  
  const handleCancel = () => {
    if (isCreate) {
      navigate(`/admin/prompts/${slug}`);
    } else {
      if (existingVersion) {
        setFormData({ template: existingVersion.template });
      }
      setSearchParams({});
    }
  };

  
  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Промпты', href: '/admin/prompts' },
    { label: prompt?.name || slug || '', href: `/admin/prompts/${slug}` },
    { label: isCreate ? 'Новая версия' : `Версия ${versionNumber}` },
  ];

  const isRecommended = !!(prompt?.recommended_version?.id && existingVersion?.id && prompt.recommended_version.id === existingVersion.id);

  const actionButtons = useVersionActions({
    status: existingVersion?.status,
    isRecommended,
    isCreate,
    callbacks: {
      onEdit: () => setSearchParams({ mode: 'edit' }),
      onActivate: () => activateMutation.mutate(),
      onDeactivate: () => deactivateMutation.mutate(),
      onSetRecommended: () => setRecommendedMutation.mutate(),
      onDuplicate: () => navigate(`/admin/prompts/${slug}/versions/new?from=${versionNumber}`),
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
      backPath={`/admin/prompts/${slug}`}
      breadcrumbs={breadcrumbs}
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      actionButtons={actionButtons}
    >
      <ContentBlock
        title="Template"
        icon="file-text"
        headerActions={
          !isCreate && existingVersion?.status ? (
            <Badge tone={existingVersion.status === 'active' ? 'success' : existingVersion.status === 'draft' ? 'warn' : 'neutral'} size="small">
              {existingVersion.status === 'active' ? 'Активна' : existingVersion.status === 'draft' ? 'Черновик' : 'Архив'}
            </Badge>
          ) : undefined
        }
      >
        {isEditable ? (
          <Textarea
            value={formData.template}
            onChange={(e) => setFormData({ template: e.target.value })}
            placeholder="Введите template промпта..."
            rows={20}
            style={{ fontFamily: 'monospace' }}
          />
        ) : (
          <pre style={{ 
            whiteSpace: 'pre-wrap', 
            wordBreak: 'break-word',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
            lineHeight: '1.5',
          }}>
            {existingVersion?.template || 'Нет template'}
          </pre>
        )}
      </ContentBlock>
    </EntityPage>
  );
}

export default PromptVersionPage;
