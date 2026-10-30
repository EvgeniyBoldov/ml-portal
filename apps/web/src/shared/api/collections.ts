/**
 * Collections API client
 */
import { apiRequest } from './http';

export type SearchMode = 'exact' | 'like' | 'range' | 'vector';
export type CollectionType = 'table' | 'document' | 'sql' | 'api' | 'template';

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
  type?: BackendCollectionField['data_type'];
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
  data_description?: string | null;
  usage_purpose?: string | null;
  usage_rules?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DataInstanceShort {
  id: string;
  slug: string;
  name: string;
}

export interface CollectionSource {
  name: string;
  type: string;
}

export interface PublishedCollectionVersionInfo {
  number: number;
  status: 'published';
}

export interface CollectionCount {
  value: number | null;
  kind: string | null;
  unit: string | null;
}

export interface CollectionWorkspace {
  id: string;
  name: string;
}

export interface CollectionWorkspacesResponse {
  items: CollectionWorkspace[];
}

export interface CollectionCapabilities {
  view_content: boolean;
  view_schema: boolean;
  can_edit_content: boolean;
  upload_documents: boolean;
  delete_documents: boolean;
  ingest: boolean;
  manage_memory: boolean;
  upload_csv: boolean;
  mutate_rows: boolean;
  reindex: boolean;
  upload_templates: boolean;
  analyze_templates: boolean;
  approve_templates: boolean;
  edit_templates: boolean;
  delete_templates: boolean;
  download: boolean;
}

export interface CollectionVersionCreate {
  data_description?: string | null;
  usage_purpose?: string | null;
  usage_rules?: string | null;
  notes?: string | null;
}

