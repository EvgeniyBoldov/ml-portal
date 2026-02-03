/**
 * ToolViewPage - View tool details with releases
 * 
 * Layout with tabs:
 * - Обзор: Tool info + status + recommended release
 * - Версии бэкенда: Versions from code (read-only)
 * - Версии: Versions for agents (CRUD)
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
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';
import { Tabs, TabPanel } from '@/shared/ui/Tabs';
import { Badge, Button, DataTable, StatusBadgeCard, type DataTableColumn } from '@/shared/ui';

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
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.toolDetail(toolSlug!) });
      showSuccess(`Синхронизация завершена: ${data.stats.created} создано, ${data.stats.updated} обновлено`);
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка синхронизации'),
  });

  // Back path - navigate to group if available (using slug)
  const groupSlug = tool?.tool_group_slug;
  const backPath = groupSlug 
    ? `/admin/tools/groups/${groupSlug}` 
    : '/admin/tools';

  // Field definitions (readonly)
  const toolFields: FieldDefinition[] = [
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      disabled: true,
    },
    {
      key: 'slug',
      label: 'Slug (ID)',
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

  // Breadcrumbs
  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инструменты', href: '/admin/tools' },
    ...(groupSlug ? [{ label: groupSlug, href: `/admin/tools/groups/${groupSlug}` }] : []),
    { label: tool?.name || 'Инструмент' },
  ];

  const handleReleaseClick = (release: ToolReleaseListItem) => {
    navigate(`/admin/tools/${toolSlug}/versions/${release.version}`);
  };

  // DataTable columns for backend releases
  const backendReleaseColumns: DataTableColumn<ToolBackendReleaseListItem>[] = [
    {
      key: 'version',
      label: 'ВЕРСИЯ',
      width: 150,
      render: (row) => <strong>{row.version}</strong>,
    },
    {
      key: 'description',
      label: 'ОПИСАНИЕ',
      render: (row) => (
        <span style={{ color: 'var(--color-text-muted)' }}>{row.description || '—'}</span>
      ),
    },
    {
      key: 'deprecated',
      label: 'СТАТУС',
      width: 120,
      render: (row) => (
        <Badge tone={row.deprecated ? 'warn' : 'success'} size="small">
          {row.deprecated ? 'Устарела' : 'Актуальна'}
        </Badge>
      ),
    },
    {
      key: 'synced_at',
      label: 'СИНХРОНИЗИРОВАНО',
      width: 180,
      render: (row) => (
        <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
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
      width: 100,
      render: (row) => <strong>v{row.version}</strong>,
    },
    {
      key: 'backend_version',
      label: 'БЭКЕНД',
      width: 120,
      render: (row) => (
        <span style={{ color: 'var(--color-text-muted)' }}>{row.backend_version || '—'}</span>
      ),
    },
    {
      key: 'status',
      label: 'СТАТУС',
      width: 120,
      render: (row) => (
        <Badge tone={STATUS_TONES[row.status]} size="small">
          {STATUS_LABELS[row.status]}
        </Badge>
      ),
    },
    {
      key: 'recommended',
      label: 'ОСНОВНАЯ',
      width: 120,
      render: (row) => (
        tool?.recommended_release_id === row.id ? (
          <Badge tone="info" size="small">★ Основная</Badge>
        ) : null
      ),
    },
    {
      key: 'created_at',
      label: 'СОЗДАНА',
      width: 150,
      render: (row) => (
        <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
          {new Date(row.created_at).toLocaleString('ru')}
        </span>
      ),
    },
  ];

  return (
    <EntityPage
      mode="view"
      entityName={tool?.name || 'Инструмент'}
      entityTypeLabel="инструмента"
      backPath={backPath}
      breadcrumbs={breadcrumbs}
      loading={isLoading}
      showDelete={false}
      actions={[
        {
          label: 'Редактировать',
          icon: 'edit',
          onClick: () => navigate(`/admin/tools/${toolSlug}/edit`),
        },
      ]}
      headerActions={
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={() => rescanMutation.mutate()}
            disabled={rescanMutation.isPending}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '4px',
              border: '1px solid var(--color-border)',
              background: 'var(--color-bg)',
              color: 'var(--color-text)',
              cursor: rescanMutation.isPending ? 'not-allowed' : 'pointer',
              opacity: rescanMutation.isPending ? 0.6 : 1,
              fontSize: '0.875rem',
              fontWeight: 500,
            }}
          >
            {rescanMutation.isPending ? 'Синхронизация...' : 'Rescan Backend'}
          </button>
        </div>
      }
    >
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab}>
        <TabPanel id="main" activeTab={activeTab}>
          <ContentGrid>
            <ContentBlock
              width="2/3"
              title="Информация об инструменте"
              icon="tool"
              fields={toolFields}
              data={formData}
            />
            <StatusBadgeCard
              label="Статус"
              status={tool?.is_active ? 'active' : 'inactive'}
              statusOptions={[
                { value: 'active', label: 'Активен', tone: 'success' },
                { value: 'inactive', label: 'Неактивен', tone: 'neutral' },
              ]}
              editable={false}
              width="1/3"
            />
          </ContentGrid>
          
          <ContentGrid>
            <ContentBlock
              width="1/3"
              title="Тип инструмента"
              icon="settings"
            >
              {tool && (
                <Badge tone={TYPE_TONES[tool.type] || 'neutral'} size="large">
                  {TYPE_LABELS[tool.type] || tool.type}
                </Badge>
              )}
            </ContentBlock>

            <ContentBlock
              width="2/3"
              title="Основной релиз"
              icon="star"
            >
              {tool?.recommended_release ? (
                <div style={{ fontSize: '0.875rem' }}>
                  <div style={{ marginBottom: '0.5rem' }}>
                    <strong>Версия:</strong> v{tool.recommended_release.version}
                  </div>
                  <div style={{ marginBottom: '0.5rem' }}>
                    <strong>Бэкенд:</strong> {tool.recommended_release.backend_release?.version || '—'}
                  </div>
                  <Badge tone={STATUS_TONES[tool.recommended_release.status]}>
                    {STATUS_LABELS[tool.recommended_release.status]}
                  </Badge>
                  <Button 
                    variant="ghost" 
                    size="small"
                    style={{ marginLeft: '1rem' }}
                    onClick={() => handleReleaseClick(tool.recommended_release as ToolReleaseListItem)}
                  >
                    Открыть →
                  </Button>
                </div>
              ) : (
                <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
                  Основной релиз не выбран. Создайте и активируйте версию, затем установите её как основную.
                </p>
              )}
            </ContentBlock>
          </ContentGrid>
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
