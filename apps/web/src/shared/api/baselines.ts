import { apiRequest } from './http';

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export type BaselineStatus = 'draft' | 'active' | 'archived';
export type BaselineScope = 'default' | 'tenant' | 'user';

export interface BaselineContainer {
  id: string;
  slug: string;
  name: string;
  description?: string;
  scope: BaselineScope;
  tenant_id?: string;
  user_id?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface BaselineVersion {
  id: string;
  baseline_id: string;
  template: string;
  version: number;
  status: BaselineStatus;
  parent_version_id?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface BaselineVersionInfo {
  id: string;
  version: number;
  status: BaselineStatus;
  notes?: string;
  created_at: string;
}

export interface BaselineListItem {
  id: string;
  slug: string;
  name: string;
  description?: string;
  scope: BaselineScope;
  tenant_id?: string;
  user_id?: string;
  is_active: boolean;
  versions_count: number;
  latest_version?: number;
  active_version?: number;
  updated_at: string;
}

export interface BaselineDetail {
  id: string;
  slug: string;
  name: string;
  description?: string;
  scope: BaselineScope;
  tenant_id?: string;
  user_id?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  versions: BaselineVersionInfo[];
}

export interface EffectiveBaselineItem {
  id: string;
  slug: string;
  name: string;
  scope: BaselineScope;
  template: string;
}

export interface EffectiveBaselinesResponse {
  baselines: EffectiveBaselineItem[];
  merged_content: string;
}

// Request types
export interface CreateBaselineContainerRequest {
  slug: string;
  name: string;
  description?: string;
  scope: BaselineScope;
  tenant_id?: string;
  user_id?: string;
  is_active?: boolean;
}

export interface UpdateBaselineContainerRequest {
  name?: string;
  description?: string;
  is_active?: boolean;
}

export interface CreateBaselineVersionRequest {
  template: string;
  parent_version_id?: string;
  notes?: string;
}

export interface UpdateBaselineVersionRequest {
  template?: string;
  notes?: string;
}

export interface ListBaselinesParams {
  skip?: number;
  limit?: number;
  scope?: BaselineScope;
  tenant_id?: string;
  user_id?: string;
  is_active?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// API CLIENT
// ─────────────────────────────────────────────────────────────────────────────

export const baselinesApi = {
  // ─── BASELINE CONTAINER ───
  
  async createContainer(data: CreateBaselineContainerRequest): Promise<BaselineContainer> {
    return apiRequest<BaselineContainer>('/admin/baselines', {
      method: 'POST',
      body: data,
    });
  },

  async list(params?: ListBaselinesParams): Promise<BaselineListItem[]> {
    return apiRequest<BaselineListItem[]>('/admin/baselines', {
      method: 'GET',
      params,
    });
  },

  async get(slug: string): Promise<BaselineDetail> {
    return apiRequest<BaselineDetail>(`/admin/baselines/${slug}`, {
      method: 'GET',
    });
  },

  async updateContainer(slug: string, data: UpdateBaselineContainerRequest): Promise<BaselineContainer> {
    return apiRequest<BaselineContainer>(`/admin/baselines/${slug}`, {
      method: 'PATCH',
      body: data,
    });
  },

  async delete(slug: string): Promise<void> {
    return apiRequest<void>(`/admin/baselines/${slug}`, {
      method: 'DELETE',
    });
  },

  // ─── EFFECTIVE BASELINES ───

  async getEffective(params?: { tenant_id?: string; user_id?: string }): Promise<EffectiveBaselinesResponse> {
    return apiRequest<EffectiveBaselinesResponse>('/admin/baselines/effective', {
      method: 'GET',
      params,
    });
  },

  // ─── BASELINE VERSION ───

  async createVersion(slug: string, data: CreateBaselineVersionRequest): Promise<BaselineVersion> {
    return apiRequest<BaselineVersion>(`/admin/baselines/${slug}/versions`, {
      method: 'POST',
      body: data,
    });
  },

  async getVersions(slug: string): Promise<BaselineVersionInfo[]> {
    return apiRequest<BaselineVersionInfo[]>(`/admin/baselines/${slug}/versions`, {
      method: 'GET',
    });
  },

  async getVersion(slug: string, versionId: string): Promise<BaselineVersion> {
    return apiRequest<BaselineVersion>(`/admin/baselines/${slug}/versions/${versionId}`, {
      method: 'GET',
    });
  },

  async updateVersion(slug: string, versionId: string, data: UpdateBaselineVersionRequest): Promise<BaselineVersion> {
    return apiRequest<BaselineVersion>(`/admin/baselines/${slug}/versions/${versionId}`, {
      method: 'PATCH',
      body: data,
    });
  },

  async activateVersion(slug: string, versionId: string): Promise<BaselineVersion> {
    return apiRequest<BaselineVersion>(`/admin/baselines/${slug}/versions/${versionId}/activate`, {
      method: 'POST',
    });
  },

  async archiveVersion(slug: string, versionId: string): Promise<BaselineVersion> {
    return apiRequest<BaselineVersion>(`/admin/baselines/${slug}/versions/${versionId}/archive`, {
      method: 'POST',
    });
  },

  async setRecommendedVersion(slug: string, versionId: string): Promise<BaselineDetail> {
    return apiRequest<BaselineDetail>(`/admin/baselines/${slug}/recommended?version_id=${versionId}`, {
      method: 'PUT',
    });
  },
};
