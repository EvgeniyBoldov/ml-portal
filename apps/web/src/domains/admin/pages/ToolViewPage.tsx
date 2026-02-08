/**
 * ToolViewPage - View tool details with releases
 * 
 * Layout pattern: same as PromptEditorPage
 * - Split layout: info block left + status/release block right
 * - Tabs: Обзор | Версии бэкенда | Версии
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { 
  toolReleasesApi, 
  toolReleasesKeys,
  type ToolReleaseListItem,
  type ToolBackendReleaseListItem,
} from '@/shared/api/toolReleases';
import { EntityPage, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { ContentBlock, type FieldDefinition } from '@/shared/ui/ContentBlock';
import { Tabs, TabPanel } from '@/shared/ui/Tabs';
import { Badge, Button, DataTable, type DataTableColumn } from '@/shared/ui';

const TYPE_LABELS: Record<string, string> = {
  api: 'API',
  function: 'Функция',
  database: 'База данных',
  builtin: 'Встроенный',
};

const TYPE_TONES: Record<string, 'warn' | 'success' | 'info' | 'neutral'> = {
  api: 'info',
  function: 'success',
  database: 'warn',
  builtin: 'neutral',
};

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

type TabType = 'main' | 'backend-releases' | 'releases';

export function ToolViewPage() {
  const { toolSlug } = useParams<{ toolSlug: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabType>('main');
  const showSuccess = useSuccessToast();
  const showError = useErrorToast();
  
  const { data: tool, isLoading } = useQuery({
    queryKey: toolReleasesKeys.toolDetail(toolSlug!),
    queryFn: () => toolReleasesApi.getTool(toolSlug!),
    enabled: !!toolSlug,
  });

  // Rescan backend releases mutation
  const rescanMutation = useMutation({
    mutationFn: () => toolReleasesApi.rescanBackendReleases(toolSlug!),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.toolDetail(toolSlug!) });
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.backendReleases(toolSlug!) });
      const br = data.stats?.backend_releases || {};
      showSuccess(`Синхронизация завершена: ${br.backend_releases_created || 0} создано, ${br.backend_releases_updated || 0} обновлено`);
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка синхронизации'),
  });

  // Back path - navigate to group if available
  const groupSlug = tool?.tool_group_slug;
  const backPath = groupSlug 
    ? `/admin/tools/groups/${groupSlug}` 
    : '/admin/tools';

  // Field definitions (readonly)
  const toolFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug (ID)',
      type: 'text',
      disabled: true,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      disabled: true,
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      disabled: true,
      rows: 2,
    },
  ];

  const formData = tool ? {
    slug: tool.slug,
    name: tool.name,
    description: tool.description || '',
  } : { slug: '', name: '', description: '' };

  const tabs = [
    { id: 'main', label: 'Обзор' },
    { id: 'backend-releases', label: `Версии бэкенда (${tool?.backend_releases?.length || 0})` },
    { id: 'releases', label: `Версии (${tool?.releases?.length || 0})` },
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инструменты', href: '/admin/tools' },
    ...(groupSlug ? [{ label: groupSlug, href: `/admin/tools/groups/${groupSlug}` }] : []),
    { label: tool?.name || toolSlug || 'Инструмент' },
  ];

  const handleReleaseClick = (release: ToolReleaseListItem) => {
    navigate(`/admin/tools/${toolSlug}/versions/${release.version}`);
  };

  // DataTable columns for backend releases
  const backendReleaseColumns: DataTableColumn<ToolBackendReleaseListItem>[] = [
    {
      key: 'version',
      label: 'ВЕРСИЯ',
      width: 120,
      render: (row) => <strong>{row.version}</strong>,
    },
    {
      key: 'schema_hash',
      label: 'SCHEMA HASH',
      width: 120,
      render: (row) => (
        <code style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
          {row.schema_hash ? row.schema_hash.slice(0, 8) : '—'}
        </code>
      ),
    },
    {
      key: 'worker_build_id',
      label: 'BUILD ID',
      width: 120,
      render: (row) => (
        <code style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
          {row.worker_build_id ? row.worker_build_id.slice(0, 12) : '—'}
        </code>
      ),
    },
    {
      key: 'deprecated',
      label: 'СТАТУС',
      width: 100,
      render: (row) => (
        <Badge tone={row.deprecated ? 'warn' : 'success'} size="small">
          {row.deprecated ? 'Устарела' : 'Актуальна'}
        </Badge>
      ),
    },
    {
      key: 'synced_at',
      label: 'СИНХРОНИЗИРОВАНО',
      width: 160,
      render: (row) => (
        <span style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
          {new Date(row.synced_at).toLocaleString('ru')}
        </span>
      ),
    },
  ];

  // DataTable columns for releases
  const releaseColumns: DataTableColumn<ToolReleaseListItem>[] = [
    {
      key: 'version',
      label: 'ВЕРСИЯ',
      width: 80,
      render: (row) => <strong>v{row.version}</strong>,
    },
    {
      key: 'backend_version',
      label: 'БЭКЕНД',
      width: 100,
      render: (row) => (
        <span style={{ color: 'var(--muted)' }}>{row.backend_version || '—'}</span>
      ),
    },
    {
      key: 'status',
      label: 'СТАТУС',
      width: 100,
      render: (row) => (
        <Badge tone={STATUS_TONES[row.status]} size="small">
          {STATUS_LABELS[row.status]}
        </Badge>
      ),
    },
    {
      key: 'expected_schema_hash',
      label: 'SCHEMA',
      width: 100,
      render: (row) => (
        <code style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
          {row.expected_schema_hash ? row.expected_schema_hash.slice(0, 8) : '—'}
        </code>
      ),
    },
    {
      key: 'recommended',
      label: 'ОСНОВНАЯ',
      width: 100,
      render: (row) => (
        tool?.recommended_release_id === row.id ? (
          <Badge tone="info" size="small">★ Основная</Badge>
        ) : null
      ),
    },
    {
      key: 'created_at',
      label: 'СОЗДАНА',
      width: 140,
      render: (row) => (
        <span style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
          {new Date(row.created_at).toLocaleString('ru')}
        </span>
      ),
    },
  ];

  return (
    <EntityPage
      mode="view"
      entityName={tool?.name || toolSlug || 'Инструмент'}
      entityTypeLabel="инструмента"
      backPath={backPath}
      breadcrumbs={breadcrumbs}
      loading={isLoading}
      showDelete={false}
      headerActions={
        <Button
          variant="outline"
          size="small"
          onClick={() => rescanMutation.mutate()}
          disabled={rescanMutation.isPending}
        >
          {rescanMutation.isPending ? 'Синхронизация...' : 'Rescan Backend'}
        </Button>
      }
    >
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab}>
        <TabPanel id="main" activeTab={activeTab}>
          <ContentBlock
            title="Основная информация"
            fields={toolFields}
            data={formData}
            headerActions={
              <Badge tone={tool?.is_active ? 'success' : 'neutral'} size="small">
                {tool?.is_active ? 'Активен' : 'Неактивен'}
              </Badge>
            }
          />
        </TabPanel>

        <TabPanel id="backend-releases" activeTab={activeTab}>
          <DataTable
            columns={backendReleaseColumns}
            data={tool?.backend_releases || []}
            keyField="id"
            emptyText="Версии из кода ещё не синхронизированы"
          />
        </TabPanel>

        <TabPanel id="releases" activeTab={activeTab}>
          <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'flex-end' }}>
            <Button 
              variant="primary"
              onClick={() => navigate(`/admin/tools/${toolSlug}/versions/new`)}
            >
              Создать версию
            </Button>
          </div>
          <DataTable
            columns={releaseColumns}
            data={tool?.releases || []}
            keyField="id"
            emptyText="Версии ещё не созданы. Создайте первую версию для использования инструмента агентами."
            onRowClick={handleReleaseClick}
          />
        </TabPanel>
      </Tabs>
    </EntityPage>
  );
}

export default ToolViewPage;
