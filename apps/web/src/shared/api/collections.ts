/**
 * Collections API client
 */
import { apiRequest } from './http';

export type SearchMode = 'exact' | 'like' | 'range' | 'vector';
export type CollectionType = 'table' | 'document' | 'sql' | 'api';

export interface BackendCollectionField {
  name: string;
  category?: 'system' | 'specific' | 'user';
  data_type:
    | 'string'
    | 'text'
    | 'integer'
    | 'float'
    | 'boolean'
    | 'datetime'
    | 'date'
    | 'enum'
    | 'json'
    | 'file';
  required: boolean;
  description?: string;
  filterable?: boolean;
  sortable?: boolean;
  used_in_retrieval?: boolean;
  used_in_prompt_context?: boolean;
}

export interface CollectionField extends Partial<BackendCollectionField> {
  name: string;
  type?: 'text' | 'integer' | 'float' | 'boolean' | 'datetime' | 'date' | 'file';
  required: boolean;
  search_modes: SearchMode[];
  description?: string;
}

export interface VectorConfig {
  chunk_strategy: 'by_tokens' | 'by_paragraphs' | 'by_sentences' | 'by_markdown';
  chunk_size: number;
  overlap: number;
}

export interface CollectionVersion {
  id: string;
  collection_id: string;
  version: number;
  status: string;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CollectionVersionCreate {
  notes?: string | null;
}

export interface CollectionVersionUpdate {
  notes?: string | null;
}

export interface CollectionTypePreset {
  collection_type: CollectionType;
  fields: BackendCollectionField[];
}

export interface CollectionTypePresetsResponse {
  items: CollectionTypePreset[];
}

export interface DiscoveredSqlTable {
  schema_name: string;
  table_name: string;
  object_type?: string;
  table_schema: Record<string, unknown>;
}

export interface DiscoverSqlTablesResponse {
  items: DiscoveredSqlTable[];
  total: number;
}

export interface DiscoveredApiEntity {
  entity_type: string;
  aliases: string[];
  examples: string[];
}

export interface DiscoverApiEntitiesResponse {
  items: DiscoveredApiEntity[];
  total: number;
}

export interface Collection {
  id: string;
  tenant_id?: string;
  collection_type: CollectionType;
  slug: string;
  name: string;
  description?: string;
  fields: CollectionField[];
  source_contract?: Record<string, unknown> | null;
  status?: string;
  status_details?: Record<string, unknown> | null;
  table_name?: string;
  table_schema?: Record<string, unknown> | null;
  data_instance_id?: string | null;
  
  // Vector search fields
  has_vector_search: boolean;
  vector_config?: VectorConfig;
  qdrant_collection_name?: string;
  
  // Vectorization statistics
  total_rows: number;
  vectorized_rows: number;
  total_chunks: number;
  failed_rows: number;
  vectorization_progress: number;
  is_fully_vectorized: boolean;
  
