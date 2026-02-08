/**
 * BaselineVersionPage - View/Edit/Create baseline version
 * 
 * REFACTORED: Simplified with shared components
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { baselinesApi, type BaselineVersion } from '@/shared/api/baselines';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, ContentBlock, Textarea, Badge, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui';
import { useVersionActions } from '@/shared/hooks/useVersionActions';

export function BaselineVersionPage() {
  const { slug, version: versionParam } = useParams<{ slug: string; version: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isCreate = !versionParam;
  const versionNumber = isCreate ? 0 : parseInt(versionParam, 10);
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const [formData, setFormData] = useState({ template: '' });
  const [saving, setSaving] = useState(false);

  // Load baseline for breadcrumbs
  const { data: baseline } = useQuery({
    queryKey: qk.baselines.detail(slug!),
    queryFn: () => baselinesApi.get(slug!),
    enabled: !!slug,
  });

  // Load existing version
  const { data: existingVersion, isLoading } = useQuery({
    queryKey: ['baselines', slug, 'versions', versionNumber],
    queryFn: () => baselinesApi.getVersion(slug!, String(versionNumber)),
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
    mutationFn: (data: { template: string }) => baselinesApi.createVersion(slug!, data),
    onSuccess: (created: BaselineVersion) => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      showSuccess('Версия создана');
      navigate(`/admin/baselines/${slug}/versions/${created.version}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: (data: { template: string }) => baselinesApi.updateVersion(existingVersion!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['baselines', slug, 'versions', versionNumber] });
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      showSuccess('Версия обновлена');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const activateMutation = useMutation({
    mutationFn: () => baselinesApi.activateVersion(existingVersion!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: ['baselines', slug, 'versions', versionNumber] });
      showSuccess('Версия активирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deactivateMutation = useMutation({
    mutationFn: () => baselinesApi.archiveVersion(existingVersion!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: ['baselines', slug, 'versions', versionNumber] });
      showSuccess('Версия архивирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const setRecommendedMutation = useMutation({
    mutationFn: () => baselinesApi.setRecommendedVersion(slug!, existingVersion!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
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
      navigate(`/admin/baselines/${slug}`);
    } else {
      if (existingVersion) {
        setFormData({ template: existingVersion.template });
      }
      setSearchParams({});
    }
  };

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Бейслайны', href: '/admin/baselines' },
    { label: baseline?.name || slug || '', href: `/admin/baselines/${slug}` },
    { label: isCreate ? 'Новая версия' : `Версия ${versionNumber}` },
  ];

  const isRecommended = !!(baseline?.recommended_version?.id && existingVersion?.id && baseline.recommended_version.id === existingVersion.id);

  const actionButtons = useVersionActions({
    status: existingVersion?.status,
    isRecommended,
    isCreate,
    callbacks: {
      onEdit: () => setSearchParams({ mode: 'edit' }),
      onActivate: () => activateMutation.mutate(),
      onDeactivate: () => deactivateMutation.mutate(),
      onSetRecommended: () => setRecommendedMutation.mutate(),
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
      backPath={`/admin/baselines/${slug}`}
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

export default BaselineVersionPage;
