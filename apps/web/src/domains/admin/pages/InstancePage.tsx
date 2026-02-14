/**
 * InstancePage - Create/View/Edit tool instance
 *
 * Tabs:
 * 1. Обзор - основная информация, конфигурация, статус
 * 2. Креденшалы - таблица привязанных креденшалов
 */
import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  toolInstancesApi,
  toolGroupsApi,
  credentialsApi,
  type ToolInstanceCreate,
  type ToolInstanceUpdate,
  type Credential,
} from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui/EntityPage/EntityPageV2';
import { ContentBlock, Badge, DataTable, Button, type FieldDefinition, type DataTableColumn } from '@/shared/ui';

// --- Constants ---

const INSTANCE_TYPE_OPTIONS = [
  { value: 'local', label: 'Локальный' },
  { value: 'remote', label: 'Удаленный' },
];

const CATEGORY_OPTIONS = [
  { value: 'collection', label: 'Collection' },
  { value: 'rag', label: 'RAG' },
  { value: 'llm', label: 'LLM' },
  { value: 'dcbox', label: 'DCBox' },
  { value: 'jira', label: 'Jira' },
  { value: 'database', label: 'Database' },
  { value: 'api', label: 'API' },
  { value: 'other', label: 'Другое' },
];

const CATEGORY_LABELS: Record<string, string> = Object.fromEntries(
  CATEGORY_OPTIONS.map(o => [o.value, o.label])
);

// --- Component ---

