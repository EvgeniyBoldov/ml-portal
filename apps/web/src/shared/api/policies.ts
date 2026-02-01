import { apiRequest } from './http';

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export type PolicyVersionStatus = 'draft' | 'active' | 'inactive';

export interface PolicyVersion {
  id: string;
  policy_id: string;
  version: number;
  status: PolicyVersionStatus;
  max_steps?: number;
  max_tool_calls?: number;
  max_wall_time_ms?: number;
  tool_timeout_ms?: number;
  max_retries?: number;
  budget_tokens?: number;
  budget_cost_cents?: number;
  extra_config: Record<string, any>;
  parent_version_id?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface Policy {
  id: string;
  slug: string;
  name: string;
  description?: string;
  recommended_version_id?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PolicyDetail extends Policy {
  versions: PolicyVersion[];
  recommended_version?: PolicyVersion;
}

export interface PolicyCreate {
  slug: string;
  name: string;
  description?: string;
}

export interface PolicyUpdate {
  name?: string;
  description?: string;
  is_active?: boolean;
}

export interface PolicyVersionCreate {
  max_steps?: number;
  max_tool_calls?: number;
  max_wall_time_ms?: number;
  tool_timeout_ms?: number;
  max_retries?: number;
  budget_tokens?: number;
  budget_cost_cents?: number;
  extra_config?: Record<string, any>;
  notes?: string;
  parent_version_id?: string;
}

export interface PolicyVersionUpdate {
  max_steps?: number;
  max_tool_calls?: number;
  max_wall_time_ms?: number;
  tool_timeout_ms?: number;
  max_retries?: number;
  budget_tokens?: number;
  budget_cost_cents?: number;
  extra_config?: Record<string, any>;
  notes?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────

export const policiesApi = {
  // Policy container operations
  async list(params: {
    skip?: number;
    limit?: number;
    is_active?: boolean;
  } = {}): Promise<Policy[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.is_active !== undefined) searchParams.set('is_active', String(params.is_active));
    
    return apiRequest(`/admin/policies?${searchParams.toString()}`);
  },

  async get(slug: string): Promise<PolicyDetail> {
    return apiRequest(`/admin/policies/${slug}`);
  },

  async create(data: PolicyCreate): Promise<Policy> {
    return apiRequest('/admin/policies', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(slug: string, data: PolicyUpdate): Promise<Policy> {
    return apiRequest(`/admin/policies/${slug}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(slug: string): Promise<void> {
    return apiRequest(`/admin/policies/${slug}`, {
      method: 'DELETE',
    });
  },

  // Version operations
  async listVersions(slug: string, status?: PolicyVersionStatus): Promise<PolicyVersion[]> {
    const params = status ? `?status_filter=${status}` : '';
    return apiRequest(`/admin/policies/${slug}/versions${params}`);
  },

  async getVersion(slug: string, versionNumber: number): Promise<PolicyVersion> {
    return apiRequest(`/admin/policies/${slug}/versions/${versionNumber}`);
  },

  async createVersion(slug: string, data: PolicyVersionCreate): Promise<PolicyVersion> {
    return apiRequest(`/admin/policies/${slug}/versions`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateVersion(slug: string, versionNumber: number, data: PolicyVersionUpdate): Promise<PolicyVersion> {
    return apiRequest(`/admin/policies/${slug}/versions/${versionNumber}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async deleteVersion(slug: string, versionNumber: number): Promise<void> {
    return apiRequest(`/admin/policies/${slug}/versions/${versionNumber}`, {
      method: 'DELETE',
    });
  },

  async activateVersion(slug: string, versionNumber: number): Promise<PolicyVersion> {
    return apiRequest(`/admin/policies/${slug}/versions/${versionNumber}/activate`, {
      method: 'POST',
    });
  },

  async deactivateVersion(slug: string, versionNumber: number): Promise<PolicyVersion> {
    return apiRequest(`/admin/policies/${slug}/versions/${versionNumber}/deactivate`, {
      method: 'POST',
    });
  },

  async getRecommendedVersion(slug: string): Promise<PolicyVersion> {
    return apiRequest(`/admin/policies/${slug}/recommended`);
  },

  async setRecommendedVersion(slug: string, versionId: string): Promise<Policy> {
    return apiRequest(`/admin/policies/${slug}/recommended?version_id=${versionId}`, {
      method: 'PUT',
    });
  },
};