  is_active: boolean;
  current_version_id?: string | null;
  current_version?: CollectionVersion | null;
  created_at: string;
  updated_at: string;
  is_readonly?: boolean;
}

export interface CollectionListResponse {
  items: Collection[];
  total: number;
  page?: number;
  size?: number;
  has_more?: boolean;
}

export interface CreateCollectionRequest {
  tenant_id?: string;
  collection_type?: CollectionType;
  slug: string;
  name: string;
  description?: string;
  fields: CollectionField[];
  vector_config?: VectorConfig;
  table_schema?: Record<string, unknown> | null;
  data_instance_id?: string | null;
}

export interface SchemaOperation {
  op: 'add' | 'alter' | 'rename' | 'remove';
  name?: string;
  new_name?: string;
  field?: BackendCollectionField;
}

export interface UpdateCollectionRequest {
  name?: string;
  description?: string | null;
  is_active?: boolean;
  data_instance_id?: string | null;
  table_name?: string | null;
  table_schema?: Record<string, unknown> | null;
  schema_ops?: SchemaOperation[];
}

export interface CollectionDataResponse {
  items: Record<string, unknown>[];
  total: number;
  limit: number;
  offset: number;
}

export interface RowMutationRequest {
  data: Record<string, unknown>;
}

export interface CollectionRowMutationResponse {
  item: Record<string, unknown>;
  vectorization_task_id?: string | null;
}

export interface UploadDocumentRequest {
  file: File;
  title?: string;
  source?: string;
  scope?: string;
  tags?: string[];
  auto_ingest?: boolean;
}

export interface UploadDocumentResponse {
  doc_id: string;
  row_id: string;
  collection_id: string;
  status: string;
  message: string;
}

export interface CollectionDocument {
  id: string;
  name: string;
  filename: string;
  status: string;
  agg_status: string;
  scope: string;
  tags: string[];
  size_bytes: number | null;
  content_type: string | null;
  created_at: string | null;
  updated_at: string | null;
  collection_row_id: string | null;
  title: string | null;
  source: string | null;
  doc_scope: string | null;
  s3_key: string | null;
  document?: Record<string, unknown>;
  collection?: Record<string, unknown>;
  artifacts?: Record<string, { key?: string; content_type?: string; format?: string; available?: boolean }>;
  meta_fields: Record<string, unknown>;
}

export interface CollectionDocumentsResponse {
  items: CollectionDocument[];
  total: number;
  page: number;
  size: number;
  has_more: boolean;
}

export interface DocumentUploadPolicy {
  max_bytes: number;
  allowed_extensions: string[];
  allowed_content_types_by_extension: Record<string, string[]>;
}

export interface CSVPreviewResponse {
  columns: string[];
  matched_columns: string[];
  unmatched_columns: string[];
  missing_required: string[];
  sample_rows: Record<string, unknown>[];
  total_rows: number;
  can_upload: boolean;
}

export interface CSVUploadResponse {
  inserted_rows: number;
  errors: Array<{ row: number; field: string; message: string }>;
  total_rows: number;
}

function normalizeCollectionType(type?: CollectionType): CollectionType {
  if (type === 'document') return 'document';
  if (type === 'sql') return 'sql';
  if (type === 'api') return 'api';
  return 'table';
}

function inferSearchModes(field: BackendCollectionField): SearchMode[] {
  const modes: SearchMode[] = [];
  if (field.filterable) {
    if (field.data_type === 'text' || field.data_type === 'string') {
      modes.push('exact', 'like');
    } else {
      modes.push('exact');
    }
  }
  if (field.sortable) {
    modes.push('range');
  }
  if (field.used_in_retrieval) {
    modes.push('vector');
  }
  return Array.from(new Set(modes));
}

function toBackendField(field: CollectionField): BackendCollectionField {
  const searchModes = field.search_modes ?? [];
  const dataType = field.data_type ?? field.type ?? 'text';

  return {
    name: field.name,
    category: field.category ?? 'user',
    data_type: dataType,
    required: field.required,
    description: field.description,
    filterable:
      field.filterable ??
      (searchModes.includes('exact') || searchModes.includes('like')),
    sortable: field.sortable ?? searchModes.includes('range'),
    used_in_retrieval: field.used_in_retrieval ?? searchModes.includes('vector'),
    used_in_prompt_context: field.used_in_prompt_context ?? false,
  };
}

function toFrontendField(field: CollectionField | BackendCollectionField): CollectionField {
  const normalized = field as BackendCollectionField;
  return {
    ...normalized,
    type:
      normalized.data_type === 'string' ||
      normalized.data_type === 'json' ||
      normalized.data_type === 'enum'
        ? 'text'
        : normalized.data_type,
    search_modes:
      'search_modes' in field && Array.isArray((field as CollectionField).search_modes)
        ? (field as CollectionField).search_modes
        : inferSearchModes(normalized),
  };
}

function toFrontendCollection(collection: Collection): Collection {
  const normalizedType = normalizeCollectionType(collection.collection_type);
  return {
    ...collection,
    collection_type: normalizedType,
    is_readonly: normalizedType === 'sql' || normalizedType === 'api',
    fields: Array.isArray(collection.fields)
      ? collection.fields.map((field) => toFrontendField(field))
      : [],
  };
}

export const collectionsApi = {
  // Admin endpoints (require admin role)
  listAll: async (params?: {
    page?: number;
    size?: number;
    tenant_id?: string;
    is_active?: boolean;
  }): Promise<CollectionListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.size) searchParams.set('size', String(params.size));
    if (params?.tenant_id) searchParams.set('tenant_id', params.tenant_id);
    if (params?.is_active !== undefined)
      searchParams.set('is_active', String(params.is_active));

