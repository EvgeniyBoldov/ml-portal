/**
 * ToolGroupViewPage v2 - View/Edit tool group with tabs
 *
 * Tabs: Обзор | Инструменты
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

type TabType = 'main' | 'tools';

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

  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
    type: '',
    description_for_router: '',
  });
  const [saving, setSaving] = useState(false);

  const { data: group, isLoading: groupLoading } = useQuery({
    queryKey: toolReleasesKeys.groupDetail(groupSlug!),
    queryFn: () => toolReleasesApi.getGroup(groupSlug!),
    enabled: !!groupSlug,
  });

  useEffect(() => {
    if (group) {
      setFormData({
        slug: group.slug,
        name: group.name,
        description: group.description || '',
        type: group.type || '',
        description_for_router: group.description_for_router || '',
      });
    }
  }, [group]);

  const updateMutation = useMutation({
    mutationFn: () => toolReleasesApi.updateGroup(groupSlug!, {
      name: formData.name,
      description: formData.description || null,
      type: formData.type || null,
      description_for_router: formData.description_for_router || null,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.groupDetail(groupSlug!) });
      queryClient.invalidateQueries({ queryKey: toolReleasesKeys.groupsList() });
      showSuccess('Группа обновлена');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка обновления'),
  });

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
        type: group.type || '',
        description_for_router: group.description_for_router || '',
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

  const groupFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug',
      type: 'text',
      disabled: true,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'RAG',
    },
    {
      key: 'type',
      label: 'Тип',
      type: 'text',
      placeholder: 'jira / crm / rag ...',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Описание группы инструментов...',
      rows: 2,
    },
    {
      key: 'description_for_router',
      label: 'Описание для роутера',
      type: 'textarea',
      placeholder: 'Описание для маршрутизации агентов...',
      rows: 2,
    },
  ];

  const tabs = [
    { id: 'main', label: 'Обзор' },
    { id: 'tools', label: `Инструменты (${group?.tools?.length || 0})` },
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инструменты', href: '/admin/tools' },
    { label: group?.name || groupSlug || 'Группа' },
  ];

  const toolColumns: DataTableColumn<ToolListItem>[] = [
    {
      key: 'slug',
      label: 'SLUG / ИМЯ',
      width: 250,
      render: (row) => (
        <div>
          <div style={{ fontWeight: 500 }}>{row.slug}</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>{row.name}</div>
        </div>
      ),
    },
    {
      key: 'kind',
      label: 'ТИП',
      width: 100,
      render: (row) => (
        <Badge tone={KIND_TONES[row.kind] || 'neutral'} size="small">
          {KIND_LABELS[row.kind] || row.kind}
        </Badge>
      ),
    },
    {
      key: 'releases_count',
      label: 'ВЕРСИИ',
      width: 100,
      render: (row) => (
        <span style={{ color: 'var(--text-secondary)' }}>
          {row.releases_count || 0}
          {row.has_current_version && ' ★'}
        </span>
      ),
    },
    {
      key: 'backend_releases_count',
      label: 'БЭКЕНД',
      width: 100,
      render: (row) => (
        <span style={{ color: 'var(--text-secondary)' }}>
          {row.backend_releases_count || 0}
        </span>
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
      </Tabs>
    </EntityPage>
  );
}

export default ToolGroupViewPage;