export interface CollectionVersionUpdate {
  data_description?: string | null;
  usage_purpose?: string | null;
  usage_rules?: string | null;
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
  fields: CollectionField[];
  source_contract?: Record<string, unknown> | null;
  status?: string;
  readiness?: { status: string };
  status_details?: Record<string, unknown> | null;
  deprecated_at?: string | null;
  retention_days?: number;
  table_name?: string;
  table_schema?: Record<string, unknown> | null;
  data_instance_id: string;
  data_instance?: DataInstanceShort | null;
  source?: CollectionSource | null;
  description?: string | null;
  purpose?: string | null;
  version?: PublishedCollectionVersionInfo | null;
  count?: CollectionCount | null;
  capabilities?: CollectionCapabilities;
  capability_reasons?: Record<string, string>;
  
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
  memory_enabled?: boolean;
  lifecycle_status?: string;
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

export interface GlossaryCatalogTerm {
  canonical_term: string;
  aliases: string[];
  description: string;
  updated_at: string;
  source_document_id: string | null;
  source_document_title: string | null;
  source_section_ids: string[];
}

export interface GlossaryOverviewResponse {
  entries: GlossaryCatalogTerm[];
  total: number;
  limit?: number;
  offset?: number;
}

export interface CollectionCapabilityTool {
  operation: string;
  title: string;
  description: string;
  source: string;
  provider: string;
}

export interface CollectionCapabilitiesResponse {
  collection_id: string;
  collection_slug: string;
  collection_type?: CollectionType;
  status?: string;
  tools: CollectionCapabilityTool[];
}

export interface CreateCollectionRequest {
  tenant_id?: string;
  collection_type?: CollectionType;
  slug?: string;
  name: string;
  fields: CollectionField[];
  vector_config?: VectorConfig;
  table_schema?: Record<string, unknown> | null;
  data_instance_id?: string;
  memory_enabled?: boolean;
}

export interface SchemaOperation {
  op: 'add' | 'alter' | 'rename' | 'remove';
  name?: string;
  new_name?: string;
  field?: BackendCollectionField;
}

export interface UpdateCollectionRequest {
  tenant_id?: string | null;
  name?: string;
  is_active?: boolean;
  memory_enabled?: boolean;
  vector_config?: VectorConfig | null;
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
  meta_fields?: Record<string, unknown>;
  auto_ingest?: boolean;
  memory_enabled?: boolean;
  memory_scope_keys?: string[];
  project_keys?: string[];
}

export interface UploadDocumentResponse {
  doc_id: string;
  row_id: string;
  collection_id: string;
  status: string;
  message: string;
}

export interface UploadTemplateRequest {
  file: File;
}

export interface UploadTemplateResponse {
  row_id: string;
  file_id?: string;
  collection_id: string;
  status?: string;
  message?: string;
  title?: string;
  source?: string;
  template_version?: string;
  description?: string;
  draft_schema?: Record<string, unknown>;
  description_task_id?: string;
  schema_task_id?: string;
}

export interface CollectionTemplate {
  id: string;
  file?: Record<string, unknown>;
  title?: string | null;
  source?: string | null;
  template_version?: string | null;
  template_schema?: Record<string, unknown> | null;
  description?: string | null;
  status?: string | null;
  runtime_status?: 'uploaded' | 'processing' | 'approval_required' | 'ready' | 'failed' | 'archived' | null;
  runtime_stage?: 'upload' | 'schema' | 'description' | 'approval' | 'vectorization' | 'indexing' | 'done' | null;
  status_reason?: string | null;
  approval_required?: boolean;
  approved_at?: string | null;
  approved_by?: string | null;
  approved_by_name?: string | null;
  has_error?: boolean;
  error_message?: string | null;
  vectorization_status?: string | null;
  indexing_status?: string | null;
}

export interface UpdateTemplateRequest {
  description?: string | null;
}

export interface CollectionTemplatesResponse {
  items: CollectionTemplate[];
  total: number;
  page: number;
  size: number;
}

export interface ApproveTemplateResponse {
  item: CollectionTemplate;
  vectorization_task_id?: string | null;
}

export interface AnalyzeTemplatesResponse {
  collection_id: string;
  queued: number;
  missing: string[];
  items: Array<{
    row_id: string;
    description_task_id: string;
    schema_task_id: string;
  }>;
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
  memory?: {
    policy: 'collection' | 'explicit';
    enabled: boolean | null;
    effective_enabled: boolean;
    project_keys: string[];
    scope_keys?: string[];
    extraction_status: string;
    extraction_metrics: Record<string, unknown>;
  };
  artifacts?: Record<string, {
    key?: string;
    content_type?: string;
    format?: string;
    available?: boolean;
    chunk_count?: number;
  }>;
  meta_fields: Record<string, unknown>;
}

export interface CollectionDocumentsResponse {
  items: CollectionDocument[];
  total: number;
  page: number;
  size: number;
  has_more: boolean;
  stats?: { total: number; ready: number; processing: number; partial: number; failed: number; uploaded: number; archived: number };
}

export interface CollectionReindexResponse {
  status: string;
  collection_id: string;
  total: number;
  queued: number;
  skipped: number;
  failed: number;
  items: Array<{
    document_id: string;
    status: 'queued' | 'skipped' | 'failed';
    reason?: string;
    error?: string;
  }>;
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
  if (type === 'template') return 'template';
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
  if (field.sortable && field.data_type !== 'file' && field.data_type !== 'json') {
    modes.push('range');
  }
  if (field.used_in_retrieval && field.data_type === 'text') {
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
    filterable: field.filterable ?? (searchModes.includes('exact') || searchModes.includes('like')),
    sortable: field.sortable ?? searchModes.includes('range'),
    used_in_retrieval: field.used_in_retrieval ?? searchModes.includes('vector'),
    used_in_prompt_context: field.used_in_prompt_context ?? false,
  };
}

function toFrontendField(field: CollectionField | BackendCollectionField): CollectionField {
  const normalized = field as BackendCollectionField;
  return {
    ...normalized,
    type: normalized.data_type,
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
  listWorkspaces: async (): Promise<CollectionWorkspacesResponse> =>
    apiRequest<CollectionWorkspacesResponse>('/collections/workspaces'),

  // Admin endpoints (require admin role)
  listAll: async (params?: {
    page?: number;
    size?: number;
    tenant_id?: string;
    is_active?: boolean;
    include_deprecated?: boolean;
    search?: string;
  }): Promise<CollectionListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.size) searchParams.set('size', String(params.size));
    if (params?.tenant_id) searchParams.set('tenant_id', params.tenant_id);
    if (params?.is_active !== undefined)
      searchParams.set('is_active', String(params.is_active));
    if (params?.include_deprecated !== undefined)
      searchParams.set('include_deprecated', String(params.include_deprecated));
    if (params?.search?.trim()) searchParams.set('search', params.search.trim());

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

  getCapabilities: async (id: string): Promise<CollectionCapabilitiesResponse> => {
    return apiRequest<CollectionCapabilitiesResponse>(`/admin/collections/${id}/capabilities`);
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
    const schemaOps = (data.schema_ops ?? []).map((op) => (
      op.field
        ? { ...op, field: toBackendField(op.field as CollectionField) }
        : op
    ));
    const updated = await apiRequest<Collection>(`/admin/collections/${id}`, {
      method: 'PUT',
      body: {
        ...data,
        schema_ops: schemaOps,
      },
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
    data: UploadDocumentRequest,
    tenantId?: string,
  ): Promise<UploadDocumentResponse> => {
    const formData = new FormData();
    formData.append('file', data.file);
    if (data.title) formData.append('title', data.title);
    if (data.source) formData.append('source', data.source);
    if (data.scope) formData.append('scope', data.scope);
    if (data.tags?.length) formData.append('tags', JSON.stringify(data.tags));
    if (data.meta_fields && Object.keys(data.meta_fields).length > 0) formData.append('meta_fields', JSON.stringify(data.meta_fields));
    if (data.auto_ingest !== undefined) formData.append('auto_ingest', String(data.auto_ingest));
    if (data.memory_enabled !== undefined) formData.append('memory_enabled', String(data.memory_enabled));
    if (data.memory_scope_keys?.length) formData.append('memory_scope_keys', JSON.stringify(data.memory_scope_keys));
    if (data.project_keys?.length) formData.append('project_keys', JSON.stringify(data.project_keys));

    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest<UploadDocumentResponse>(
      `/collections/${collectionId}/upload-document${params.size ? `?${params}` : ''}`,
      { method: 'POST', body: formData }
    );
  },

  uploadTemplate: async (
    collectionId: string,
    data: UploadTemplateRequest,
    tenantId?: string,
  ): Promise<UploadTemplateResponse> => {
    const formData = new FormData();
    formData.append('file', data.file);

    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest<UploadTemplateResponse>(
      `/collections/${collectionId}/templates/upload${params.size ? `?${params}` : ''}`,
      { method: 'POST', body: formData }
    );
  },

  listTemplates: async (
    collectionId: string,
    params?: { page?: number; size?: number; query?: string; tenant_id?: string }
  ): Promise<CollectionTemplatesResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.size) searchParams.set('size', String(params.size));
    if (params?.query) searchParams.set('query', params.query);
    if (params?.tenant_id) searchParams.set('tenant_id', params.tenant_id);
    const query = searchParams.toString();
    return apiRequest<CollectionTemplatesResponse>(
      `/collections/${collectionId}/templates${query ? `?${query}` : ''}`
    );
  },

  getTemplate: async (
    collectionId: string,
    rowId: string,
    tenantId?: string,
  ): Promise<CollectionTemplate> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest<CollectionTemplate>(`/collections/${collectionId}/templates/${rowId}${params.size ? `?${params}` : ''}`);
  },

