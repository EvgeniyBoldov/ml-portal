import { apiRequest } from './http';

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export type PolicyVersionStatus = 'draft' | 'active' | 'deprecated';

export interface PolicyVersion {
  id: string;
  policy_id: string;
  version: number;
  status: PolicyVersionStatus;
  hash: string;
  policy_text: string;
  policy_json?: Record<string, any>;
  parent_version_id?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface PolicyVersionInfo {
  id: string;
  version: number;
  status: PolicyVersionStatus;
  hash: string;
  policy_text: string;
  policy_json?: Record<string, any>;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface Policy {
  id: string;
  slug: string;
  name: string;
  description?: string;
  current_version_id?: string;
  created_at: string;
  updated_at: string;
}

export interface PolicyDetail extends Policy {
  versions: PolicyVersionInfo[];
  current_version?: PolicyVersionInfo;
}

export interface PolicyCreate {
  slug: string;
  name: string;
  description?: string;
}

export interface PolicyUpdate {
  name?: string;
  description?: string;
}

export interface PolicyVersionCreate {
  policy_text?: string;
  policy_json?: Record<string, any>;
  notes?: string;
  parent_version_id?: string;
}

export interface PolicyVersionUpdate {
  policy_text?: string;
  policy_json?: Record<string, any>;
  notes?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────

export const policiesApi = {
  async list(params: { skip?: number; limit?: number } = {}): Promise<Policy[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
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
};
