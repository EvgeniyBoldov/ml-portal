/**
 * InstancePage v3 — просмотр/создание/редактирование/удаление коннектора.
 *
 * Classification axes: connector_type (data|mcp|model), connector_subtype (sql|api), placement (local|remote).
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import {
  toolInstancesApi,
  credentialsApi,
  type ToolInstanceDetail,
  type ToolInstanceCreate,
  type ToolInstanceUpdate,
  type ToolInstance,
} from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useEntityEditor } from '@/shared/hooks/useEntityEditor';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { Button, ConfirmDialog, Badge, HealthIndicator } from '@/shared/ui';
import DataTable, { type DataTableColumn } from '@/shared/ui/DataTable/DataTable';
import { type Credential } from '@/shared/api/credentials';

/* ─── Field configs ─── */

const INFO_FIELDS: FieldConfig[] = [
  {
    key: 'slug',
    type: 'text',
    label: 'Slug (ID)',
    description: 'Уникальный идентификатор (нельзя изменить после создания)',
    placeholder: 'my-instance',
    editable: false,
  },
  {
    key: 'name',
    type: 'text',
    label: 'Название',
    required: true,
    placeholder: 'My Tool Instance',
  },
  {
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    placeholder: 'Описание коннектора...',
    rows: 3,
  },
  {
    key: 'is_active',
    type: 'boolean',
    label: 'Активен',
    description: 'Коннектор доступен для использования',
  },
];

const CLASSIFICATION_FIELDS: FieldConfig[] = [
  {
    key: 'connector_type',
    type: 'select',
    label: 'Тип',
    description: 'Тип коннектора',
    options: [
      { value: 'data', label: 'Data — источник данных' },
      { value: 'mcp', label: 'MCP — провайдер инструментов' },
      { value: 'model', label: 'Model — провайдер моделей' },
    ],
  },
  {
    key: 'connector_subtype',
    type: 'select',
    label: 'Подтип data-коннектора',
    description: 'Способ подключения к источнику данных',
    options: [
      { value: 'sql', label: 'SQL' },
      { value: 'api', label: 'API' },
    ],
  },
  {
    key: 'access_via_instance_id',
    type: 'select',
    label: 'MCP-коннектор',
    description: 'Коннектор, через который доступен data-коннектор',
  },
  {
    key: 'placement',
    type: 'select',
    label: 'Размещение',
    description: 'Локальный или удаленный',
    editable: false,
    options: [
      { value: 'local', label: 'Локальный (auto-managed)' },
      { value: 'remote', label: 'Удалённый (user-managed)' },
    ],
  },
];

const CONNECTION_FIELDS: FieldConfig[] = [
  {
    key: 'url',
    type: 'text',
    label: 'URL',
    placeholder: 'https://api.example.com/v1',
    description: 'Endpoint для подключения',
  },
];

const SQL_CONFIG_FIELDS: FieldConfig[] = [
  {
    key: 'database_name',
    type: 'text',
    label: 'Database name',
    required: true,
    placeholder: 'netbox',
    description: 'Имя базы данных для SQL подключения',
  },
  {
    key: 'schema_name',
    type: 'text',
    label: 'Schema name',
    placeholder: 'public',
    description: 'Опционально: схема БД',
  },
];

const API_CONFIG_FIELDS: FieldConfig[] = [
  {
    key: 'base_path',
    type: 'text',
    label: 'Base path',
    placeholder: '/v1',
    description: 'Опционально: базовый путь API',
  },
  {
    key: 'timeout_seconds',
    type: 'number',
    label: 'Timeout (sec)',
    placeholder: '30',
    description: 'Таймаут запроса',
  },
];