    const query = searchParams.toString();
    const response = await apiRequest<CollectionListResponse>(
      `/admin/collections${query ? `?${query}` : ''}`
    );
    return {
      ...response,
      items: response.items.map((item) => toFrontendCollection(item)),
    };
  },

  getById: async (id: string): Promise<Collection> => {
    const collection = await apiRequest<Collection>(`/admin/collections/${id}`);
    return toFrontendCollection(collection);
  },

  getTypePresets: async (): Promise<CollectionTypePresetsResponse> => {
    return apiRequest<CollectionTypePresetsResponse>('/admin/collections/type-presets');
  },

  create: async (data: CreateCollectionRequest): Promise<Collection> => {
    const created = await apiRequest<Collection>('/admin/collections', {
      method: 'POST',
      body: {
        ...data,
        collection_type: normalizeCollectionType(data.collection_type),
        fields: (data.fields ?? []).map((field) => toBackendField(field)),
      },
    });
    return toFrontendCollection(created);
  },

  delete: async (
    id: string,
    dropTable = true
  ): Promise<void> => {
    await apiRequest(`/admin/collections/${id}?drop_table=${dropTable}`, {
      method: 'DELETE',
    });
  },

  update: async (
    id: string,
    data: UpdateCollectionRequest
  ): Promise<Collection> => {
    const updated = await apiRequest<Collection>(`/admin/collections/${id}`, {
      method: 'PUT',
      body: data,
    });
    return toFrontendCollection(updated);
  },

  getSchema: async (
    id: string
  ): Promise<{ slug: string; name: string; description: string; input_schema: object }> => {
    return apiRequest(`/admin/collections/${id}/schema`);
  },

  discoverSqlTables: async (collectionId: string): Promise<DiscoverSqlTablesResponse> => {
    return apiRequest<DiscoverSqlTablesResponse>(`/admin/collections/${collectionId}/discover-tables`, {
      method: 'POST',
    });
  },

  discoverApiEntities: async (collectionId: string): Promise<DiscoverApiEntitiesResponse> => {
    return apiRequest<DiscoverApiEntitiesResponse>(`/admin/collections/${collectionId}/discover-entities`, {
      method: 'POST',
    });
  },

  listVersions: async (collectionId: string): Promise<CollectionVersion[]> => {
    return apiRequest<CollectionVersion[]>(`/admin/collections/${collectionId}/versions`);
  },

  getVersion: async (collectionId: string, version: number): Promise<CollectionVersion> => {
    return apiRequest<CollectionVersion>(`/admin/collections/${collectionId}/versions/${version}`);
  },

  createVersion: async (
    collectionId: string,
    data: CollectionVersionCreate,
  ): Promise<CollectionVersion> => {
    return apiRequest<CollectionVersion>(`/admin/collections/${collectionId}/versions`, {
      method: 'POST',
      body: data,
    });
  },

  updateVersion: async (
    collectionId: string,
    version: number,
    data: CollectionVersionUpdate,
  ): Promise<CollectionVersion> => {
    return apiRequest<CollectionVersion>(`/admin/collections/${collectionId}/versions/${version}`, {
      method: 'PATCH',
      body: data,
    });
  },

  activateVersion: async (
    collectionId: string,
    version: number,
  ): Promise<CollectionVersion> => {
    return apiRequest<CollectionVersion>(`/admin/collections/${collectionId}/versions/${version}/publish`, {
      method: 'POST',
    });
  },

  setCurrentVersion: async (collectionId: string, versionId: string): Promise<Collection> => {
    return apiRequest<Collection>(`/admin/collections/${collectionId}/current-version?version_id=${versionId}`, {
      method: 'PUT',
    });
  },

  deactivateVersion: async (
    collectionId: string,
    version: number,
  ): Promise<CollectionVersion> => {
    return apiRequest<CollectionVersion>(`/admin/collections/${collectionId}/versions/${version}/archive`, {
      method: 'POST',
    });
  },

  deleteVersion: async (
    collectionId: string,
    version: number,
  ): Promise<void> => {
    await apiRequest(`/admin/collections/${collectionId}/versions/${version}`, {
      method: 'DELETE',
    });
  },

  uploadDocument: async (
    collectionId: string,
    data: UploadDocumentRequest
  ): Promise<UploadDocumentResponse> => {
    const formData = new FormData();
    formData.append('file', data.file);
    if (data.title) formData.append('title', data.title);
    if (data.source) formData.append('source', data.source);
    if (data.scope) formData.append('scope', data.scope);
    if (data.tags?.length) formData.append('tags', JSON.stringify(data.tags));
    if (data.auto_ingest !== undefined) formData.append('auto_ingest', String(data.auto_ingest));

    return apiRequest<UploadDocumentResponse>(
      `/collections/${collectionId}/upload-document`,
      { method: 'POST', body: formData }
    );
  },

  // Tenant-level endpoints
  list: async (activeOnly = true): Promise<CollectionListResponse> => {
    const response = await apiRequest<CollectionListResponse>(
      `/collections/?active_only=${activeOnly}`
    );
    return {
      ...response,
      items: response.items.map((item) => toFrontendCollection(item)),
    };
  },

  getBySlug: async (slug: string): Promise<Collection> => {
    const collection = await apiRequest<Collection>(`/collections/${slug}`);
    return toFrontendCollection(collection);
  },

  // CSV operations
  previewCSV: async (
    slug: string,
    file: File,
    options?: { encoding?: string; delimiter?: string }
  ): Promise<CSVPreviewResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const params = new URLSearchParams();
    if (options?.encoding) params.set('encoding', options.encoding);
    if (options?.delimiter) params.set('delimiter', options.delimiter);

    const query = params.toString();
    return apiRequest<CSVPreviewResponse>(
      `/collections/${slug}/preview${query ? `?${query}` : ''}`,
      {
        method: 'POST',
        body: formData,
      }
    );
  },

  uploadCSV: async (
    slug: string,
    file: File,
    options?: { encoding?: string; delimiter?: string; skip_errors?: boolean }
  ): Promise<CSVUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const params = new URLSearchParams();
    if (options?.encoding) params.set('encoding', options.encoding);
    if (options?.delimiter) params.set('delimiter', options.delimiter);
    if (options?.skip_errors !== undefined)
      params.set('skip_errors', String(options.skip_errors));

    const query = params.toString();
    return apiRequest<CSVUploadResponse>(
      `/collections/${slug}/upload${query ? `?${query}` : ''}`,
      {
        method: 'POST',
        body: formData,
      }
    );
  },

  getData: async (
    slug: string,
    params?: { limit?: number; offset?: number; search?: string; tenant_id?: string }
  ): Promise<CollectionDataResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    if (params?.search) searchParams.set('search', params.search);
    if (params?.tenant_id) searchParams.set('tenant_id', params.tenant_id);

    const query = searchParams.toString();
    return apiRequest<CollectionDataResponse>(`/collections/${slug}/data${query ? `?${query}` : ''}`);
  },

  createRow: async (
    slug: string,
    data: RowMutationRequest,
    tenantId?: string
  ): Promise<CollectionRowMutationResponse> => {
    const searchParams = new URLSearchParams();
    if (tenantId) searchParams.set('tenant_id', tenantId);
    const query = searchParams.toString();
    return apiRequest<CollectionRowMutationResponse>(`/collections/${slug}/rows${query ? `?${query}` : ''}`, {
      method: 'POST',
      body: data,
    });
  },

  updateRow: async (
    slug: string,
    rowId: string,
    data: RowMutationRequest,
    tenantId?: string
  ): Promise<CollectionRowMutationResponse> => {
    const searchParams = new URLSearchParams();
    if (tenantId) searchParams.set('tenant_id', tenantId);
    const query = searchParams.toString();
    return apiRequest<CollectionRowMutationResponse>(`/collections/${slug}/rows/${rowId}${query ? `?${query}` : ''}`, {
      method: 'PATCH',
      body: data,
    });
  },

  deleteRows: async (
    slug: string,
    ids: string[],
    tenantId?: string
  ): Promise<{ deleted: number; ids: number[] }> => {
    const params = new URLSearchParams();
    ids.forEach(id => params.append('ids', String(id)));
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/collections/${slug}/data?${params.toString()}`, {
      method: 'DELETE',
    });
  },

  downloadTemplate: (slug: string): string => {
    return `/api/v1/collections/${slug}/template`;
  },

  // Document-type collection endpoints
  getDocumentUploadPolicy: async (): Promise<DocumentUploadPolicy> => {
    return apiRequest<DocumentUploadPolicy>('/collections/uploads/document-policy');
  },

  listDocuments: async (
    collectionId: string,
    params?: { page?: number; size?: number; status?: string }
  ): Promise<CollectionDocumentsResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.size) searchParams.set('size', String(params.size));
    if (params?.status) searchParams.set('status', params.status);
    const query = searchParams.toString();
    return apiRequest<CollectionDocumentsResponse>(
      `/collections/${collectionId}/documents${query ? `?${query}` : ''}`
    );
  },

  deleteDocuments: async (
    collectionId: string,
    docIds: string[]
  ): Promise<{ deleted: number; collection_id: string }> => {
    const params = new URLSearchParams();
    docIds.forEach(id => params.append('ids', id));
    return apiRequest(`/collections/${collectionId}/documents?${params.toString()}`, {
      method: 'DELETE',
    });
  },

  // Document status & ingest (scoped to collection, not RAG)
  getDocStatusGraph: async (collectionId: string, docId: string) => {
    return apiRequest(`/collections/${collectionId}/docs/${docId}/status-graph`);
  },

  startDocIngest: async (
    collectionId: string,
    docId: string
  ): Promise<{ status: string; message: string; document_id: string; embedding_models: string[] }> => {
    return apiRequest(`/collections/${collectionId}/docs/${docId}/ingest/start`, {
      method: 'POST',
    });
  },

  stopDocIngest: async (
    collectionId: string,
    docId: string,
    stage: string
  ): Promise<{ status: string; message: string; document_id: string; stage: string }> => {
    return apiRequest(`/collections/${collectionId}/docs/${docId}/ingest/stop?stage=${stage}`, {
      method: 'POST',
    });
  },

  retryDocIngest: async (
    collectionId: string,
    docId: string,
    stage: string
  ): Promise<{ status: string; message: string; document_id: string; stage: string }> => {
    return apiRequest(`/collections/${collectionId}/docs/${docId}/ingest/retry?stage=${stage}`, {
      method: 'POST',
    });
  },

  downloadDocFile: async (
    collectionId: string,
    docId: string,
    kind: 'original' | 'canonical' = 'original'
  ): Promise<{ url: string }> => {
    return apiRequest(`/collections/${collectionId}/docs/${docId}/download?kind=${kind}`);
  },

  getStatusEventsUrl: (collectionId: string, docId?: string): string => {
    const base = `/api/v1/collections/${collectionId}/status/events`;
    return docId ? `${base}?document_id=${encodeURIComponent(docId)}` : base;
  },
};

export default collectionsApi;
