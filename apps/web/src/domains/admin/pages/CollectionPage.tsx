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
  type BackendCollectionField,
  type CreateCollectionRequest,
  type CollectionField,
  type ToolInstanceDetail,
  type CollectionType,
  type UpdateCollectionRequest,
} from '@/shared/api';
import { lifecycleApi } from '@/shared/api/lifecycle';
import { qk } from '@/shared/api/keys';
import { useEntityEditor } from '@/shared/hooks/useEntityEditor';
import { EntityPageV2, Tab } from '@/shared/ui';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { VersionsBlock } from '@/shared/ui/VersionsBlock';
import { Button, LifecycleDeleteDialog } from '@/shared/ui';
import { buildEntityCrudActions, composeEntityActions } from '@/shared/ui/EntityPage/entityCrudActions';
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

type CollectionEditorForm = {
  slug: string;
  name: string;
  description: string;
  collection_type: CollectionType;
  tenant_id: string;
  table_name: string;
  data_instance_id: string;
  is_active: boolean;
  has_vector_search: boolean;
  chunk_strategy: string;
  chunk_size: number;
  overlap: number;
  fields: CollectionField[];
};

type EditableBackendField = BackendCollectionField & {
  search_modes: CollectionField['search_modes'];
  type: NonNullable<CollectionField['type']>;
};

function normalizeEditableFields(fields: CollectionField[]): EditableBackendField[] {
  return fields
    .filter((field) => field.category !== 'specific')
    .map((field) => ({
      name: field.name,
      category: field.category ?? 'user',
      data_type: field.data_type ?? field.type ?? 'text',
      required: field.required,
      description: field.description ?? '',
      filterable: field.filterable ?? (field.search_modes.includes('exact') || field.search_modes.includes('like')),
      sortable: field.sortable ?? field.search_modes.includes('range'),
      used_in_retrieval: field.used_in_retrieval ?? field.search_modes.includes('vector'),
      used_in_prompt_context: field.used_in_prompt_context ?? false,
      search_modes: [...field.search_modes],
      type: field.type ?? 'text',
    }));
}

function sameFieldShape(a: EditableBackendField, b: EditableBackendField): boolean {
  return (
    a.name === b.name
    && (a.category ?? 'user') === (b.category ?? 'user')
    && (a.data_type ?? a.type ?? 'text') === (b.data_type ?? b.type ?? 'text')
    && Boolean(a.required) === Boolean(b.required)
    && String(a.description ?? '') === String(b.description ?? '')
    && Boolean(a.filterable ?? (a.search_modes.includes('exact') || a.search_modes.includes('like')))
      === Boolean(b.filterable ?? (b.search_modes.includes('exact') || b.search_modes.includes('like')))
    && Boolean(a.sortable ?? a.search_modes.includes('range'))
      === Boolean(b.sortable ?? b.search_modes.includes('range'))
    && Boolean(a.used_in_retrieval ?? a.search_modes.includes('vector'))
      === Boolean(b.used_in_retrieval ?? b.search_modes.includes('vector'))
    && Boolean(a.used_in_prompt_context)
      === Boolean(b.used_in_prompt_context)
  );
}

function buildSchemaOps(
  originalFields: CollectionField[],
  currentFields: CollectionField[],
): NonNullable<UpdateCollectionRequest['schema_ops']> {
  const original = normalizeEditableFields(originalFields);
  const current = normalizeEditableFields(currentFields);
  const originalByName = new Map(original.map((field) => [field.name, field]));
  const currentByName = new Map(current.map((field) => [field.name, field]));
  const removed = original.filter((field) => !currentByName.has(field.name));
  const added = current.filter((field) => !originalByName.has(field.name));
  const ops: NonNullable<UpdateCollectionRequest['schema_ops']> = [];
  const consumedAdded = new Set<string>();
  const consumedRemoved = new Set<string>();

  for (let index = 0; index < Math.min(removed.length, added.length); index += 1) {
    const oldField = removed[index];
    const newField = added[index];
    if (sameFieldShape({ ...oldField, name: newField.name }, newField)) {
      ops.push({ op: 'rename', name: oldField.name, new_name: newField.name });
      consumedRemoved.add(oldField.name);
      consumedAdded.add(newField.name);
    }
  }

  for (const field of removed) {
    if (!consumedRemoved.has(field.name)) {
      ops.push({ op: 'remove', name: field.name });
    }
  }

  for (const field of added) {
    if (!consumedAdded.has(field.name)) {
      ops.push({ op: 'add', field });
    }
  }

  for (const field of current) {
    const previous = originalByName.get(field.name);
    if (!previous) continue;
    if (!sameFieldShape(previous, field)) {
      ops.push({ op: 'alter', name: field.name, field });
    }
  }

  return ops;
}

