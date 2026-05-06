/**
 * CollectionPage — просмотр/создание/редактирование/удаление коллекции.
 *
 * Использует useEntityEditor для стандартной CRUD логики.
 */
import { useEffect, useMemo, useRef, useState as useReactState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  collectionsApi,
  adminApi,
  toolInstancesApi,
  type Collection,
  type CreateCollectionRequest,
  type CollectionField,
  type ToolInstanceDetail,
  type CollectionType,
} from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useEntityEditor } from '@/shared/hooks/useEntityEditor';
import { EntityPageV2, Tab } from '@/shared/ui';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { VersionsBlock } from '@/shared/ui/VersionsBlock';
import { Button, ConfirmDialog } from '@/shared/ui';
import { Select } from '@/shared/ui/Select';
import DataTable, { type DataTableColumn } from '@/shared/ui/DataTable/DataTable';
import { SqlCatalogDataTable } from './collection/SqlCatalogDataTable';
import { SqlDiscoveryModal } from './collection/SqlDiscoveryModal';
import { useSqlCollectionCatalog } from './collection/useSqlCollectionCatalog';
import {
  INFO_FIELDS,
  buildConfigFieldsByType,
  VECTOR_FIELDS,
  META_FIELDS,
  STATS_FIELDS,
  VECTOR_STATS_FIELDS,
} from './collection/fields/blockConfigs';
import {
  ensureSqlPresetFields,
  applyCollectionTypeFieldPreset,
} from './collection/fields/collectionFieldPresets';
import { FieldsEditor } from './collection/fields/FieldsEditor';
import { collectionFieldColumns } from './collection/fields/fieldColumns';

/* ─── Page-specific columns ─── */

type RuntimeOperationRow = NonNullable<ToolInstanceDetail['runtime_operations']>[number];

const ACTIVE_VERSION_CONTENT_FIELDS: FieldConfig[] = [
  {
    key: 'data_description',
    type: 'textarea',
    label: 'Что это за данные',
    description: 'Человеко-читаемое описание состава и смысла данных.',
    rows: 5,
    editable: false,
  },
  {
    key: 'usage_purpose',
    type: 'textarea',
    label: 'Зачем эти данные',
    description: 'Какие сценарии и задачи в рантайме покрывает коллекция.',
    rows: 5,
    editable: false,
  },
  {
    key: 'notes',
    type: 'textarea',
    label: 'Заметки версии',
    description: 'Технические заметки по изменениям в версии.',
    rows: 5,
    editable: false,
  },
];

