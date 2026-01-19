/**
 * Collections API client
 */
import { apiRequest } from './http';

export interface CollectionField {
  name: string;
  type: 'text' | 'integer' | 'float' | 'boolean' | 'datetime' | 'date';
  required: boolean;
  searchable: boolean;
  search_mode?: 'exact' | 'like' | 'range';
  description?: string;
}

export interface Collection {
  id: string;
  tenant_id?: string;
  slug: string;
  name: string;
  description?: string;
  type: 'sql' | 'vector' | 'hybrid';
  fields: CollectionField[];
  row_count: number;
  table_name?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CollectionListResponse {
  items: Collection[];
  total: number;
  page?: number;
  size?: number;
  has_more?: boolean;
}

export interface CreateCollectionRequest {
  tenant_id: string;
  slug: string;
  name: string;
  description?: string;
  type?: 'sql' | 'vector' | 'hybrid';
  fields: CollectionField[];
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
    return apiRequest<CollectionListResponse>(
      `/admin/collections${query ? `?${query}` : ''}`
    );
  },

  getById: async (id: string): Promise<Collection> => {
    return apiRequest<Collection>(`/admin/collections/${id}`);
  },

  create: async (data: CreateCollectionRequest): Promise<Collection> => {
    return apiRequest<Collection>('/admin/collections', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  delete: async (
    id: string,
    dropTable = true
  ): Promise<{ status: string; id: string; table_dropped: boolean }> => {
    return apiRequest(`/admin/collections/${id}?drop_table=${dropTable}`, {
      method: 'DELETE',
    });
  },

  getSchema: async (
    id: string
  ): Promise<{ slug: string; name: string; description: string; input_schema: object }> => {
    return apiRequest(`/admin/collections/${id}/schema`);
  },

  // Tenant-level endpoints
  list: async (activeOnly = true): Promise<CollectionListResponse> => {
    return apiRequest<CollectionListResponse>(
      `/collections/?active_only=${activeOnly}`
    );
  },

  getBySlug: async (slug: string): Promise<Collection> => {
    return apiRequest<Collection>(`/collections/${slug}`);
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
    params?: { limit?: number; offset?: number; search?: string }
  ): Promise<{ items: Record<string, unknown>[]; total: number; limit: number; offset: number }> => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    if (params?.search) searchParams.set('search', params.search);

    const query = searchParams.toString();
    return apiRequest(`/collections/${slug}/data${query ? `?${query}` : ''}`);
  },

  deleteRows: async (
    slug: string,
    ids: number[]
  ): Promise<{ deleted: number; ids: number[] }> => {
    const params = new URLSearchParams();
    ids.forEach(id => params.append('ids', String(id)));
    return apiRequest(`/collections/${slug}/data?${params.toString()}`, {
      method: 'DELETE',
    });
  },

  downloadTemplate: (slug: string): string => {
    return `/api/v1/collections/${slug}/template`;
  },
};

export default collectionsApi;