function fallbackOperationsByCollectionType(collectionType: CollectionType): RuntimeOperationRow[] {
  const base = (operation_slug: string, operation: string, source = 'local'): RuntimeOperationRow => ({
    operation_slug,
    operation,
    source,
    discovered_tool_slug: operation,
    provider_instance_slug: null,
    risk_level: 'low',
    side_effects: 'none',
    idempotent: true,
    requires_confirmation: false,
  });

  if (collectionType === 'document') {
    return [
      base('collection.document.catalog_inspect', 'collection.catalog'),
      base('collection.document.search', 'collection.doc_search'),
    ];
  }
  if (collectionType === 'table') {
    return [
      base('collection.table.catalog_inspect', 'collection.catalog'),
      base('collection.table.search', 'collection.search'),
      base('collection.table.aggregate', 'collection.aggregate'),
      base('collection.table.get', 'collection.get'),
    ];
  }
  if (collectionType === 'sql') {
    return [
      base('collection.sql.catalog_inspect', 'collection.catalog'),
      base('collection.sql.search_objects', 'search_objects'),
      base('collection.sql.execute', 'execute_sql'),
    ];
  }
  if (collectionType === 'api') {
    return [
      base('collection.api.catalog_inspect', 'collection.catalog'),
    ];
  }
  if (collectionType === 'template') {
    return [
      base('template.list', 'template.list'),
      base('collection.text_search', 'collection.text_search'),
      base('template.get_schema', 'template.get_schema'),
      base('template.fill', 'template.fill'),
    ];
  }
  return [];
}

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
      list: qk.collections.adminList(),
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
      if (!data.name?.trim() || !data.tenant_id) {
        return 'Заполните название и тенант';
      }
      const createType = (data.collection_type ?? 'table') as CollectionType;
      const isRemoteType = createType === 'sql' || createType === 'api';
      if (isRemoteType && !data.data_instance_id) {
        return 'Нужно выбрать коннектор данных';
      }
      if (createType === 'template' && (!data.fields || data.fields.length === 0)) {
        return 'Добавьте хотя бы одно поле в коллекцию шаблонов';
      }
      return null;
    },
    transformCreate: (data) => {
      const isDocument = data.collection_type === 'document';
      const isTemplate = data.collection_type === 'template';
      const isApi = data.collection_type === 'api';
      const isSql = data.collection_type === 'sql';
      const fields = (
        isApi
          ? []
          : isSql
            ? ensureSqlPresetFields((data.fields ?? []) as CollectionField[])
            : isDocument || isTemplate
              ? (data.fields ?? []).filter((f: CollectionField) => f.category !== 'specific')
              : (data.fields ?? [])
      ) as CollectionField[];
      const hasVectorFields = fields.some((f: CollectionField) => f.search_modes?.includes('vector'));
      const needsVectorConfig = data.has_vector_search || isDocument || hasVectorFields;

      return {
        tenant_id: data.tenant_id,
        collection_type: data.collection_type ?? 'table',
        slug: data.slug?.trim() || undefined,
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
    transformUpdate: (data: CollectionEditorForm) => {
      const schemaOps = buildSchemaOps(collection?.fields ?? [], (data.fields ?? []) as CollectionField[]);
      return {
        tenant_id: data.tenant_id || undefined,
        name: data.name,
        description: data.description,
        is_active: data.is_active,
        table_name: data.table_name || undefined,
        schema_ops: schemaOps,
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
  const isTemplateType = activeCollectionType === 'template';

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
  const infoFieldsViewEdit = useMemo(
    () => infoFieldsWithOptions.map((field) => (
      field.key === 'tenant_id' ? { ...field, editable: true } : field
    )),
    [infoFieldsWithOptions],
  );

  const configFieldsCreate = buildConfigFieldsByType(
    (formData.collection_type ?? 'table') as CollectionType,
    { editableCollectionType: true, editableDataInstance: true, connectorOptions },
  );
  const configFieldsViewEdit = buildConfigFieldsByType(
    activeCollectionType,
    { editableCollectionType: false, editableDataInstance: false, connectorOptions },
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

  const runtimeOperations = useMemo(() => {
    const fromConnector = dataConnector?.runtime_operations ?? [];
    const fallback = fallbackOperationsByCollectionType(activeCollectionType);
    const merged = [...fromConnector, ...fallback];
    const bySlug = new Map<string, RuntimeOperationRow>();
    for (const op of merged) {
      if (!op?.operation_slug) continue;
      if (!bySlug.has(op.operation_slug)) bySlug.set(op.operation_slug, op);
    }
    return Array.from(bySlug.values()).sort((a, b) => a.operation_slug.localeCompare(b.operation_slug));
  }, [activeCollectionType, dataConnector?.runtime_operations]);
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
      } else if (nextType === 'template') {
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
  const restoreMutation = useMutation({
    mutationFn: () => lifecycleApi.restoreEntity('collection', String(collection!.id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.collections.adminList() });
      queryClient.invalidateQueries({ queryKey: qk.collections.detail(String(collection!.id)) });
    },
  });

  const isDocumentCollection = collection?.collection_type === 'document';
  const isTemplateCollection = collection?.collection_type === 'template';

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

  const uploadTemplateMutation = useMutation({
    mutationFn: (file: File) =>
      collectionsApi.uploadTemplate(collection!.id, { file }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.collections.detail(collection!.id) });
      setUploading(false);
    },
    onError: () => {
      setUploading(false);
    },
  });

  const handleUploadClick = () => fileInputRef.current?.click();
  const reindexMutation = useMutation({
    mutationFn: () => collectionsApi.reindexDocuments(collection!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.collections.detail(collection!.id) });
    },
  });

  const handleReindexClick = () => {
    if (reindexMutation.isPending) return;
    reindexMutation.mutate();
  };

  const handleFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    if (isTemplateCollection) {
      uploadTemplateMutation.mutate(file);
    } else {
      uploadMutation.mutate(file);
    }
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
          actions={composeEntityActions({
            crud: buildEntityCrudActions({
              mode,
              saving,
              tone: 'default',
              labels: {
                edit: 'Изменить',
                delete: 'Удалить',
              },
              lifecycleStatus: collection?.lifecycle_status,
              onEdit: handleEdit,
              onSave: handleSave,
              onCancel: handleCancel,
              onDelete: handleDelete,
              onRestore: () => restoreMutation.mutate(),
              restorePending: restoreMutation.isPending,
            }),
            extra: mode === 'view' && (isDocumentCollection || isTemplateCollection)
              ? [
                  ...(isDocumentCollection ? [
                    <Button
                      key="reindex"
                      variant="primary"
                      onClick={handleReindexClick}
                      disabled={reindexMutation.isPending}
                    >
                      {reindexMutation.isPending ? 'Запуск...' : 'Переиндексировать'}
                    </Button>,
                  ] : []),
                  <Button
                    key="upload"
                    variant="success"
                    onClick={handleUploadClick}
                    disabled={uploading}
                  >
                    {uploading ? 'Загрузка...' : (isTemplateCollection ? 'Загрузить шаблон' : 'Загрузить файл')}
                  </Button>,
                ]
              : [],
            extraPosition: 'beforeCrud',
          })}
        >
          <Block
            title="Основная информация"
            icon="database"
            iconVariant="info"
            width="1/2"
            fields={infoFieldsViewEdit}
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

      <LifecycleDeleteDialog
        open={showDeleteConfirm}
        kind="collection"
        entityId={String(collection?.id || '')}
        entityLabel={collection?.name || 'Коллекция'}
        onCancel={() => setShowDeleteConfirm(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: qk.collections.adminList() });
          if (collection?.id) {
            queryClient.invalidateQueries({ queryKey: qk.collections.detail(collection.id) });
          }
          setShowDeleteConfirm(false);
          navigate('/admin/collections');
        }}
      />
    </>
  );
}

export default CollectionPage;
