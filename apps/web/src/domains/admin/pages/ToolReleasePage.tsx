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
  type ToolBackendReleaseDetail,
} from '@/shared/api/toolReleases';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, Badge, type FieldDefinition } from '@/shared/ui';
import { Select } from '@/shared/ui/Select/Select';
import { useVersionActions } from '@/shared/hooks/useVersionActions';

interface FormData {
  backend_release_id: string;
  description_for_llm: string;
  category: string;
  tags: string;
  field_hints: string;
  examples: string;
  return_summary: string;
  config: string;
  notes: string;
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

  const isCreate = !versionParam;
  const versionNumber = isCreate ? 0 : parseInt(versionParam || '0', 10);
  const isEditMode = searchParams.get('mode') === 'edit' || isCreate;
  const fromVersion = searchParams.get('from');
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const [formData, setFormData] = useState<FormData>({
    backend_release_id: '',
    description_for_llm: '',
    category: '',
    tags: '',
    field_hints: '{}',
    examples: '[]',
    return_summary: '',
    config: '{}',
    notes: '',
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

  // Load source release for duplication
  const fromVersionNumber = fromVersion ? parseInt(fromVersion, 10) : 0;
  const { data: sourceRelease } = useQuery({
    queryKey: toolReleasesKeys.releaseDetail(toolSlug!, fromVersionNumber),
    queryFn: () => toolReleasesApi.getRelease(toolSlug!, fromVersionNumber),
    enabled: isCreate && !!toolSlug && fromVersionNumber > 0,
  });

  // Sync form data
  useEffect(() => {
    if (isCreate && sourceRelease) {
      setFormData({
        backend_release_id: sourceRelease.backend_release_id || (tool?.backend_releases?.[0]?.id || ''),
        description_for_llm: sourceRelease.description_for_llm || '',
        category: sourceRelease.category || '',
        tags: sourceRelease.tags?.join(', ') || '',
        field_hints: JSON.stringify(sourceRelease.field_hints || {}, null, 2),
        examples: JSON.stringify(sourceRelease.examples || [], null, 2),
        return_summary: sourceRelease.return_summary || '',
        config: JSON.stringify(sourceRelease.config || {}, null, 2),
        notes: '',
      });
    } else if (isCreate && tool?.backend_releases?.length) {
      const latest = tool.backend_releases[0];
      setFormData({
        backend_release_id: latest.id,
        description_for_llm: '',
        category: '',
        tags: '',
        field_hints: '{}',
        examples: '[]',
        return_summary: '',
        config: '{}',
        notes: '',
      });
    } else if (existingRelease) {
      setFormData({
        backend_release_id: existingRelease.backend_release_id,
        description_for_llm: existingRelease.description_for_llm || '',
        category: existingRelease.category || '',
        tags: existingRelease.tags?.join(', ') || '',
        field_hints: JSON.stringify(existingRelease.field_hints || {}, null, 2),
        examples: JSON.stringify(existingRelease.examples || [], null, 2),
        return_summary: existingRelease.return_summary || '',
        config: JSON.stringify(existingRelease.config, null, 2),
        notes: existingRelease.notes || '',
      });
    }
  }, [existingRelease, isCreate, tool, sourceRelease]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: () => toolReleasesApi.createRelease(toolSlug!, {
      backend_release_id: formData.backend_release_id,
      from_release_id: sourceRelease?.id || undefined,
      description_for_llm: formData.description_for_llm || undefined,
      category: formData.category || undefined,
      tags: formData.tags ? formData.tags.split(',').map(t => t.trim()).filter(Boolean) : undefined,
      field_hints: JSON.parse(formData.field_hints || '{}'),
      examples: JSON.parse(formData.examples || '[]'),
      return_summary: formData.return_summary || undefined,
      config: JSON.parse(formData.config || '{}'),
      notes: formData.notes || undefined,
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
      description_for_llm: formData.description_for_llm || undefined,
      category: formData.category || undefined,
      tags: formData.tags ? formData.tags.split(',').map(t => t.trim()).filter(Boolean) : undefined,
      field_hints: JSON.parse(formData.field_hints || '{}'),
      examples: JSON.parse(formData.examples || '[]'),
      return_summary: formData.return_summary || undefined,
      config: JSON.parse(formData.config || '{}'),
      notes: formData.notes || undefined,
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
    mutationFn: () => toolReleasesApi.setCurrentVersion(toolSlug!, existingRelease!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.toolDetail(toolSlug!) });
      showSuccess('Релиз установлен как основной');
    },
    onError: (err: Error) => showError(err.message),
  });

  // Handlers
  const handleSave = async () => {
    // Validate JSON fields
    for (const [field, label] of [['config', 'Конфигурация'], ['field_hints', 'Field Hints'], ['examples', 'Examples']] as const) {
      try {
        JSON.parse(formData[field] || (field === 'examples' ? '[]' : '{}'));
      } catch {
        showError(`Некорректный JSON в поле "${label}"`);
        return;
      }
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

  const handleCancel = () => {
    if (mode === 'edit' && existingRelease) {
      setFormData({
        backend_release_id: existingRelease.backend_release_id,
        description_for_llm: existingRelease.description_for_llm || '',
        category: existingRelease.category || '',
        tags: existingRelease.tags?.join(', ') || '',
        field_hints: JSON.stringify(existingRelease.field_hints || {}, null, 2),
        examples: JSON.stringify(existingRelease.examples || [], null, 2),
        return_summary: existingRelease.return_summary || '',
        config: JSON.stringify(existingRelease.config, null, 2),
        notes: existingRelease.notes || '',
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

  // Field definitions
  const mainFields: FieldDefinition[] = [
    {
      key: 'description_for_llm',
      label: 'Описание для LLM',
      type: 'textarea',
      placeholder: 'Описание инструмента для языковой модели...',
      rows: 3,
    },
    {
      key: 'category',
      label: 'Категория',
      type: 'text',
      placeholder: 'search / create / update ...',
    },
    {
      key: 'tags',
      label: 'Теги',
      type: 'text',
      placeholder: 'rag, search, documents (через запятую)',
      description: 'Теги через запятую',
    },
    {
      key: 'return_summary',
      label: 'Описание возврата',
      type: 'textarea',
      placeholder: 'Что возвращает инструмент...',
      rows: 2,
    },
    {
      key: 'notes',
      label: 'Заметки',
      type: 'textarea',
      placeholder: 'Описание изменений в этом релизе...',
      rows: 2,
    },
  ];

  const jsonFields: FieldDefinition[] = [
    {
      key: 'field_hints',
      label: 'Field Hints (JSON)',
      type: 'textarea',
      placeholder: '{"query": "Поисковый запрос"}',
      rows: 4,
      description: 'Подсказки для полей входной схемы',
    },
    {
      key: 'examples',
      label: 'Examples (JSON)',
      type: 'textarea',
      placeholder: '[{"query": "пример запроса"}]',
      rows: 4,
      description: 'Примеры вызовов инструмента',
    },
    {
      key: 'config',
      label: 'Конфигурация (JSON)',
      type: 'textarea',
      placeholder: '{}',
      rows: 4,
      description: 'Дополнительные настройки (timeout, retries и т.д.)',
    },
  ];

  const breadcrumbs = [
    { label: 'Инструменты', href: '/admin/tools' },
    ...(tool?.tool_group_slug ? [{ label: tool.tool_group_slug, href: `/admin/tools/groups/${tool.tool_group_slug}` }] : []),
    { label: tool?.name || toolSlug || '', href: `/admin/tools/${toolSlug}` },
    { label: isCreate ? 'Новая версия' : `Версия v${versionNumber}` },
  ];

  // Check if this release is the current version
  const isRecommended = !!(tool?.current_version_id && existingRelease?.id && tool.current_version_id === existingRelease.id);

  const actionButtons = useVersionActions({
    status: existingRelease?.status,
    isRecommended,
    isCreate,
    callbacks: {
      onEdit: () => setSearchParams({ mode: 'edit' }),
      onActivate: () => activateMutation.mutate(),
      onDeactivate: () => archiveMutation.mutate(),
      onSetRecommended: () => setRecommendedMutation.mutate(),
      onDuplicate: () => navigate(`/admin/tools/${toolSlug}/versions/new?from=${versionNumber}`),
    },
    loading: {
      activate: activateMutation.isPending,
      deactivate: archiveMutation.isPending,
      setRecommended: setRecommendedMutation.isPending,
    },
  });

  // Backend release info block
  const selectedBackendRelease = tool?.backend_releases?.find(
    (br: ToolBackendReleaseListItem) => br.id === formData.backend_release_id
  );

  // Load full backend release detail (with input_schema/output_schema)
  // In view mode — from existingRelease.backend_release (already full)
  // In create mode — fetch separately by selected backend_release_id
  const { data: fetchedBackendRelease } = useQuery({
    queryKey: toolReleasesKeys.backendReleaseDetail(
      toolSlug!,
      selectedBackendRelease?.version || ''
    ),
    queryFn: () => toolReleasesApi.getBackendRelease(toolSlug!, selectedBackendRelease!.version),
    enabled: isCreate && !!toolSlug && !!selectedBackendRelease?.version,
  });

  const backendReleaseDetail: ToolBackendReleaseDetail | null =
    existingRelease?.backend_release ?? fetchedBackendRelease ?? null;

  return (
    <EntityPage
      mode={mode}
      entityName={isCreate ? 'Новый релиз' : `Релиз v${versionNumber}`}
      entityTypeLabel="релиза"
      backPath={`/admin/tools/${toolSlug}`}
      loading={isLoading}
      saving={saving}
      onSave={handleSave}
      onCancel={handleCancel}
      breadcrumbs={breadcrumbs}
      actionButtons={actionButtons}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <ContentBlock
          title="Основные настройки"
          editable={isEditable}
          fields={mainFields}
          data={formData}
          onChange={handleFieldChange}
          headerActions={
            <Badge tone={STATUS_TONES[isCreate ? 'draft' : (existingRelease?.status || 'draft')]} size="small">
              {STATUS_LABELS[isCreate ? 'draft' : (existingRelease?.status || 'draft')]}
            </Badge>
          }
        />

        <ContentBlock
          title="JSON-конфигурация"
          icon="code"
          editable={isEditable}
          fields={jsonFields}
          data={formData}
          onChange={handleFieldChange}
        />

        <ContentBlock title="Версия бэкенда" icon="code">
            {isEditable && isCreate ? (
              <div style={{ fontSize: '0.875rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                  Выберите версию бэкенда:
                </label>
                <Select
                  options={backendReleaseOptions}
                  value={formData.backend_release_id}
                  onChange={(val) => handleFieldChange('backend_release_id', val)}
                  placeholder="-- Выберите версию --"
                />
              </div>
            ) : selectedBackendRelease ? (
              <div style={{ fontSize: '0.875rem' }}>
                <div><strong>Версия:</strong> {selectedBackendRelease.version}</div>
                {selectedBackendRelease.description && (
                  <div style={{ marginTop: '0.5rem', color: 'var(--text-secondary)' }}>
                    {selectedBackendRelease.description}
                  </div>
                )}
                {selectedBackendRelease.deprecated && (
                  <div style={{ marginTop: '0.5rem', color: 'var(--status-warn)' }}>
                    Эта версия устарела
                  </div>
                )}
              </div>
            ) : (
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                Версия бэкенда не выбрана
              </p>
            )}
        </ContentBlock>

        {backendReleaseDetail && (
          <>
            <ContentBlock title="Мета-информация бэкенда" icon="info">
              <div style={{ fontSize: '0.875rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div><strong>Метод:</strong> <code>{backendReleaseDetail.method_name}</code></div>
                {backendReleaseDetail.schema_hash && (
                  <div><strong>Schema Hash:</strong> <code>{backendReleaseDetail.schema_hash.slice(0, 16)}...</code></div>
                )}
                {backendReleaseDetail.worker_build_id && (
                  <div><strong>Worker Build:</strong> <code>{backendReleaseDetail.worker_build_id}</code></div>
                )}
                {backendReleaseDetail.deprecation_message && (
                  <div style={{ color: 'var(--status-warn)' }}>
                    <strong>Deprecation:</strong> {backendReleaseDetail.deprecation_message}
                  </div>
                )}
                <div><strong>Синхронизировано:</strong> {new Date(backendReleaseDetail.synced_at).toLocaleString('ru')}</div>
              </div>
            </ContentBlock>

            <ContentBlock title="Input Schema" icon="code">
              <pre style={{
                fontSize: '0.8125rem',
                background: 'var(--bg-secondary)',
                padding: '1rem',
                borderRadius: '6px',
                overflow: 'auto',
                maxHeight: '400px',
                margin: 0,
                color: 'var(--text-primary)',
              }}>
                {JSON.stringify(backendReleaseDetail.input_schema, null, 2)}
              </pre>
            </ContentBlock>

            {backendReleaseDetail.output_schema && Object.keys(backendReleaseDetail.output_schema).length > 0 && (
              <ContentBlock title="Output Schema" icon="code">
                <pre style={{
                  fontSize: '0.8125rem',
                  background: 'var(--bg-secondary)',
                  padding: '1rem',
                  borderRadius: '6px',
                  overflow: 'auto',
                  maxHeight: '400px',
                  margin: 0,
                  color: 'var(--text-primary)',
                }}>
                  {JSON.stringify(backendReleaseDetail.output_schema, null, 2)}
                </pre>
              </ContentBlock>
            )}
          </>
        )}
      </div>
    </EntityPage>
  );
}

export default ToolReleasePage;