  getTemplateDownload: async (collectionId: string, rowId: string, tenantId?: string): Promise<{ download_url: string }> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest<{ download_url: string }>(`/collections/${collectionId}/templates/${rowId}/download${params.size ? `?${params}` : ''}`);
  },

  getTemplateStatusGraph: async (
    collectionId: string,
    rowId: string,
    tenantId?: string,
  ): Promise<Record<string, unknown>> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest<Record<string, unknown>>(`/collections/${collectionId}/templates/${rowId}/status-graph${params.size ? `?${params}` : ''}`);
  },

  updateTemplate: async (
    collectionId: string,
    rowId: string,
    data: UpdateTemplateRequest,
    tenantId?: string,
  ): Promise<CollectionTemplate> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest<CollectionTemplate>(`/collections/${collectionId}/templates/${rowId}${params.size ? `?${params}` : ''}`, {
      method: 'PATCH',
      body: data,
    });
  },

  analyzeTemplates: async (
    collectionId: string,
    rowIds: string[],
    tenantId?: string,
  ): Promise<AnalyzeTemplatesResponse> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest<AnalyzeTemplatesResponse>(`/collections/${collectionId}/templates/analyze${params.size ? `?${params}` : ''}`, {
      method: 'POST',
      body: { row_ids: rowIds },
    });
  },

  getTemplateStatusEventsUrl: (collectionId: string, rowId: string, tenantId?: string): string =>
    `/api/v1/collections/${collectionId}/templates/${encodeURIComponent(rowId)}/status/events${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`,

  getTemplateCollectionStatusEventsUrl: (collectionId: string, tenantId?: string): string =>
    `/api/v1/collections/${collectionId}/templates/status/events${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`,

  approveTemplate: async (
    collectionId: string,
    rowId: string,
    tenantId?: string,
  ): Promise<ApproveTemplateResponse> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest<ApproveTemplateResponse>(`/collections/${collectionId}/templates/${rowId}/approve${params.size ? `?${params}` : ''}`, {
      method: 'POST',
      body: {},
    });
  },

  // Tenant-level endpoints
  list: async (activeOnly = true, tenantId?: string): Promise<CollectionListResponse> => {
    const params = new URLSearchParams({ active_only: String(activeOnly) });
    if (tenantId) params.set('tenant_id', tenantId);
    const response = await apiRequest<CollectionListResponse>(
      `/collections/?${params.toString()}`
    );
    return {
      ...response,
      items: response.items.map((item) => toFrontendCollection(item)),
    };
  },

  getBySlug: async (slug: string, tenantId?: string): Promise<Collection> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    const query = params.toString();
    const collection = await apiRequest<Collection>(`/collections/${slug}${query ? `?${query}` : ''}`);
    return toFrontendCollection(collection);
  },

  getGlossaryOverview: async (params?: { query?: string; limit?: number; offset?: number }): Promise<GlossaryOverviewResponse> => {
    const search = new URLSearchParams();
    if (params?.query) search.set('query', params.query);
    if (params?.limit !== undefined) search.set('limit', String(params.limit));
    if (params?.offset !== undefined) search.set('offset', String(params.offset));
    return apiRequest<GlossaryOverviewResponse>(`/collections/glossary${search.toString() ? `?${search}` : ''}`);
  },

  // CSV operations
  previewCSV: async (
    slug: string,
    file: File,
    options?: { encoding?: string; delimiter?: string; tenant_id?: string }
  ): Promise<CSVPreviewResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const params = new URLSearchParams();
    if (options?.encoding) params.set('encoding', options.encoding);
    if (options?.delimiter) params.set('delimiter', options.delimiter);
    if (options?.tenant_id) params.set('tenant_id', options.tenant_id);

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
    options?: { encoding?: string; delimiter?: string; skip_errors?: boolean; tenant_id?: string }
  ): Promise<CSVUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const params = new URLSearchParams();
    if (options?.encoding) params.set('encoding', options.encoding);
    if (options?.delimiter) params.set('delimiter', options.delimiter);
    if (options?.skip_errors !== undefined)
      params.set('skip_errors', String(options.skip_errors));
    if (options?.tenant_id) params.set('tenant_id', options.tenant_id);

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

  deleteTemplates: async (
    collectionId: string,
    ids: string[],
    tenantId?: string,
  ): Promise<{ deleted: number; ids: string[] }> => {
    const params = new URLSearchParams();
    ids.forEach((id) => params.append('ids', id));
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/collections/${collectionId}/templates?${params.toString()}`, {
      method: 'DELETE',
    });
  },

  downloadTemplate: (slug: string, tenantId?: string): string => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return `/api/v1/collections/${slug}/template${params.size ? `?${params}` : ''}`;
  },

  // Document-type collection endpoints
  getDocumentUploadPolicy: async (): Promise<DocumentUploadPolicy> => {
    return apiRequest<DocumentUploadPolicy>('/collections/uploads/document-policy');
  },

  listDocuments: async (
    collectionId: string,
    params?: { page?: number; size?: number; status?: string; query?: string; tenant_id?: string }
  ): Promise<CollectionDocumentsResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.size) searchParams.set('size', String(params.size));
    if (params?.status) searchParams.set('status', params.status);
    if (params?.query) searchParams.set('query', params.query);
    if (params?.tenant_id) searchParams.set('tenant_id', params.tenant_id);
    const query = searchParams.toString();
    return apiRequest<CollectionDocumentsResponse>(
      `/collections/${collectionId}/documents${query ? `?${query}` : ''}`
    );
  },

  deleteDocuments: async (
    collectionId: string,
    docIds: string[],
    tenantId?: string,
  ): Promise<{ deleted: number; collection_id: string }> => {
    const params = new URLSearchParams();
    docIds.forEach(id => params.append('ids', id));
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/collections/${collectionId}/documents?${params.toString()}`, {
      method: 'DELETE',
    });
  },

  reindexDocuments: async (collectionId: string, tenantId?: string): Promise<CollectionReindexResponse> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest<CollectionReindexResponse>(`/collections/${collectionId}/reindex${params.size ? `?${params}` : ''}`, {
      method: 'POST',
    });
  },

  // Document status & ingest (scoped to collection, not RAG)
  addDocumentToMemory: async (collectionId: string, docId: string, tenantId?: string): Promise<{ status: string; operation_id: string }> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/collections/${collectionId}/docs/${docId}/memory${params.size ? `?${params}` : ''}`, { method: 'POST' });
  },

  removeDocumentFromMemory: async (collectionId: string, docId: string, tenantId?: string): Promise<{ status: string; operation_id: string }> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/collections/${collectionId}/docs/${docId}/memory${params.size ? `?${params}` : ''}`, { method: 'DELETE' });
  },

  getDocStatusGraph: async (collectionId: string, docId: string, tenantId?: string) => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/collections/${collectionId}/docs/${docId}/status-graph${params.size ? `?${params}` : ''}`);
  },

  startDocIngest: async (
    collectionId: string,
    docId: string,
    tenantId?: string,
  ): Promise<{ status: string; message: string; document_id: string; embedding_models: string[] }> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/collections/${collectionId}/docs/${docId}/ingest/start${params.size ? `?${params}` : ''}`, {
      method: 'POST',
    });
  },

  stopDocIngest: async (
    collectionId: string,
    docId: string,
    stage: string,
    tenantId?: string,
  ): Promise<{ status: string; message: string; document_id: string; stage: string }> => {
    const params = new URLSearchParams({ stage });
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/collections/${collectionId}/docs/${docId}/ingest/stop?${params}`, {
      method: 'POST',
    });
  },

  retryDocIngest: async (
    collectionId: string,
    docId: string,
    stage: string,
    tenantId?: string,
  ): Promise<{ status: string; message: string; document_id: string; stage: string }> => {
    const params = new URLSearchParams({ stage });
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/collections/${collectionId}/docs/${docId}/ingest/retry?${params}`, {
      method: 'POST',
    });
  },

  downloadDocFile: async (
    collectionId: string,
    docId: string,
    kind: 'original' | 'canonical' = 'original'
  ): Promise<{ file_id: string; download_url: string }> => {
    return apiRequest(`/collections/${collectionId}/docs/${docId}/download?kind=${kind}`);
  },

  startCsvExport: async (
    slug: string,
    tenantId?: string,
  ): Promise<{ export_id: string; status: string; task_id: string; expires_in: number }> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/collections/${slug}/export${params.size ? `?${params}` : ''}`, {
      method: 'POST',
    });
  },

  getCsvExportStatus: async (
    slug: string,
    exportId: string,
    tenantId?: string,
  ): Promise<{
    export_id: string;
    status: string;
    file_id?: string;
    download_url?: string;
    file_name?: string;
    content_type?: string;
    size_bytes?: number;
    expires_at?: string;
    error?: string;
  }> => {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/collections/${slug}/export/${exportId}${params.size ? `?${params}` : ''}`);
  },

  getStatusEventsUrl: (collectionId: string, tenantId?: string): string =>
    `/api/v1/collections/${collectionId}/status/events${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`,

  getDocumentStatusEventsUrl: (collectionId: string, docId: string, tenantId?: string): string =>
    `/api/v1/collections/${collectionId}/docs/${encodeURIComponent(docId)}/status/events${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`,
};

export default collectionsApi;
