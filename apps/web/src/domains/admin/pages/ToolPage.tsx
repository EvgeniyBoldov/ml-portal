/**
 * ToolViewPage - Tool container with versions using EntityTabsPage
 * 
 * Refactored to follow AgentEditorPage pattern with EntityTabsPage
 * Tool container: slug, name, description, kind, tags
 * Versions hold: releases with backend_version, status, notes
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { 
  toolReleasesApi, 
  toolReleasesKeys,
  type ToolReleaseListItem,
  type ToolBackendReleaseListItem,
} from '@/shared/api/toolReleases';
import { 
  EntityPageV2,
  Tab,
  type BreadcrumbItem, 
  type EntityPageMode,
} from '@/shared/ui/EntityPage/EntityPageV2';
import { 
  type FieldDefinition, 
  DataTable,
  type DataTableColumn,
  Badge,
  Button,
  ContentBlock,
  ShortVersionBlock,
} from '@/shared/ui';
import { getStatusProps } from '@/shared/lib/statusConfig';

const KIND_LABELS: Record<string, string> = {
  read: 'Read',
  write: 'Write',
  mixed: 'Mixed',
};

const KIND_TONES: Record<string, 'warn' | 'success' | 'info' | 'neutral'> = {
  read: 'info',
  write: 'warn',
  mixed: 'neutral',
};

export function ToolPage() {
  const { toolSlug } = useParams<{ toolSlug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = toolSlug === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isNew ? 'create' : isEditMode ? 'edit' : 'view';
  const [saving, setSaving] = useState(false);

  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
    kind: '',
    tags: '',
  });
  
  const { data: tool, isLoading } = useQuery({
    queryKey: toolReleasesKeys.toolDetail(toolSlug!),
    queryFn: () => toolReleasesApi.getTool(toolSlug!),
    enabled: !!toolSlug && !isNew,
  });

  useEffect(() => {
    if (tool) {
      setFormData({
        slug: tool.slug,
        name: tool.name,
        description: tool.description || '',
        kind: tool.kind,
        tags: tool.tags?.join(', ') || '',
      });
    }
  }, [tool]);

  const rescanMutation = useMutation({
    mutationFn: () => toolReleasesApi.rescanBackendReleases(toolSlug!),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.toolDetail(toolSlug!) });
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.backendReleases(toolSlug!) });
      const br = data.stats?.backend_releases || {};
      showSuccess(`Синхронизация: ${br.backend_releases_created || 0} создано, ${br.backend_releases_updated || 0} обновлено`);
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка синхронизации'),
  });

  const handleFieldChange = (key: string, value: string) => {
    setFormData((prev: typeof formData) => ({ ...prev, [key]: value }));
  };

  const handleEdit = () => {
    setSearchParams({ mode: 'edit' });
  };

  const handleCancel = () => {
    setSearchParams({});
    setFormData(tool ? {
      slug: tool.slug,
      name: tool.name,
      description: tool.description || '',
      kind: tool.kind,
      tags: tool.tags?.join(', ') || '',
    } : {
      slug: '',
      name: '',
      description: '',
      kind: '',
      tags: '',
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Tool editing logic would go here
      showSuccess('Инструмент сохранен');
      setSearchParams({});
    } catch (error) {
      showError('Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const containerFields: FieldDefinition[] = [
    { key: 'slug', label: 'Slug', type: 'text' },
    { key: 'name', label: 'Название', type: 'text' },
    { key: 'kind', label: 'Тип', type: 'text' },
    { key: 'tags', label: 'Теги', type: 'text' },
    { key: 'description', label: 'Описание', type: 'textarea', rows: 2 },
  ];

  const releaseColumns: DataTableColumn<ToolReleaseListItem>[] = [
    {
      key: 'version',
      label: 'Версия',
      render: (row) => <strong>v{row.version}</strong>,
    },
    {
      key: 'backend_version',
      label: 'Бэкенд',
      render: (row) => row.backend_version || '—',
    },
    {
      key: 'status',
      label: 'Статус',
      render: (row) => (
        <Badge tone={getStatusProps('version', row.status).tone} size="small">
          {getStatusProps('version', row.status).label}
        </Badge>
      ),
    },
    {
      key: 'current',
      label: 'Основная',
      render: (row) => (
        tool?.current_version_id === row.id ? (
          <Badge tone="info" size="small">★ Основная</Badge>
        ) : null
      ),
    },
    {
      key: 'created_at',
      label: 'Создана',
      render: (row) => new Date(row.created_at).toLocaleDateString('ru-RU'),
    },
  ];

  const backendColumns: DataTableColumn<ToolBackendReleaseListItem>[] = [
    {
      key: 'version',
      label: 'Версия',
      render: (row) => <strong>{row.version}</strong>,
    },
    {
      key: 'description',
      label: 'Описание',
      render: (row) => row.description || '—',
    },
    {
      key: 'schema_hash',
      label: 'Schema',
      render: (row) => row.schema_hash ? row.schema_hash.slice(0, 8) : '—',
    },
    {
      key: 'deprecated',
      label: 'Статус',
      render: (row) => (
        <Badge tone={row.deprecated ? 'warn' : 'success'} size="small">
          {row.deprecated ? 'Устарела' : 'Актуальна'}
        </Badge>
      ),
    },
    {
      key: 'synced_at',
      label: 'Синхронизировано',
      render: (row) => new Date(row.synced_at).toLocaleDateString('ru-RU'),
    },
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инструменты', href: '/admin/tools' },
    { label: tool?.name || 'Новый инструмент' },
  ];

  return (
    <EntityPageV2
      title={tool?.name || 'Новый инструмент'}
      mode={mode}
      breadcrumbs={breadcrumbs}
      loading={isLoading}
      saving={saving}
          >
      <Tab 
        title="Обзор" 
        layout="grid"
        actions={
          mode === 'view' ? [
            <Button key="edit" onClick={handleEdit}>
              Редактировать
            </Button>,
          ] : mode === 'edit' ? [
            <Button key="save" onClick={handleSave} disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </Button>,
            <Button key="cancel" variant="outline" onClick={handleCancel}>
              Отмена
            </Button>,
          ] : []
        }
      >
        <ContentBlock
          title="Основные сведения"
          icon="info"
          editable={mode === 'edit'}
          fields={containerFields}
          data={formData}
          onChange={handleFieldChange}
          headerActions={
            <Badge tone={KIND_TONES[tool?.kind || 'mixed'] || 'neutral'} size="small">
              {KIND_LABELS[tool?.kind || 'mixed'] || tool?.kind || '—'}
            </Badge>
          }
        />
        <ShortVersionBlock
          title="Основная версия"
          entityType="tool"
          version={
            tool?.releases?.find(r => r.id === tool?.recommended_release_id) || 
            tool?.releases?.[0] || 
            {
              version: 0,
              created_at: new Date().toISOString(),
              status: 'draft'
            }
          }
        >
          <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
            {tool?.releases?.length ? (
              <div>
                <div style={{ marginBottom: '0.5rem' }}>
                  Backend: {tool?.releases?.find(r => r.id === tool?.recommended_release_id)?.backend_version || tool?.releases?.[0]?.backend_version || '—'}
                </div>
                <div style={{ fontSize: '0.875rem' }}>
                  {tool?.releases?.find(r => r.id === tool?.recommended_release_id)?.description_for_llm || tool?.releases?.[0]?.description_for_llm || 'Нет описания'}
                </div>
              </div>
            ) : (
              <div>Нет версий</div>
            )}
          </div>
        </ShortVersionBlock>
      </Tab>
      
      <Tab 
        title="Версии" 
        layout="full" 
        badge={tool?.releases?.length || 0}
        actions={[
          <Button key="create" onClick={() => navigate(`/admin/tools/${toolSlug}/versions/new`)}>
            Создать версию
          </Button>,
          ...(tool?.releases?.some(r => r.status === 'draft') ? [
            <Button key="edit-bindings" variant="outline">
              Редактировать привязки
            </Button>,
          ] : []),
        ]}
      >
        <DataTable
          columns={releaseColumns}
          data={tool?.releases || []}
          keyField="id"
          onRowClick={(v: ToolReleaseListItem) => navigate(`/admin/tools/${toolSlug}/versions/${v.version}`)}
          emptyText="Нет версий. Нажмите 'Создать версию'."
        />
      </Tab>
      
      <Tab 
        title="Бэкенд" 
        layout="full" 
        badge={tool?.backend_releases?.length || 0}
        actions={[
          <Button 
            key="rescan"
            variant="outline"
            onClick={() => rescanMutation.mutate()}
            disabled={rescanMutation.isPending}
          >
            {rescanMutation.isPending ? 'Синхронизация...' : 'Rescan Backend'}
          </Button>,
        ]}
      >
        <DataTable
          columns={backendColumns}
          data={tool?.backend_releases || []}
          keyField="id"
          onRowClick={(row: ToolBackendReleaseListItem) =>
            navigate(`/admin/tools/${toolSlug}/backend/${row.version}`)
          }
          emptyText="Нет бэкенд-релизов. Нажмите 'Rescan Backend'."
        />
      </Tab>
    </EntityPageV2>
  );
}

export default ToolPage;
