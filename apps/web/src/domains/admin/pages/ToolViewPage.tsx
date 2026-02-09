/**
 * ToolViewPage v2 - Tool container with 3 tabs:
 * 1. Обзор — info fields + current version card
 * 2. Версии — releases table (ToolRelease)
 * 3. Бэкенд-релизы — backend releases table (read-only)
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

type TabType = 'main' | 'releases' | 'backend-releases';

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

  const groupSlug = tool?.tool_group_slug;
  const backPath = groupSlug 
    ? `/admin/tools/groups/${groupSlug}` 
    : '/admin/tools';

  const toolFields: FieldDefinition[] = [
    { key: 'slug', label: 'Slug', type: 'text', disabled: true },
    { key: 'name', label: 'Название', type: 'text', disabled: true },
    { key: 'kind', label: 'Тип', type: 'text', disabled: true },
    { key: 'tags', label: 'Теги', type: 'text', disabled: true },
  ];

  const formData = tool ? {
    slug: tool.slug,
    name: tool.name,
    kind: KIND_LABELS[tool.kind] || tool.kind,
    tags: tool.tags?.join(', ') || '—',
  } : { slug: '', name: '', kind: '', tags: '' };

  const currentVer = tool?.current_version;

  const tabs = [
    { id: 'main', label: 'Обзор' },
    { id: 'releases', label: `Версии (${tool?.releases?.length || 0})` },
    { id: 'backend-releases', label: `Бэкенд (${tool?.backend_releases?.length || 0})` },
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инструменты', href: '/admin/tools' },
    ...(groupSlug ? [{ label: groupSlug, href: `/admin/tools/groups/${groupSlug}` }] : []),
    { label: tool?.name || toolSlug || 'Инструмент' },
  ];

  const handleReleaseClick = (release: ToolReleaseListItem) => {
    navigate(`/admin/tools/${toolSlug}/versions/${release.version}`);
  };

  const backendReleaseColumns: DataTableColumn<ToolBackendReleaseListItem>[] = [
    {
      key: 'version',
      label: 'ВЕРСИЯ',
      width: 120,
      render: (row) => <strong>{row.version}</strong>,
    },
    {
      key: 'description',
      label: 'ОПИСАНИЕ',
      render: (row) => (
        <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
          {row.description || '—'}
        </span>
      ),
    },
    {
      key: 'schema_hash',
      label: 'SCHEMA',
      width: 100,
      render: (row) => (
        <code style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
          {row.schema_hash ? row.schema_hash.slice(0, 8) : '—'}
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
        <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
          {new Date(row.synced_at).toLocaleString('ru')}
        </span>
      ),
    },
  ];

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
        <span style={{ color: 'var(--text-secondary)' }}>{row.backend_version || '—'}</span>
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
      key: 'current',
      label: 'ОСНОВНАЯ',
      width: 100,
      render: (row) => (
        tool?.current_version_id === row.id ? (
          <Badge tone="info" size="small">★ Основная</Badge>
        ) : null
      ),
    },
    {
      key: 'notes',
      label: 'ЗАМЕТКИ',
      render: (row) => (
        <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
          {row.notes || '—'}
        </span>
      ),
    },
    {
      key: 'created_at',
      label: 'СОЗДАНА',
      width: 140,
      render: (row) => (
        <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
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
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <Button
            variant="outline"
            size="small"
            onClick={() => rescanMutation.mutate()}
            disabled={rescanMutation.isPending}
          >
            {rescanMutation.isPending ? 'Синхронизация...' : 'Rescan Backend'}
          </Button>
        </div>
      }
    >
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab}>
        <TabPanel id="main" activeTab={activeTab}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <ContentBlock
              title="Основная информация"
              icon="tool"
              fields={toolFields}
              data={formData}
              headerActions={
                <Badge tone={KIND_TONES[tool?.kind || ''] || 'neutral'} size="small">
                  {KIND_LABELS[tool?.kind || ''] || tool?.kind || '—'}
                </Badge>
              }
            />

            <ContentBlock title="Текущая версия" icon="check-circle">
              {currentVer ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.875rem' }}>
                  <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    <strong>v{currentVer.version}</strong>
                    <Badge tone={STATUS_TONES[currentVer.status]} size="small">
                      {STATUS_LABELS[currentVer.status]}
                    </Badge>
                    {currentVer.backend_release && (
                      <span style={{ color: 'var(--text-secondary)' }}>
                        Бэкенд: {currentVer.backend_release.version}
                      </span>
                    )}
                  </div>
                  {currentVer.description_for_llm && (
                    <div>
                      <div style={{ fontWeight: 500, marginBottom: '0.25rem' }}>Описание для LLM:</div>
                      <div style={{ color: 'var(--text-secondary)' }}>{currentVer.description_for_llm}</div>
                    </div>
                  )}
                  {currentVer.notes && (
                    <div style={{ color: 'var(--text-secondary)' }}>
                      <em>{currentVer.notes}</em>
                    </div>
                  )}
                  <Button
                    variant="outline"
                    size="small"
                    onClick={() => navigate(`/admin/tools/${toolSlug}/versions/${currentVer.version}`)}
                    style={{ alignSelf: 'flex-start' }}
                  >
                    Открыть версию
                  </Button>
                </div>
              ) : (
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                  Текущая версия не установлена. Создайте и активируйте версию.
                </div>
              )}
            </ContentBlock>
          </div>
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

        <TabPanel id="backend-releases" activeTab={activeTab}>
          <DataTable
            columns={backendReleaseColumns}
            data={tool?.backend_releases || []}
            keyField="id"
            emptyText="Версии из кода ещё не синхронизированы. Нажмите 'Rescan Backend'."
          />
        </TabPanel>
      </Tabs>
    </EntityPage>
  );
}

export default ToolViewPage;
