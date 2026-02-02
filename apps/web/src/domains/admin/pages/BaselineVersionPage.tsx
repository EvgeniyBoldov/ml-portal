/**
 * BaselineVersionPage - View/Edit/Create baseline version
 * 
 * Routes:
 * - /admin/baselines/:slug/versions/new - Create new version
 * - /admin/baselines/:slug/versions/:version - View version
 * - /admin/baselines/:slug/versions/:version?mode=edit - Edit version (only draft)
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { baselinesApi, type BaselineVersionInfo } from '@/shared/api/baselines';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, StatusBadgeCard, type FieldDefinition, type StatusOption } from '@/shared/ui';
import Button from '@/shared/ui/Button';
import styles from './PromptVersionPage.module.css';

interface FormData {
  template: string;
}

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

  const [formData, setFormData] = useState<FormData>({
    template: '',
  });
  const [saving, setSaving] = useState(false);

  // Load baseline for breadcrumbs and to find version ID
  const { data: baseline, isLoading: baselineLoading } = useQuery({
    queryKey: qk.baselines.detail(slug!),
    queryFn: () => baselinesApi.get(slug!),
    enabled: !!slug,
  });

  // Find the version ID from baseline versions by version number
  const versionId = baseline?.versions?.find(v => v.version === versionNumber)?.id;

  // Load existing version (only if we have versionId)
  const { data: existingVersion, isLoading: versionLoading } = useQuery({
    queryKey: qk.baselines.version(slug!, versionNumber),
    queryFn: () => baselinesApi.getVersion(slug!, versionId!),
    enabled: !isCreate && !!slug && !!versionId,
  });

  const isLoading = baselineLoading || versionLoading;

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
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      showSuccess('Версия создана');
      navigate(`/admin/baselines/${slug}/versions/${created.version}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: (data: { template: string }) => baselinesApi.updateVersion(slug!, existingVersion!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      showSuccess('Версия обновлена');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const activateMutation = useMutation({
    mutationFn: () => baselinesApi.activateVersion(slug!, existingVersion!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      showSuccess('Версия активирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const archiveMutation = useMutation({
    mutationFn: () => baselinesApi.archiveVersion(slug!, existingVersion!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      showSuccess('Версия архивирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const handleSave = async () => {
    setSaving(true);
    try {
      if (mode === 'create') {
        await createMutation.mutateAsync({ template: formData.template });
      } else {
        await updateMutation.mutateAsync({ template: formData.template });
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => {
    if (existingVersion?.status !== 'draft') {
      showError('Только черновики можно редактировать');
      return;
    }
    setSearchParams({ mode: 'edit' });
  };

  const handleCancel = () => {
    if (mode === 'edit' && existingVersion) {
      setFormData({ template: existingVersion.template });
      setSearchParams({});
    } else if (mode === 'create') {
      navigate(`/admin/baselines/${slug}`);
    }
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  // Status options
  const statusOptions: StatusOption[] = [
    { value: 'draft', label: 'Черновик', tone: 'warn' },
    { value: 'active', label: 'Активна', tone: 'success' },
    { value: 'archived', label: 'Архив', tone: 'neutral' },
  ];

  // Field definitions
  const templateFields: FieldDefinition[] = [
    {
      key: 'template',
      label: 'Текст бейслайна',
      type: 'textarea',
      required: true,
      placeholder: 'Введите текст бейслайна...',
      rows: 16,
      description: 'Ограничения и правила для агента',
    },
  ];

  const breadcrumbs = [
    { label: 'Бейслайны', href: '/admin/baselines' },
    { label: baseline?.name || slug || '', href: `/admin/baselines/${slug}` },
    { label: isCreate ? 'Новая версия' : `Версия ${versionNumber}` },
  ];

  // Render header actions
  const renderHeaderActions = () => {
    if (isCreate) return null;
    return (
      <>
        {existingVersion?.status === 'draft' && (
          <>
            <Button variant="primary" onClick={() => activateMutation.mutate()} disabled={activateMutation.isPending}>
              Активировать
            </Button>
            <Button variant="secondary" onClick={() => archiveMutation.mutate()} disabled={archiveMutation.isPending}>
              Архивировать
            </Button>
          </>
        )}
        {existingVersion?.status === 'active' && (
          <Button variant="secondary" onClick={() => archiveMutation.mutate()} disabled={archiveMutation.isPending}>
            Архивировать
          </Button>
        )}
        {existingVersion?.status === 'archived' && (
          <Button variant="primary" onClick={() => activateMutation.mutate()} disabled={activateMutation.isPending}>
            Активировать
          </Button>
        )}
        <Button variant="secondary" onClick={() => navigate(`/admin/baselines/${slug}/versions/new`)}>
          Новая версия
        </Button>
      </>
    );
  };

  return (
    <EntityPage
      mode={mode}
      entityName={isCreate ? 'Новая версия' : `Версия ${versionNumber}`}
      entityTypeLabel="версии"
      backPath={`/admin/baselines/${slug}`}
      loading={isLoading}
      saving={saving}
      onEdit={existingVersion?.status === 'draft' ? handleEdit : undefined}
      onSave={handleSave}
      onCancel={handleCancel}
      breadcrumbs={breadcrumbs}
      headerActions={renderHeaderActions()}
    >
      <ContentGrid>
        {/* Left column: Template - 2/3 */}
        <ContentBlock
          width="2/3"
          title="Текст бейслайна"
          editable={isEditable}
          fields={templateFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Right column: Status - 1/3 */}
        <StatusBadgeCard
          label="Статус"
          status={isCreate ? 'draft' : (existingVersion?.status || 'draft')}
          statusOptions={statusOptions}
          editable={false}
          width="1/3"
        />
      </ContentGrid>
    </EntityPage>
  );
}

export default BaselineVersionPage;