export function InstancePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isCreate = !id;
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  // --- Form state ---
  const [formData, setFormData] = useState({
    tool_group_id: '',
    name: '',
    instance_type: 'local',
    url: '',
    description: '',
    config: '{}',
    category: '',
    is_active: true,
  });

  // --- Queries ---

  const { data: instance, isLoading } = useQuery({
    queryKey: qk.toolInstances.detail(id!),
    queryFn: () => toolInstancesApi.get(id!),
    enabled: !isCreate && !!id,
  });

  const { data: toolGroups = [] } = useQuery({
    queryKey: qk.toolGroups.list({}),
    queryFn: () => toolGroupsApi.listGroups(),
    staleTime: 300000,
  });

  const { data: credentials = [] } = useQuery({
    queryKey: [...qk.credentials.list({ instance_id: id! }), 'instance'],
    queryFn: () => credentialsApi.list({ instance_id: id! }),
    enabled: !isCreate && !!id,
  });

  // --- Options ---

  const toolGroupOptions = useMemo(() =>
    toolGroups.map((g: any) => ({ value: g.id, label: `${g.name} (${g.slug})` })),
    [toolGroups],
  );

  // --- Sync form data ---

  useEffect(() => {
    if (instance) {
      setFormData({
        tool_group_id: instance.tool_group_id,
        name: instance.name || '',
        instance_type: instance.instance_type || 'local',
        url: instance.url || '',
        description: instance.description || '',
        config: JSON.stringify(instance.config || {}, null, 2),
        category: instance.category || '',
        is_active: instance.is_active,
      });
    }
  }, [instance]);

  // --- Mutations ---

  const createMutation = useMutation({
    mutationFn: (data: ToolInstanceCreate) => toolInstancesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
      showSuccess('Инстанс создан');
      navigate('/admin/instances');
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: (data: ToolInstanceUpdate) => toolInstancesApi.update(id!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.detail(id!) });
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
      showSuccess('Инстанс обновлён');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const healthCheckMutation = useMutation({
    mutationFn: () => toolInstancesApi.healthCheck(id!),
    onSuccess: (result) => {
      showSuccess(`Health: ${result.status}`);
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.detail(id!) });
    },
    onError: (err: Error) => showError(err.message),
  });

  // --- Handlers ---

  const handleSave = async () => {
    let config: Record<string, unknown> = {};
    if (formData.config.trim()) {
      try {
        config = JSON.parse(formData.config);
      } catch {
        showError('Неверный формат JSON в конфигурации');
        return;
      }
    }

    if (isCreate) {
      if (!formData.tool_group_id) {
        showError('Выберите группу инструментов');
        return;
      }
      if (!formData.name.trim()) {
        showError('Введите название');
        return;
      }
      createMutation.mutate({
        tool_group_id: formData.tool_group_id,
        name: formData.name,
        url: formData.url || undefined,
        description: formData.description || undefined,
        config,
        category: formData.category || undefined,
      });
    } else {
      updateMutation.mutate({
        name: formData.name,
        url: formData.url || undefined,
        description: formData.description || undefined,
        config,
        is_active: formData.is_active,
        category: formData.category || undefined,
      });
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isCreate) {
      navigate('/admin/instances');
    } else {
      if (instance) {
        setFormData({
          tool_group_id: instance.tool_group_id,
          name: instance.name || '',
          instance_type: instance.instance_type || 'local',
          url: instance.url || '',
          description: instance.description || '',
          config: JSON.stringify(instance.config || {}, null, 2),
          category: instance.category || '',
          is_active: instance.is_active,
        });
      }
      setSearchParams({});
    }
  };

  // --- Field definitions ---

  const mainFields: FieldDefinition[] = [
    {
      key: 'tool_group_id',
      label: 'Группа инструментов',
      type: 'select',
      required: true,
      options: toolGroupOptions,
      disabled: !isCreate, // Нельзя менять группу после создания
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
    },
    {
      key: 'instance_type',
      label: 'Тип',
      type: 'select',
      options: INSTANCE_TYPE_OPTIONS,
      disabled: !isCreate, // Нельзя менять тип после создания
    },
    {
      key: 'url',
      label: 'URL',
      type: 'text',
      placeholder: 'https://api.example.com/v1',
    },
    {
      key: 'category',
      label: 'Категория',
      type: 'select',
      options: CATEGORY_OPTIONS,
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      rows: 3,
    },
  ];

  const statusFields: FieldDefinition[] = [
    {
      key: 'is_active',
      label: 'Статус',
      type: 'boolean',
    },
    {
      key: 'health_status',
      label: 'Health',
      type: 'badge',
      badgeTone: instance?.health_status === 'healthy' ? 'success'
        : instance?.health_status === 'unhealthy' ? 'danger' : 'neutral',
    },
    {
      key: 'created_at',
      label: 'Создан',
      type: 'date',
    },
  ];

  const configFields: FieldDefinition[] = [
    {
      key: 'config',
      label: 'JSON конфигурация',
      type: 'textarea',
      rows: 10,
      placeholder: '{"key": "value"}',
    },
  ];

  // --- View data ---

  const viewData = instance ? {
    tool_group_id: instance.tool_group_name || instance.tool_group_slug || instance.tool_group_id,
    name: instance.name,
    instance_type: instance.instance_type === 'local' ? 'Локальный' : 'Удаленный',
    url: instance.url || '—',
    category: CATEGORY_LABELS[instance.category || ''] || instance.category || '—',
    description: instance.description || '—',
    is_active: instance.is_active,
    health_status: instance.health_status || '—',
    created_at: instance.created_at ? new Date(instance.created_at).toLocaleString('ru-RU') : '—',
    config: JSON.stringify(instance.config || {}, null, 2),
  } : formData;

  // --- Credential columns ---

  const credentialColumns: DataTableColumn<Credential>[] = [
    {
      key: 'auth_type',
      label: 'ТИП',
      width: 120,
      render: (c) => <Badge tone="neutral">{c.auth_type}</Badge>,
    },
    {
      key: 'owner',
      label: 'ВЛАДЕЛЕЦ',
      render: (c) => {
        if (c.owner_platform) return <Badge tone="info">Платформа</Badge>;
        if (c.owner_tenant_id) return <span style={{ fontSize: '0.8125rem' }}>Тенант: <code>{c.owner_tenant_id.slice(0, 8)}…</code></span>;
        if (c.owner_user_id) return <span style={{ fontSize: '0.8125rem' }}>Юзер: <code>{c.owner_user_id.slice(0, 8)}…</code></span>;
        return <span style={{ color: 'var(--text-secondary)' }}>—</span>;
      },
    },
    {
      key: 'is_active',
      label: 'СТАТУС',
      width: 100,
      render: (c) => (
        <Badge tone={c.is_active ? 'success' : 'neutral'}>
          {c.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      label: 'СОЗДАН',
      width: 120,
      render: (c) => (
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
          {new Date(c.created_at).toLocaleDateString('ru-RU')}
        </span>
      ),
    },
  ];

  // --- Breadcrumbs ---

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инстансы', href: '/admin/instances' },
    { label: isCreate ? 'Новый инстанс' : (instance?.name || 'Инстанс') },
  ];

  const saving = createMutation.isPending || updateMutation.isPending;

  // --- Create mode ---

  if (isCreate) {
    return (
      <EntityPageV2
        title="Новый инстанс"
        mode={mode}
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/instances"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="grid">
          <ContentBlock
            title="Основная информация"
            icon="server"
            fields={mainFields}
            data={formData}
            editable={true}
            onChange={(key, value) => setFormData(prev => ({ ...prev, [key]: value }))}
          />
          <ContentBlock
            title="Конфигурация"
            icon="settings"
            fields={configFields}
            data={formData}
            editable={true}
            onChange={(key, value) => setFormData(prev => ({ ...prev, [key]: value }))}
          />
        </Tab>
      </EntityPageV2>
    );
  }

  // --- View/Edit mode ---

  return (
    <EntityPageV2
      title={instance?.name || 'Инстанс'}
      mode={mode}
      loading={isLoading}
      saving={saving}
      breadcrumbs={breadcrumbs}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
    >
      <Tab title="Обзор" layout="grid" actions={
        mode === 'view' ? [
          <Button key="health" variant="outline" onClick={() => healthCheckMutation.mutate()} disabled={healthCheckMutation.isPending}>
            Health Check
          </Button>,
        ] : []
      }>
        <ContentBlock
          title="Основная информация"
          icon="server"
          fields={mainFields}
          data={isEditable ? formData : viewData}
          editable={isEditable}
          onChange={(key, value) => setFormData(prev => ({ ...prev, [key]: value }))}
        />
        <ContentBlock
          title="Статус"
          icon="activity"
          fields={statusFields}
          data={isEditable ? { ...formData, health_status: instance?.health_status || '—', created_at: instance?.created_at } : viewData}
          editable={isEditable}
          onChange={(key, value) => setFormData(prev => ({ ...prev, [key]: value }))}
        />
        <ContentBlock
          title="Конфигурация"
          icon="settings"
          width="full"
          fields={configFields}
          data={isEditable ? formData : viewData}
          editable={isEditable}
          onChange={(key, value) => setFormData(prev => ({ ...prev, [key]: value }))}
        />
      </Tab>

      <Tab title="Креденшалы" layout="full" badge={credentials.length || undefined}>
        <DataTable
          columns={credentialColumns}
          data={credentials}
          keyField="id"
          emptyText="Нет привязанных креденшалов"
          onRowClick={(c) => navigate(`/admin/credentials/${c.id}`)}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default InstancePage;
