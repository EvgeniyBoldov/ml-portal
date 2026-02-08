/**
 * ToolGroupViewPage - View/Edit tool group with tabs
 * 
 * Layout pattern: same as PromptEditorPage
 * - Split layout: info block left + status block right
 * - Tabs: Обзор | Инструменты | Инстансы
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  toolReleasesApi, 
  toolReleasesKeys,
  type ToolListItem,
} from '@/shared/api/toolReleases';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, type FieldDefinition } from '@/shared/ui/ContentBlock';
import { Tabs, TabPanel } from '@/shared/ui/Tabs';
import { Badge, Button, DataTable, type DataTableColumn, type BreadcrumbItem } from '@/shared/ui';

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

type TabType = 'main' | 'tools' | 'instances';

export function ToolGroupViewPage() {
  const { groupSlug } = useParams<{ groupSlug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [activeTab, setActiveTab] = useState<TabType>('main');
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit';

  // Form state
  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
  });
  const [saving, setSaving] = useState(false);

  // Load group with tools
  const { data: group, isLoading: groupLoading } = useQuery({
    queryKey: toolReleasesKeys.groupDetail(groupSlug!),
    queryFn: () => toolReleasesApi.getGroup(groupSlug!),
    enabled: !!groupSlug,
  });

  // Sync form data
  useEffect(() => {
    if (group) {
      setFormData({
        slug: group.slug,
        name: group.name,
        description: group.description || '',
      });
    }
  }, [group]);

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: () => toolReleasesApi.updateGroup(groupSlug!, {
      name: formData.name,
      description: formData.description,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.groupDetail(groupSlug!) });
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.groupsList() });
      showSuccess('Группа обновлена');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка обновления'),
  });

  // Rescan mutation
  const rescanMutation = useMutation({
    mutationFn: () => toolReleasesApi.rescanGroupTools(groupSlug!),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.groupDetail(groupSlug!) });
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.groupsList() });
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.tools() });
      const t = data.stats?.tools || {};
      const br = data.stats?.backend_releases || {};
      showSuccess(`Синхронизация: ${t.created || 0} тулзов создано, ${br.backend_releases_created || 0} версий создано`);
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка синхронизации'),
  });

  // Handlers
  const handleSave = async () => {
    setSaving(true);
    try {
      await updateMutation.mutateAsync();
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (group) {
      setFormData({
        slug: group.slug,
        name: group.name,
        description: group.description || '',
      });
    }
    setSearchParams({});
  };

  const handleFieldChange = (key: string, value: string) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  const handleToolClick = (tool: ToolListItem) => {
    navigate(`/admin/tools/${tool.slug}`);
  };

  // Field definitions
  const groupFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug (ID)',
      type: 'text',
      disabled: true,
      description: 'Уникальный идентификатор (создаётся автоматически)',
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'RAG',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Описание группы инструментов...',
      rows: 2,
    },
  ];

  const tabs = [
    { id: 'main', label: 'Обзор' },
    { id: 'tools', label: `Инструменты (${group?.tools?.length || 0})` },
    { id: 'instances', label: `Инстансы (${group?.instances_count || 0})` },
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инструменты', href: '/admin/tools' },
    { label: group?.name || groupSlug || 'Группа' },
  ];

  // DataTable columns for tools
  const toolColumns: DataTableColumn<ToolListItem>[] = [
    {
      key: 'slug',
      label: 'SLUG / ИМЯ',
      width: 250,
      render: (row) => (
        <div>
          <div style={{ fontWeight: 500 }}>{row.slug}</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>{row.name}</div>
        </div>
      ),
    },
    {
      key: 'type',
      label: 'ТИП',
      width: 120,
      render: (row) => (
        <Badge tone={TYPE_TONES[row.type] || 'neutral'} size="small">
          {TYPE_LABELS[row.type] || row.type}
        </Badge>
      ),
    },
    {
      key: 'releases_count',
      label: 'ВЕРСИИ',
      width: 100,
      render: (row) => (
        <span style={{ color: 'var(--muted)' }}>
          {row.releases_count || 0}
          {row.has_recommended && ' ★'}
        </span>
      ),
    },
    {
      key: 'is_active',
      label: 'СТАТУС',
      width: 100,
      render: (row) => (
        <Badge tone={row.is_active ? 'success' : 'neutral'} size="small">
          {row.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      ),
    },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={group?.name || groupSlug || 'Группа'}
      entityTypeLabel="группы"
      backPath="/admin/tools"
      breadcrumbs={breadcrumbs}
      loading={groupLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      showDelete={false}
      headerActions={
        <Button
          variant="outline"
          size="small"
          onClick={() => rescanMutation.mutate()}
          disabled={rescanMutation.isPending}
        >
          {rescanMutation.isPending ? 'Синхронизация...' : 'Rescan'}
        </Button>
      }
    >
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab}>
        <TabPanel id="main" activeTab={activeTab}>
          <ContentBlock
            title="Основная информация"
            editable={isEditable}
            fields={groupFields}
            data={formData}
            onChange={handleFieldChange}
            headerActions={
              <Badge tone={group?.is_active ? 'success' : 'neutral'} size="small">
                {group?.is_active ? 'Активна' : 'Неактивна'}
              </Badge>
            }
          />
        </TabPanel>

        <TabPanel id="tools" activeTab={activeTab}>
          <DataTable
            columns={toolColumns}
            data={group?.tools || []}
            keyField="id"
            emptyText="В этой группе пока нет инструментов"
            onRowClick={handleToolClick}
          />
        </TabPanel>

        <TabPanel id="instances" activeTab={activeTab}>
          <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)' }}>
            Таб инстансы будет реализован позже
          </div>
        </TabPanel>
      </Tabs>
    </EntityPage>
  );
}

export default ToolGroupViewPage;
