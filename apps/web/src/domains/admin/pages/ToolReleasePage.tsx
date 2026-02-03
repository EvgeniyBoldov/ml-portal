/**
 * ToolReleasePage - View/Edit/Create tool version
 * 
 * Routes:
 * - /admin/tools/:toolSlug/versions/new - Create new version
 * - /admin/tools/:toolSlug/versions/:version - View version
 * - /admin/tools/:toolSlug/versions/:version?mode=edit - Edit version (only draft)
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  toolReleasesApi, 
  toolReleasesKeys,
  type ToolReleaseResponse,
  type ToolBackendReleaseListItem,
} from '@/shared/api/toolReleases';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, StatusBadgeCard, type FieldDefinition, type StatusOption } from '@/shared/ui';
import Button from '@/shared/ui/Button';

interface FormData {
  backend_release_id: string;
  notes: string;
  config: string;
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

export function ToolReleasePage() {
  const { toolSlug, version: versionParam } = useParams<{ toolSlug: string; version: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isCreate = versionParam === 'new';
  const versionNumber = isCreate ? 0 : parseInt(versionParam || '0', 10);
  const isEditMode = searchParams.get('mode') === 'edit' || isCreate;
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const [formData, setFormData] = useState<FormData>({
    backend_release_id: '',
    notes: '',
    config: '{}',
  });
  const [saving, setSaving] = useState(false);

  // Load tool details
  const { data: tool, isLoading: toolLoading } = useQuery({
    queryKey: toolReleasesKeys.toolDetail(toolSlug!),
    queryFn: () => toolReleasesApi.getTool(toolSlug!),
    enabled: !!toolSlug,
  });

  // Load existing release
  const { data: existingRelease, isLoading: releaseLoading } = useQuery({
    queryKey: toolReleasesKeys.releaseDetail(toolSlug!, versionNumber),
    queryFn: () => toolReleasesApi.getRelease(toolSlug!, versionNumber),
    enabled: !isCreate && !!toolSlug && versionNumber > 0,
  });

  const isLoading = toolLoading || releaseLoading;

  // Sync form data
  useEffect(() => {
    if (isCreate && tool?.backend_releases?.length) {
      // Default to latest backend release
      const latest = tool.backend_releases[0];
      setFormData({
        backend_release_id: latest.id,
        notes: '',
        config: '{}',
      });
    } else if (existingRelease) {
      setFormData({
        backend_release_id: existingRelease.backend_release_id,
        notes: existingRelease.notes || '',
        config: JSON.stringify(existingRelease.config, null, 2),
      });
    }
  }, [existingRelease, isCreate, tool]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: () => toolReleasesApi.createRelease(toolSlug!, {
      backend_release_id: formData.backend_release_id,
      notes: formData.notes || undefined,
      config: JSON.parse(formData.config || '{}'),
    }),
    onSuccess: (created: ToolReleaseResponse) => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.toolDetail(toolSlug!) });
      showSuccess('Релиз создан');
      navigate(`/admin/tools/${toolSlug}/versions/${created.version}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: () => toolReleasesApi.updateRelease(toolSlug!, versionNumber, {
      backend_release_id: formData.backend_release_id,
      notes: formData.notes || undefined,
      config: JSON.parse(formData.config || '{}'),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.toolDetail(toolSlug!) });
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.releaseDetail(toolSlug!, versionNumber) });
      showSuccess('Релиз обновлён');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const activateMutation = useMutation({
    mutationFn: () => toolReleasesApi.activateRelease(toolSlug!, versionNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.toolDetail(toolSlug!) });
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.releaseDetail(toolSlug!, versionNumber) });
      showSuccess('Релиз активирован');
    },
    onError: (err: Error) => showError(err.message),
  });

  const archiveMutation = useMutation({
    mutationFn: () => toolReleasesApi.archiveRelease(toolSlug!, versionNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.toolDetail(toolSlug!) });
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.releaseDetail(toolSlug!, versionNumber) });
      showSuccess('Релиз архивирован');
    },
    onError: (err: Error) => showError(err.message),
  });

  const setRecommendedMutation = useMutation({
    mutationFn: () => toolReleasesApi.setRecommendedRelease(toolSlug!, existingRelease!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.toolDetail(toolSlug!) });
      showSuccess('Релиз установлен как основной');
    },
    onError: (err: Error) => showError(err.message),
  });

  // Handlers
  const handleSave = async () => {
    // Validate JSON
    try {
      JSON.parse(formData.config || '{}');
    } catch {
      showError('Некорректный JSON в конфигурации');
      return;
    }

    setSaving(true);
    try {
      if (mode === 'create') {
        await createMutation.mutateAsync();
      } else {
        await updateMutation.mutateAsync();
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => {
    if (existingRelease?.status !== 'draft') {
      showError('Только черновики можно редактировать');
      return;
    }
    setSearchParams({ mode: 'edit' });
  };

  const handleCancel = () => {
    if (mode === 'edit' && existingRelease) {
      setFormData({
        backend_release_id: existingRelease.backend_release_id,
        notes: existingRelease.notes || '',
        config: JSON.stringify(existingRelease.config, null, 2),
      });
      setSearchParams({});
    } else if (mode === 'create') {
      navigate(`/admin/tools/${toolSlug}`);
    }
  };

  const handleFieldChange = (key: string, value: string) => {
    setFormData((prev: FormData) => ({ ...prev, [key]: value }));
  };

  // Backend release options for select
  const backendReleaseOptions = (tool?.backend_releases || []).map((br: ToolBackendReleaseListItem) => ({
    value: br.id,
    label: `${br.version}${br.deprecated ? ' (deprecated)' : ''}`,
  }));

  // Status options
  const statusOptions: StatusOption[] = [
    { value: 'draft', label: 'Черновик', tone: 'warn' },
    { value: 'active', label: 'Активна', tone: 'success' },
    { value: 'archived', label: 'Архив', tone: 'neutral' },
  ];

  // Field definitions (без backend_release_id - он в отдельном read-only блоке)
  const releaseFields: FieldDefinition[] = [
    {
      key: 'notes',
      label: 'Заметки',
      type: 'textarea',
      placeholder: 'Описание изменений в этом релизе...',
      rows: 3,
    },
    {
      key: 'config',
      label: 'Конфигурация (JSON)',
      type: 'textarea',
      placeholder: '{}',
      rows: 6,
      description: 'Дополнительные настройки (timeout, retries и т.д.)',
    },
  ];

  const breadcrumbs = [
    { label: 'Инструменты', href: '/admin/tools' },
    ...(tool?.tool_group_slug ? [{ label: tool.tool_group_slug, href: `/admin/tools/groups/${tool.tool_group_slug}` }] : []),
    { label: tool?.name || toolSlug || '', href: `/admin/tools/${toolSlug}` },
    { label: isCreate ? 'Новая версия' : `Версия v${versionNumber}` },
  ];

  // Check if this release is the recommended one
  const isRecommended = tool?.recommended_release_id === existingRelease?.id;

  // Render header actions
  const renderHeaderActions = () => {
    if (isCreate) return null;
    return (
      <>
        {existingRelease?.status === 'draft' && (
          <Button variant="primary" onClick={() => activateMutation.mutate()} disabled={activateMutation.isPending}>
            Активировать
          </Button>
        )}
        {existingRelease?.status === 'active' && (
          <>
            {!isRecommended && (
              <Button variant="primary" onClick={() => setRecommendedMutation.mutate()} disabled={setRecommendedMutation.isPending}>
                Сделать основным
              </Button>
            )}
            <Button variant="secondary" onClick={() => archiveMutation.mutate()} disabled={archiveMutation.isPending}>
              Архивировать
            </Button>
          </>
        )}
        <Button variant="secondary" onClick={() => navigate(`/admin/tools/${toolSlug}/releases/new`)}>
          Новый релиз
        </Button>
      </>
    );
  };

  // Backend release info block
  const selectedBackendRelease = tool?.backend_releases?.find(
    (br: ToolBackendReleaseListItem) => br.id === formData.backend_release_id
  );

  return (
    <EntityPage
      mode={mode}
      entityName={isCreate ? 'Новый релиз' : `Релиз v${versionNumber}`}
      entityTypeLabel="релиза"
      backPath={`/admin/tools/${toolSlug}`}
      loading={isLoading}
      saving={saving}
      onEdit={existingRelease?.status === 'draft' ? handleEdit : undefined}
      onSave={handleSave}
      onCancel={handleCancel}
      breadcrumbs={breadcrumbs}
      headerActions={renderHeaderActions()}
    >
      <ContentGrid>
        {/* Left column: Release config - 2/3 */}
        <ContentBlock
          width="2/3"
          title="Настройки релиза"
          editable={isEditable}
          fields={releaseFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Right column: Status + Backend info - 1/3 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <StatusBadgeCard
            label="Статус"
            status={isCreate ? 'draft' : (existingRelease?.status || 'draft')}
            statusOptions={statusOptions}
            editable={false}
            width="full"
          />
          
          {/* Backend version selection - read-only block */}
          <ContentBlock
            width="full"
            title="Версия бэкенда"
            icon="code"
          >
            {isEditable && isCreate ? (
              <div style={{ fontSize: '0.875rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                  Выберите версию бэкенда:
                </label>
                <select
                  value={formData.backend_release_id}
                  onChange={(e) => handleFieldChange('backend_release_id', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.5rem',
                    borderRadius: '4px',
                    border: '1px solid var(--color-border)',
                    fontSize: '0.875rem',
                  }}
                >
                  <option value="">-- Выберите версию --</option>
                  {backendReleaseOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            ) : selectedBackendRelease ? (
              <div style={{ fontSize: '0.875rem' }}>
                <div><strong>Версия:</strong> {selectedBackendRelease.version}</div>
                {selectedBackendRelease.description && (
                  <div style={{ marginTop: '0.5rem', color: 'var(--color-text-muted)' }}>
                    {selectedBackendRelease.description}
                  </div>
                )}
                {selectedBackendRelease.deprecated && (
                  <div style={{ marginTop: '0.5rem', color: 'var(--color-warning)' }}>
                    ⚠️ Эта версия устарела
                  </div>
                )}
              </div>
            ) : (
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
                Версия бэкенда не выбрана
              </p>
            )}
          </ContentBlock>

          {isRecommended && (
            <ContentBlock width="full" title="Основной релиз" icon="star">
              <div style={{ fontSize: '0.875rem', color: 'var(--color-success)' }}>
                ✓ Этот релиз используется агентами по умолчанию
              </div>
            </ContentBlock>
          )}
        </div>
      </ContentGrid>
    </EntityPage>
  );
}

export default ToolReleasePage;
