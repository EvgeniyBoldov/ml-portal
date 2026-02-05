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
import { EntityPage, ContentBlock, ContentGrid, Textarea, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui';
import { StatusBadgeCard, type StatusOption } from '@/shared/ui';
import { useStatusConfig } from '@/shared/hooks/useStatusConfig';
import layoutStyles from '@/shared/ui/styles/layouts.module.css';

export function PromptVersionPage() {
  const { slug, version: versionParam } = useParams<{ slug: string; version: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const statusConfig = useStatusConfig('prompt');

  const isCreate = !versionParam;
  const versionNumber = isCreate ? 0 : parseInt(versionParam, 10);
  const isEditMode = searchParams.get('mode') === 'edit';
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

  useEffect(() => {
    if (isCreate) {
      setFormData({ template: '' });
    } else if (existingVersion) {
      setFormData({ template: existingVersion.template });
    }
  }, [existingVersion, isCreate]);

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

  const changeStatusMutation = useMutation({
    mutationFn: (status: string) => promptsApi.updateVersionStatus(existingVersion!.id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.version(slug!, versionNumber) });
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      showSuccess('Статус изменен');
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

  const statusOptions: StatusOption[] = [
    { value: 'draft', label: statusConfig.labels.draft, tone: statusConfig.tones.draft },
    { value: 'active', label: statusConfig.labels.active, tone: statusConfig.tones.active },
    { value: 'archived', label: statusConfig.labels.archived, tone: statusConfig.tones.archived },
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Промпты', href: '/admin/prompts' },
    { label: prompt?.name || slug || '', href: `/admin/prompts/${slug}` },
    { label: isCreate ? 'Новая версия' : `Версия ${versionNumber}` },
  ];

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
    >
      <ContentGrid>
        {/* Template - 2/3 width */}
        <ContentBlock width="2/3" title="Template" icon="file-text">
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

        {/* Status - 1/3 width */}
        {!isCreate && existingVersion && (
          <StatusBadgeCard
            label="Статус"
            status={existingVersion.status}
            statusOptions={statusOptions}
            onChangeStatus={(status) => changeStatusMutation.mutate(status)}
            disabled={changeStatusMutation.isPending}
          />
        )}
      </ContentGrid>
    </EntityPage>
  );
}

export default PromptVersionPage;