const META_FIELDS: FieldConfig[] = [
  { key: 'id', type: 'code', label: 'ID', editable: false },
  { key: 'created_at', type: 'date', label: 'Создан', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлён', editable: false },
];

const AUTH_TYPE_LABELS: Record<string, string> = {
  token: 'Bearer Token',
  basic: 'Basic Auth',
  api_key: 'API Key',
  oauth: 'OAuth 2.0',
};

const credentialColumns: DataTableColumn<Credential>[] = [
  {
    key: 'auth_type',
    label: 'Тип',
    render: (c: Credential) => (
      <Badge tone="neutral">{AUTH_TYPE_LABELS[c.auth_type] || c.auth_type}</Badge>
    ),
  },
  {
    key: 'is_active',
    label: 'Статус',
    render: (c: Credential) => (
      <Badge tone={c.is_active ? 'success' : 'warn'}>{c.is_active ? 'Активен' : 'Отключен'}</Badge>
    ),
  },
  {
    key: 'owner_platform',
    label: 'Уровень',
    render: (c: Credential) => {
      if (c.owner_platform) return <Badge tone="info">Platform</Badge>;
      if (c.owner_tenant_id) return <Badge tone="neutral">Tenant</Badge>;
      return <Badge tone="neutral">User</Badge>;
    },
  },
  {
    key: 'created_at',
    label: 'Создан',
    render: (c: Credential) => new Date(c.created_at).toLocaleDateString('ru-RU'),
  },
];

function isSystemRuntimeInstance(instance: ToolInstance): boolean {
  const providerKind = typeof instance.provider_kind === 'string'
    ? instance.provider_kind.toLowerCase()
    : typeof instance.config?.provider_kind === 'string'
      ? String(instance.config.provider_kind).toLowerCase()
      : '';
  return (
    providerKind === 'local_documents'
    || providerKind === 'local_tables'
    || providerKind === 'local_runtime'
  );
}

/* ─── Component ─── */

export function InstancePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // ─── useEntityEditor ───

  const {
    mode,
    isNew,
    isEditable,
    entity: instance,
    isLoading,
    formData,
    saving,
    showDeleteConfirm,
    setShowDeleteConfirm,
    breadcrumbs,
    handleFieldChange,
    handleSave,
    handleEdit,
    handleCancel,
    handleDelete,
    handleDeleteConfirm,
  } = useEntityEditor<ToolInstanceDetail, ToolInstanceCreate, ToolInstanceUpdate>({
    entityType: 'instance',
    entityNameLabel: 'Коннекторы',
    entityTypeLabel: 'коннектор',
    basePath: '/admin/connectors',
    listPath: '/admin/connectors',
    api: {
      get: (entityId) => toolInstancesApi.get(entityId),
      create: (data) => toolInstancesApi.create(data) as Promise<ToolInstanceDetail>,
      update: (entityId, data) => toolInstancesApi.update(entityId, data) as Promise<ToolInstanceDetail>,
      delete: (entityId) => toolInstancesApi.delete(entityId),
    },
    queryKeys: {
      list: qk.toolInstances.list({ placement: 'remote' }),
      detail: (entityId) => qk.toolInstances.detail(entityId),
    },
    getInitialFormData: (inst) => ({
      slug: inst?.slug ?? '',
      name: inst?.name ?? '',
      description: inst?.description ?? '',
      connector_type: inst?.connector_type ?? 'data',
      connector_subtype: inst?.connector_subtype ?? 'api',
      placement: inst?.placement ?? 'remote',
      url: inst?.url ?? '',
      access_via_instance_id: inst?.access_via_instance_id ?? '',
      is_active: inst?.is_active ?? true,
      database_name: String(inst?.config?.database_name ?? ''),
      schema_name: String(inst?.config?.schema_name ?? ''),
      base_path: String(inst?.config?.base_path ?? ''),
      timeout_seconds: Number(inst?.config?.timeout_seconds ?? 30),
    }),
    validateCreate: (data) => {
      if (!data.name?.trim()) return 'Введите название';
      if (data.connector_type === 'data' && !data.connector_subtype) {
        return 'Выберите подтип data-коннектора';
      }
      if (data.connector_type === 'data' && data.connector_subtype === 'sql' && !String(data.database_name ?? '').trim()) {
        return 'Для SQL-коннектора укажите database_name';
      }
      return null;
    },
    transformCreate: (data) => {
      const config = data.connector_type === 'data'
        ? (
            data.connector_subtype === 'sql'
              ? {
                  database_name: String(data.database_name ?? '').trim(),
                  schema_name: String(data.schema_name ?? '').trim() || undefined,
                }
              : {
                  base_path: String(data.base_path ?? '').trim() || undefined,
                  timeout_seconds: Number(data.timeout_seconds ?? 30),
                }
          )
        : undefined;
      return {
        slug: data.slug || undefined,
        name: data.name,
        description: data.description || undefined,
        connector_type: data.connector_type || 'data',
        connector_subtype: data.connector_type === 'data' ? (data.connector_subtype || 'api') : undefined,
        url: data.url || undefined,
        access_via_instance_id: data.access_via_instance_id || undefined,
        config,
      };
    },
    transformUpdate: (data) => {
      const config = data.connector_type === 'data'
        ? (
            data.connector_subtype === 'sql'
              ? {
                  database_name: String(data.database_name ?? '').trim(),
                  schema_name: String(data.schema_name ?? '').trim() || undefined,
                }
              : {
                  base_path: String(data.base_path ?? '').trim() || undefined,
                  timeout_seconds: Number(data.timeout_seconds ?? 30),
                }
          )
        : undefined;
      return {
        name: data.name,
        description: data.description,
        connector_type: data.connector_type,
        connector_subtype: data.connector_type === 'data' ? (data.connector_subtype || 'api') : null,
        url: data.url || undefined,
        access_via_instance_id: data.access_via_instance_id || null,
        config,
        is_active: data.is_active,
      };
    },
    messages: {
      create: 'Коннектор создан',
      update: 'Коннектор обновлён',
      delete: 'Коннектор удалён',
    },
  });

  // ─── Queries ───

  const { data: allInstances = [] } = useQuery({
    queryKey: qk.toolInstances.list({ connector_type: 'mcp', placement: 'remote' }),
    queryFn: () => toolInstancesApi.list({ connector_type: 'mcp', placement: 'remote' }),
    staleTime: 300_000,
  });

  const { data: credentials = [] } = useQuery({
    queryKey: [...qk.credentials.list({ instance_id: id! }), 'instance'],
    queryFn: () => credentialsApi.list({ instance_id: id! }),
    enabled: !isNew && !!id,
  });

  // ─── Health check ───

  const healthCheckMutation = useMutation({
    mutationFn: () => toolInstancesApi.healthCheck(id!),
    onSuccess: (result) => {
      showSuccess(`Health: ${result.status}`);
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.detail(id!) });
    },
    onError: (err: Error) => showError(err.message),
  });

  // ─── Derived ───

  const isDataInstance = (isEditable ? formData.connector_type : instance?.connector_type) === 'data';
  const isRemote = (isEditable ? formData.placement : instance?.placement) === 'remote';
  const isSystemInstance = instance ? isSystemRuntimeInstance(instance) : false;

  const serviceInstanceOptions = allInstances
    .filter((i: ToolInstance) => i.connector_type === 'mcp' && i.id !== id)
    .map((i: ToolInstance) => ({ value: i.id, label: i.name }));

  const viewData = {
    slug: instance?.slug ?? '',
    name: instance?.name ?? '',
    description: instance?.description ?? '',
    connector_type: instance?.connector_type ?? 'data',
    connector_subtype: instance?.connector_subtype ?? 'api',
    placement: instance?.placement ?? 'remote',
    url: instance?.url ?? '',
    access_via_instance_id: instance?.access_via_instance_id ?? '',
    is_active: instance?.is_active ?? false,
    database_name: String(instance?.config?.database_name ?? ''),
    schema_name: String(instance?.config?.schema_name ?? ''),
    base_path: String(instance?.config?.base_path ?? ''),
    timeout_seconds: Number(instance?.config?.timeout_seconds ?? 30),
    health_status: instance?.health_status ?? 'unknown',
    id: instance?.id ?? '',
    created_at: instance?.created_at ?? '',
    updated_at: instance?.updated_at ?? '',
  };

  const blockData = isEditable ? formData : viewData;

  // Slug editable only on create
  const infoFieldsForMode = isNew
    ? INFO_FIELDS.map(f => f.key === 'slug' ? { ...f, editable: true } : f)
    : INFO_FIELDS;

  const classificationFieldsForMode = useMemo(() => {
    const connectorOptions = [
      { value: '', label: 'Без MCP (напрямую)' },
      ...serviceInstanceOptions,
    ];

    let fields = CLASSIFICATION_FIELDS.map((field) =>
      field.key === 'access_via_instance_id'
        ? { ...field, options: connectorOptions }
        : field
    );

    if (isEditable) {
      fields = fields.filter((field) => field.key !== 'placement');
    }

    if (!isDataInstance) {
      return fields.filter((field) => field.key !== 'access_via_instance_id' && field.key !== 'connector_subtype');
    }

    return fields;
  }, [isDataInstance, isEditable, serviceInstanceOptions]);

  const connectionFieldsForMode = useMemo(
    () => (isRemote ? CONNECTION_FIELDS : []),
    [isRemote]
  );
  const dataSubtype = (isEditable ? formData.connector_subtype : viewData.connector_subtype) || 'api';
  const connectorConfigFields = useMemo(() => {
    if (!isDataInstance) return [];
    return dataSubtype === 'sql' ? SQL_CONFIG_FIELDS : API_CONFIG_FIELDS;
  }, [isDataInstance, dataSubtype]);

  // ─── Create mode ───

  if (isNew) {
    return (
      <EntityPageV2
        title="Новый коннектор"
        mode="create"
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/connectors"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="grid">
          <Block
            title="Основная информация"
            icon="server"
            iconVariant="info"
            width="1/2"
            fields={infoFieldsForMode}
            data={formData}
            editable
            onChange={handleFieldChange}
            headerActions={
              <HealthIndicator
                healthStatus={formData.health_status}
                isActive={formData.is_active}
              />
            }
          />
          <Block
            title="Классификация"
            icon="layers"
            iconVariant="primary"
            width="1/2"
            height="stretch"
            fields={classificationFieldsForMode}
            data={formData}
            editable
            onChange={handleFieldChange}
          />
          {connectionFieldsForMode.length > 0 && (
            <Block
              title="Подключение"
              icon="link"
              iconVariant="info"
              width="1/2"
              fields={connectionFieldsForMode}
              data={formData}
              editable
              onChange={handleFieldChange}
            />
          )}
          {connectorConfigFields.length > 0 && (
            <Block
              title="Параметры коннектора"
              icon="code"
              iconVariant="info"
              width="full"
              fields={connectorConfigFields}
              data={formData}
              editable
              onChange={handleFieldChange}
            />
          )}
        </Tab>
      </EntityPageV2>
    );
  }

  // ─── View / Edit mode ───

  const placementLabel = instance?.placement === 'local' ? 'локальный' : 'удалённый';
  const kindLabel = instance?.connector_type ?? 'data';

  return (
    <>
      <EntityPageV2
        title={instance ? `${instance.name} (${kindLabel} · ${placementLabel})` : 'Коннектор'}
        mode={mode}
        loading={isLoading}
        saving={saving}
        breadcrumbs={breadcrumbs}
        headerActions={
          isSystemInstance ? <Badge tone="warn">system managed</Badge> : undefined
        }
      >
        {/* ── Tab 1: Обзор ── */}
        <Tab
          title="Обзор"
          layout="grid"
          id="overview"
        actions={
          mode === 'view' ? [
              !isSystemInstance && (
                <Button key="edit" onClick={handleEdit}>Редактировать</Button>
              ),
              <Button
                key="health"
                variant="outline"
                onClick={() => healthCheckMutation.mutate()}
                disabled={healthCheckMutation.isPending}
              >
                {healthCheckMutation.isPending ? '...' : 'Health Check'}
              </Button>,
              !isSystemInstance && (
                <Button key="delete" variant="danger" onClick={handleDelete}>Удалить</Button>
              ),
            ].filter(Boolean) : mode === 'edit' ? [
              <Button key="save" onClick={handleSave} disabled={saving}>
                {saving ? 'Сохранение...' : 'Сохранить'}
              </Button>,
              <Button key="cancel" variant="outline" onClick={handleCancel} disabled={saving}>
                Отмена
              </Button>,
            ] : undefined
          }
        >
          <Block
            title="Основная информация"
            icon="server"
            iconVariant="info"
            width="1/2"
            fields={infoFieldsForMode}
            data={blockData}
            editable={isEditable}
            onChange={handleFieldChange}
            headerActions={
              <HealthIndicator
                healthStatus={viewData.health_status}
                isActive={blockData.is_active}
              />
            }
          />
          <Block
            title="Классификация"
            icon="layers"
            iconVariant="primary"
            width="1/2"
            height="stretch"
            fields={classificationFieldsForMode}
            data={blockData}
            editable={isEditable}
            onChange={handleFieldChange}
          />
          {connectionFieldsForMode.length > 0 && (
            <Block
              title="Подключение"
              icon="link"
              iconVariant="info"
              width="1/2"
              fields={connectionFieldsForMode}
              data={blockData}
              editable={isEditable}
              onChange={handleFieldChange}
            />
          )}
          <Block
            title="Метаданные"
            icon="database"
            iconVariant="info"
            width="1/2"
            fields={META_FIELDS}
            data={viewData}
          />
        </Tab>

        {connectorConfigFields.length > 0 && (
          <Tab title="Параметры" layout="grid" id="config">
            <Block
              title="Параметры коннектора"
              icon="code"
              iconVariant="info"
              width="full"
              fields={connectorConfigFields}
              data={blockData}
              editable={isEditable}
              onChange={handleFieldChange}
            />
          </Tab>
        )}

        {/* ── Tab 3: Креденшалы ── */}
        <Tab
          title="Креденшалы"
          layout="full"
          id="credentials"
          badge={credentials.length}
          actions={[
            <Button key="add" onClick={() => navigate(`/admin/credentials/new?instance_id=${id}`)}>
              Добавить креденшал
            </Button>,
          ]}
        >
          <DataTable<Credential>
            columns={credentialColumns}
            data={credentials}
            keyField="id"
            emptyText="Нет credentials. Нажмите 'Добавить креденшал'."
            onRowClick={(c) => navigate(`/admin/credentials/${c.id}`)}
          />
        </Tab>
      </EntityPageV2>

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить коннектор?"
        message={`Удаление коннектора "${instance?.name}" также удалит все привязанные креденшалы. Это действие необратимо.`}
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={handleDeleteConfirm}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}

export default InstancePage;