const ACTIVE_VERSION_META_FIELDS: FieldConfig[] = [
  { key: 'version', type: 'code', label: 'Версия', editable: false },
  { key: 'status', type: 'badge', label: 'Статус', badgeTone: 'neutral', editable: false },
  { key: 'created_at', type: 'date', label: 'Создана', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлена', editable: false },
];

const TOOL_COLUMNS: DataTableColumn<RuntimeOperationRow>[] = [
  { key: 'operation_slug', label: 'Operation slug', render: (row) => <code>{row.operation_slug}</code> },
  { key: 'operation', label: 'Operation', render: (row) => row.operation || '—' },
  { key: 'source', label: 'Source', render: (row) => row.source || '—' },
  { key: 'risk_level', label: 'Risk', render: (row) => row.risk_level || '—' },
  { key: 'side_effects', label: 'Side effects', render: (row) => row.side_effects || '—' },
  { key: 'provider_instance_slug', label: 'Provider', render: (row) => row.provider_instance_slug || '—' },
];

/* ─── Component ─── */

export function CollectionPage() {
  const navigate = useNavigate();
  const { data: tenantsData } = useQuery({
    queryKey: qk.admin.tenants.list(),
    queryFn: () => adminApi.getTenants(),
    staleTime: 60_000,
  });
  const tenantOptions = (tenantsData?.items ?? []).map((t) => ({ value: t.id, label: t.name }));

  const { data: dataConnectors = [] } = useQuery({
    queryKey: ['connectors', 'data-list'],
    queryFn: () => toolInstancesApi.list({ connector_type: 'data' }),
    staleTime: 60_000,
  });

  const {
    mode,
    isNew,
    isEditable,
    entity: collection,
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
  } = useEntityEditor<Collection, CreateCollectionRequest, Partial<CreateCollectionRequest>>({
    entityType: 'collection',
    entityNameLabel: 'Коллекции',
    entityTypeLabel: 'коллекция',
    basePath: '/admin/collections',
    listPath: '/admin/collections',
    api: {
      get: (id) => collectionsApi.getById(id),
      create: (data) => collectionsApi.create(data),
      update: (id, data) => collectionsApi.update(id, data as any),
      delete: (id) => collectionsApi.delete(id),
    },
    queryKeys: {
      list: qk.collections.list(),
      detail: (id) => qk.collections.detail(id),
    },
    getInitialFormData: (col) => ({
      slug: col?.slug ?? '',
      name: col?.name ?? '',
      description: col?.description ?? '',
      collection_type: (col?.collection_type ?? 'table') as CollectionType,
      tenant_id: col?.tenant_id ?? '',
      table_name: col?.table_name ?? '',
      data_instance_id: col?.data_instance_id ?? '',
      is_active: col?.is_active ?? true,
      has_vector_search: col?.has_vector_search ?? false,
      chunk_strategy: col?.vector_config?.chunk_strategy ?? 'by_tokens',
      chunk_size: col?.vector_config?.chunk_size ?? 500,
      overlap: col?.vector_config?.overlap ?? 50,
      fields: (
        col?.collection_type === 'sql'
          ? ensureSqlPresetFields((col?.fields ?? []) as CollectionField[])
          : (col?.fields ?? [])
      ) as CollectionField[],
    }),
    validateCreate: (data) => {
      if (!data.slug?.trim() || !data.name?.trim() || !data.tenant_id) {
        return 'Заполните slug, название и тенант';
      }
      const createType = (data.collection_type ?? 'table') as CollectionType;
      const isRemoteType = createType === 'sql' || createType === 'api';
      if (isRemoteType && !data.data_instance_id) {
        return 'Нужно выбрать коннектор данных';
      }
      return null;
    },
    transformCreate: (data) => {
      const isDocument = data.collection_type === 'document';
      const isApi = data.collection_type === 'api';
      const isSql = data.collection_type === 'sql';
      const fields = (
        isApi
          ? []
          : isSql
            ? ensureSqlPresetFields((data.fields ?? []) as CollectionField[])
            : isDocument
              ? (data.fields ?? []).filter((f: CollectionField) => f.category !== 'specific')
              : (data.fields ?? [])
      ) as CollectionField[];
      const hasVectorFields = fields.some((f: CollectionField) => f.search_modes?.includes('vector'));
      const needsVectorConfig = data.has_vector_search || isDocument || hasVectorFields;

      return {
        tenant_id: data.tenant_id,
        collection_type: data.collection_type ?? 'table',
        slug: data.slug,
        name: data.name,
        description: data.description,
        fields,
        data_instance_id: data.data_instance_id || undefined,
        vector_config: needsVectorConfig ? {
          chunk_strategy: data.chunk_strategy ?? 'by_paragraphs',
          chunk_size: data.chunk_size ?? 512,
          overlap: data.overlap ?? 50,
        } : undefined,
      };
    },
    messages: {
      create: 'Коллекция создана',
      update: 'Коллекция обновлена',
      delete: 'Коллекция удалена',
    },
  });

  const { data: versions = [] } = useQuery({
    queryKey: qk.collections.versions(collection?.id ?? ''),
    queryFn: () => collectionsApi.listVersions(collection!.id),
    enabled: !isNew && !!collection?.id,
    staleTime: 30_000,
  });

  const { data: dataConnector } = useQuery({
    queryKey: ['connectors', 'detail', collection?.data_instance_id ?? ''],
    queryFn: () => toolInstancesApi.get(collection!.data_instance_id!),
    enabled: !isNew && !!collection?.data_instance_id,
    staleTime: 30_000,
  });

  // ─── Derived ───
  const viewData = {
    slug: collection?.slug ?? '',
    name: collection?.name ?? '',
    description: collection?.description ?? '',
    collection_type: collection?.collection_type ?? 'table',
    tenant_id: collection?.tenant_id ?? '',
    table_name: collection?.table_name ?? '',
    data_instance_id: collection?.data_instance_id ?? '',
    is_active: collection?.is_active ?? true,
    has_vector_search: collection?.has_vector_search ?? false,
    chunk_strategy: collection?.vector_config?.chunk_strategy ?? 'by_tokens',
    chunk_size: collection?.vector_config?.chunk_size ?? 500,
    overlap: collection?.vector_config?.overlap ?? 50,
    status: collection?.status ?? '',
    status_details: collection?.status_details ?? {},
    qdrant_collection_name: collection?.qdrant_collection_name ?? '',
    total_rows: collection?.total_rows ?? 0,
    vectorized_rows: collection?.vectorized_rows ?? 0,
    total_chunks: collection?.total_chunks ?? 0,
    failed_rows: collection?.failed_rows ?? 0,
    vectorization_progress: collection?.vectorization_progress ?? 0,
    is_fully_vectorized: collection?.is_fully_vectorized ?? false,
    id: collection?.id ?? '',
    created_at: collection?.created_at ?? '',
    updated_at: collection?.updated_at ?? '',
  };

  const blockData = isEditable ? formData : viewData;
  const activeCollectionType = (String(blockData.collection_type || 'table') as CollectionType);
  const isApiType = activeCollectionType === 'api';
  const isDocumentType = activeCollectionType === 'document';

  const connectorSubtypeFilter = activeCollectionType === 'sql'
    ? 'sql'
    : activeCollectionType === 'api'
      ? 'api'
      : '';

  const connectorOptions = useMemo(() => {
    const filtered = dataConnectors.filter((connector) => {
      if (connector.connector_type !== 'data') return false;
      if (!connectorSubtypeFilter) return true;
      return String(connector.connector_subtype || '').toLowerCase() === String(connectorSubtypeFilter);
    });

    const options = filtered.map((connector) => ({
      value: connector.id,
      label: `${connector.name} (${connector.slug})`,
    }));

    const selectedId = String(blockData.data_instance_id || '');
    if (
      selectedId
      && dataConnector
      && !options.some((opt) => opt.value === selectedId)
    ) {
      options.unshift({
        value: dataConnector.id,
        label: `${dataConnector.name} (${dataConnector.slug})`,
      });
    }
    return options;
  }, [blockData.data_instance_id, connectorSubtypeFilter, dataConnector, dataConnectors]);

  const infoFieldsWithOptions = useMemo(
    () => INFO_FIELDS.map((field) => (
      field.key === 'tenant_id' ? { ...field, options: tenantOptions } : field
    )),
    [tenantOptions],
  );

  const infoFieldsCreate = useMemo(
    () => infoFieldsWithOptions.map((field) => (
      (field.key === 'slug' || field.key === 'tenant_id') ? { ...field, editable: true } : field
    )),
    [infoFieldsWithOptions],
  );

  const configFieldsCreate = buildConfigFieldsByType(
    (formData.collection_type ?? 'table') as CollectionType,
    { editableCollectionType: true, editableDataInstance: true, connectorOptions },
  );
  const configFieldsViewEdit = buildConfigFieldsByType(
    activeCollectionType,
    { editableCollectionType: false, editableDataInstance: true, connectorOptions },
  ).map((field) => {
    if (field.key !== 'data_instance_id') return field;
    return {
      ...field,
      type: 'custom' as const,
      render: (value: string, editable: boolean, onChange: (v: string) => void) => {
        if (editable) {
          return (
            <Select
              value={value ?? ''}
              onChange={(val) => onChange(String(val))}
              placeholder="Выберите..."
              options={connectorOptions}
              disabled={false}
            />
          );
        }

        const connectorId = String(value || collection?.data_instance_id || '');
        const connectorName = collection?.data_instance?.name ?? dataConnector?.name ?? '—';
        if (!connectorId || connectorName === '—') return <span>—</span>;

        return (
          <a
            href={`/admin/instances/${connectorId}`}
            onClick={(e) => {
              e.preventDefault();
              navigate(`/admin/instances/${connectorId}`);
            }}
          >
            {connectorName}
          </a>
        );
      },
    };
  });

  const runtimeOperations = dataConnector?.runtime_operations ?? [];
  const activeVersion =
    collection?.current_version
    ?? versions.find((v) => v.status === 'published')
    ?? versions[0]
    ?? null;
  const activeVersionData = {
    version: activeVersion?.version ? `v${activeVersion.version}` : '—',
    status: activeVersion?.status ?? '—',
    created_at: activeVersion?.created_at ?? '',
    updated_at: activeVersion?.updated_at ?? '',
    data_description: activeVersion?.data_description ?? '—',
    usage_purpose: activeVersion?.usage_purpose ?? '—',
    notes: activeVersion?.notes ?? '—',
  };

  const statsData = {
    row_count: collection?.total_rows ?? 0,
    vectorization_progress: collection?.vectorization_progress ?? 0,
    fields_count: collection?.fields?.length ?? 0,
  };

  // Auto-preset: switch fields when collection_type changes
  const handleFieldChangeWrapped = (key: string, value: unknown) => {
    handleFieldChange(key, value);
    if (key === 'collection_type') {
      const nextType = String(value || 'table') as CollectionType;
      if (nextType === 'document') {
        handleFieldChange('fields', applyCollectionTypeFieldPreset(nextType, (formData.fields ?? []) as CollectionField[]));
        handleFieldChange('has_vector_search', true);
        handleFieldChange('chunk_strategy', 'by_paragraphs');
        handleFieldChange('chunk_size', 512);
        handleFieldChange('overlap', 50);
      } else if (nextType === 'table') {
        handleFieldChange('fields', applyCollectionTypeFieldPreset(nextType, (formData.fields ?? []) as CollectionField[]));
        handleFieldChange('has_vector_search', false);
      } else if (nextType === 'api') {
        handleFieldChange('fields', applyCollectionTypeFieldPreset(nextType, (formData.fields ?? []) as CollectionField[]));
        handleFieldChange('has_vector_search', false);
      } else if (nextType === 'sql') {
        handleFieldChange('fields', applyCollectionTypeFieldPreset(nextType, (formData.fields ?? []) as CollectionField[]));
        handleFieldChange('has_vector_search', false);
      }
    }
  };

  const {
    isSqlCollection,
    sqlCollectionData,
    sqlCollectionDataLoading,
    showSqlDiscoveryModal,
    setShowSqlDiscoveryModal,
    sqlDiscoveryLoading,
    sqlDiscoveryItems,
    sqlDiscoverySelected,
    sqlDiscoverySaving,
    sqlSelectedRowIds,
    sqlDeleting,
    existingSqlTableNames,
    setSqlSelectedRowIds,
    openSqlDiscoveryModal,
    handleSqlDiscoveryToggle,
    addDiscoveredSqlTables,
    deleteSelectedSqlTables,
  } = useSqlCollectionCatalog(collection, isNew);

  // ─── Upload for document collections (hooks must be before conditional returns) ───
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useReactState(false);
  const queryClient = useQueryClient();

  const isDocumentCollection = collection?.collection_type === 'document';

  const uploadMutation = useMutation({
    mutationFn: (file: File) =>
      collectionsApi.uploadDocument(collection!.id, {
        file,
        title: file.name,
        auto_ingest: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.collections.detail(collection!.id) });
      setUploading(false);
    },
    onError: () => {
      setUploading(false);
    },
  });

  const handleUploadClick = () => fileInputRef.current?.click();

  const handleFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    uploadMutation.mutate(file);
    e.target.value = '';
  };

  // ─── Create mode ───
  if (isNew) {
    return (
      <EntityPageV2
        title="Новая коллекция"
        mode="create"
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/collections"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="grid">
          <Block
            title="Основная информация"
            icon="database"
            iconVariant="info"
            width="1/2"
            fields={infoFieldsCreate}
            data={formData}
            editable
            onChange={handleFieldChangeWrapped}
          />
          <Block
            title="Конфигурация"
            icon="settings"
            iconVariant="primary"
            width="1/2"
            height="stretch"
            fields={configFieldsCreate}
            data={formData}
            editable
            onChange={handleFieldChangeWrapped}
          />
          {formData.collection_type !== 'api' && (
            <Block
              title="Поля коллекции"
              icon="list"
              iconVariant="primary"
              width="full"
            >
              <FieldsEditor
                fields={formData.fields ?? []}
                onChange={(fields) => handleFieldChange('fields', fields)}
                collectionType={(formData.collection_type ?? 'table') as CollectionType}
              />
            </Block>
          )}
        </Tab>
      </EntityPageV2>
    );
  }

  // ─── View / Edit mode ───
  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        style={{ display: 'none' }}
        onChange={handleFileSelected}
      />
      <EntityPageV2
        title={collection?.name ?? 'Коллекция'}
        mode={mode}
        loading={isLoading}
        saving={saving}
        breadcrumbs={breadcrumbs}
        onEdit={handleEdit}
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab
          title="Обзор"
          layout="grid"
          id="overview"
          actions={
            mode === 'edit'
              ? [
                  <Button key="cancel" variant="outline" onClick={handleCancel} disabled={saving}>Отмена</Button>,
                  <Button key="save" variant="primary" onClick={handleSave} disabled={saving}>
                    {saving ? 'Сохранение...' : 'Сохранить'}
                  </Button>,
                ]
              : [
                  <Button key="edit" variant="primary" onClick={handleEdit}>Редактировать</Button>,
                  ...(isDocumentCollection ? [(
                    <Button
                      key="upload"
                      variant="primary"
                      onClick={handleUploadClick}
                      disabled={uploading}
                    >
                      {uploading ? 'Загрузка...' : 'Загрузить файл'}
                    </Button>
                  )] : []),
                  <Button key="delete" variant="danger" onClick={handleDelete}>Удалить</Button>,
                ]
          }
        >
          <Block
            title="Основная информация"
            icon="database"
            iconVariant="info"
            width="1/2"
            fields={infoFieldsWithOptions}
            data={blockData}
            editable={isEditable}
            onChange={handleFieldChangeWrapped}
          />
          <Block
            title="Конфигурация"
            icon="settings"
            iconVariant="primary"
            width="1/2"
            height="stretch"
            fields={configFieldsViewEdit}
            data={blockData}
            editable={isEditable}
            onChange={handleFieldChangeWrapped}
          />
          {isDocumentType && (
            <Block
              title="Векторизация"
              icon="zap"
              iconVariant="warning"
              width="1/2"
              fields={VECTOR_FIELDS}
              data={blockData}
              editable={isEditable}
              onChange={handleFieldChange}
            />
          )}
          <Block
            title="Статистика"
            icon="bar-chart"
            iconVariant="primary"
            width="1/2"
            fields={STATS_FIELDS}
            data={statsData}
          />
          {isDocumentType && (
            <Block
              title="Векторный статус"
              icon="zap"
              iconVariant="success"
              width="1/2"
              fields={VECTOR_STATS_FIELDS}
              data={viewData}
              editable={false}
            />
          )}
          <Block
            title="Метаданные"
            icon="code"
            iconVariant="info"
            width="full"
            fields={META_FIELDS}
            data={viewData}
            editable={false}
          />
        </Tab>

        {!isNew && (
          <Tab
            title="Описание данных"
            layout="grid"
            id="active-version"
          >
            <Block
              title="Описание версии"
              icon="file-text"
              iconVariant="info"
              width="2/3"
              fields={ACTIVE_VERSION_CONTENT_FIELDS}
              data={activeVersionData}
              editable={false}
            />
            <Block
              title="Метаданные версии"
              icon="info"
              iconVariant="neutral"
              width="1/3"
              fields={ACTIVE_VERSION_META_FIELDS}
              data={activeVersionData}
              editable={false}
            />
          </Tab>
        )}

        <Tab
          title="Поля"
          layout="full"
          id="fields"
          badge={collection?.fields?.length ?? 0}
          hidden={isApiType}
        >
          <DataTable<CollectionField>
            columns={collectionFieldColumns}
            data={collection?.fields ?? []}
            keyField="name"
            emptyText="Нет полей. Создайте новую коллекцию с нужными полями."
          />
        </Tab>

        <Tab
          title="Данные"
          layout="full"
          id="data"
          hidden={!isSqlCollection}
          badge={sqlCollectionData?.total ?? 0}
          actions={
            mode === 'view'
              ? [
                  <Button key="sql-discover" onClick={openSqlDiscoveryModal}>Добавить</Button>,
                  <Button
                    key="sql-delete-selected"
                    variant="danger"
                    onClick={deleteSelectedSqlTables}
                    disabled={sqlDeleting || sqlSelectedRowIds.size === 0}
                  >
                    {sqlDeleting ? 'Удаление...' : `Удалить (${sqlSelectedRowIds.size})`}
                  </Button>,
                ]
              : []
          }
        >
          <SqlCatalogDataTable
            data={sqlCollectionData?.items ?? []}
            loading={sqlCollectionDataLoading}
            selectedRowIds={sqlSelectedRowIds}
            onSelectionChange={setSqlSelectedRowIds}
          />
        </Tab>

        {!isNew && (
          <Tab
            title="Доступные инструменты"
            layout="full"
            id="tools"
            badge={runtimeOperations.length}
          >
            <DataTable<RuntimeOperationRow>
              columns={TOOL_COLUMNS}
              data={runtimeOperations}
              keyField="operation_slug"
              emptyText="Для связанного коннектора нет runtime-операций."
            />
          </Tab>
        )}

        {!isNew && (
          <Tab
            title="Версии"
            layout="full"
            id="versions"
            badge={versions.length}
            actions={
              mode === 'view'
                ? [
                    <Button
                      key="create-version"
                      onClick={() => navigate(`/admin/collections/${collection?.id}/versions/new`)}
                    >
                      Создать версию
                    </Button>,
                  ]
                : []
            }
          >
            <VersionsBlock
              entityType="collection"
              versions={versions}
              recommendedVersionId={collection?.current_version_id ?? undefined}
              onSelectVersion={(version) =>
                navigate(`/admin/collections/${collection?.id}/versions/${version.version}`)
              }
            />
          </Tab>
        )}
      </EntityPageV2>

      <SqlDiscoveryModal
        open={showSqlDiscoveryModal}
        onClose={() => setShowSqlDiscoveryModal(false)}
        loading={sqlDiscoveryLoading}
        saving={sqlDiscoverySaving}
        items={sqlDiscoveryItems}
        selected={sqlDiscoverySelected}
        existingNames={existingSqlTableNames}
        onToggle={handleSqlDiscoveryToggle}
        onSubmit={addDiscoveredSqlTables}
      />

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить коллекцию?"
        message={`Удаление коллекции "${collection?.name}" удалит все данные и векторные индексы. Это действие необратимо.`}
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={handleDeleteConfirm}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}

export default CollectionPage;
