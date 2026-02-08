import { apiRequest } from './http';

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export type LimitVersionStatus = 'draft' | 'active' | 'deprecated';

export interface LimitVersion {
  id: string;
  limit_id: string;
  version: number;
  status: LimitVersionStatus;
  max_steps?: number;
  max_tool_calls?: number;
  max_wall_time_ms?: number;
  tool_timeout_ms?: number;
  max_retries?: number;
  extra_config: Record<string, any>;
  parent_version_id?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface LimitVersionInfo {
  id: string;
  version: number;
  status: LimitVersionStatus;
  max_steps?: number;
  max_tool_calls?: number;
  max_wall_time_ms?: number;
  tool_timeout_ms?: number;
  max_retries?: number;
  notes?: string;
  created_at: string;
}

export interface Limit {
  id: string;
  slug: string;
  name: string;
  description?: string;
  current_version_id?: string;
  created_at: string;
  updated_at: string;
}

export interface LimitListItem {
  id: string;
  slug: string;
  name: string;
  description?: string;
  current_version_id?: string;
  versions_count: number;
  latest_version?: number;
  active_version?: number;
  updated_at: string;
}

export interface LimitDetail extends Limit {
  versions: LimitVersionInfo[];
  current_version?: LimitVersionInfo;
}

export interface LimitCreate {
  slug: string;
  name: string;
  description?: string;
}

export interface LimitUpdate {
  name?: string;
  description?: string;
}

export interface LimitVersionCreate {
  max_steps?: number;
  max_tool_calls?: number;
  max_wall_time_ms?: number;
  tool_timeout_ms?: number;
  max_retries?: number;
  extra_config?: Record<string, any>;
  notes?: string;
  parent_version_id?: string;
}

export interface LimitVersionUpdate {
  max_steps?: number;
  max_tool_calls?: number;
  max_wall_time_ms?: number;
  tool_timeout_ms?: number;
  max_retries?: number;
  extra_config?: Record<string, any>;
  notes?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────

export const limitsApi = {
  async list(params: { skip?: number; limit?: number } = {}): Promise<LimitListItem[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    return apiRequest(`/admin/limits?${searchParams.toString()}`);
  },

  async get(slug: string): Promise<LimitDetail> {
    return apiRequest(`/admin/limits/${slug}`);
  },

  async create(data: LimitCreate): Promise<Limit> {
    return apiRequest('/admin/limits', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(slug: string, data: LimitUpdate): Promise<Limit> {
    return apiRequest(`/admin/limits/${slug}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(slug: string): Promise<void> {
    return apiRequest(`/admin/limits/${slug}`, {
      method: 'DELETE',
    });
  },

  // Version operations
  async listVersions(slug: string, status?: LimitVersionStatus): Promise<LimitVersion[]> {
    const params = status ? `?status_filter=${status}` : '';
    return apiRequest(`/admin/limits/${slug}/versions${params}`);
  },

  async getVersion(slug: string, versionNumber: number): Promise<LimitVersion> {
    return apiRequest(`/admin/limits/${slug}/versions/${versionNumber}`);
  },

  async createVersion(slug: string, data: LimitVersionCreate): Promise<LimitVersion> {
    return apiRequest(`/admin/limits/${slug}/versions`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateVersion(slug: string, versionNumber: number, data: LimitVersionUpdate): Promise<LimitVersion> {
    return apiRequest(`/admin/limits/${slug}/versions/${versionNumber}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async deleteVersion(slug: string, versionNumber: number): Promise<void> {
    return apiRequest(`/admin/limits/${slug}/versions/${versionNumber}`, {
      method: 'DELETE',
    });
  },

  async activateVersion(slug: string, versionNumber: number): Promise<LimitVersion> {
    return apiRequest(`/admin/limits/${slug}/versions/${versionNumber}/activate`, {
      method: 'POST',
    });
  },

  async deactivateVersion(slug: string, versionNumber: number): Promise<LimitVersion> {
    return apiRequest(`/admin/limits/${slug}/versions/${versionNumber}/deactivate`, {
      method: 'POST',
    });
  },
};
