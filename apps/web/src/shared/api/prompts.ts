import { apiRequest } from './http';

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export type PromptStatus = 'draft' | 'active' | 'archived';
export type PromptType = 'prompt' | 'baseline';

export interface PromptContainer {
  id: string;
  slug: string;
  name: string;
  description?: string;
  type: PromptType;
  created_at: string;
  updated_at: string;
}

export interface PromptVersion {
  id: string;
  prompt_id: string;
  template: string;
  input_variables: string[];
  generation_config: Record<string, any>;
  version: number;
  status: PromptStatus;
  parent_version_id?: string;
  created_at: string;
  updated_at: string;
}

export interface PromptVersionInfo {
  id: string;
  version: number;
  status: PromptStatus;
  created_at: string;
}

export interface PromptListItem {
  id: string;
  slug: string;
  name: string;
  description?: string;
  type: PromptType;
  versions_count: number;
  latest_version?: number;
  active_version?: number;
  updated_at: string;
}

export interface PromptDetail {
  id: string;
  slug: string;
  name: string;
  description?: string;
  type: PromptType;
  created_at: string;
  updated_at: string;
  versions: PromptVersionInfo[];
}

// Request types
export interface CreatePromptContainerRequest {
  slug: string;
  name: string;
  description?: string;
  type: PromptType;
}

export interface UpdatePromptContainerRequest {
  name?: string;
  description?: string;
}

export interface CreatePromptVersionRequest {
  template: string;
  parent_version_id?: string;
  input_variables?: string[];
  generation_config?: Record<string, any>;
}

export interface UpdatePromptVersionRequest {
  template?: string;
  input_variables?: string[];
  generation_config?: Record<string, any>;
}

// ─────────────────────────────────────────────────────────────────────────────
// API CLIENT
// ─────────────────────────────────────────────────────────────────────────────

export const promptsApi = {
  // ─── PROMPT CONTAINER ───
  
  async createContainer(data: CreatePromptContainerRequest): Promise<PromptContainer> {
    return apiRequest<PromptContainer>('/admin/prompts', {
      method: 'POST',
      body: data,
    });
  },

  async listPrompts(params?: { skip?: number; limit?: number; type?: PromptType }): Promise<PromptListItem[]> {
    return apiRequest<PromptListItem[]>('/admin/prompts', {
      method: 'GET',
      params,
    });
  },

  async getPrompt(slug: string): Promise<PromptDetail> {
    return apiRequest<PromptDetail>(`/admin/prompts/${slug}`, {
      method: 'GET',
    });
  },

  async updateContainer(slug: string, data: UpdatePromptContainerRequest): Promise<PromptContainer> {
    return apiRequest<PromptContainer>(`/admin/prompts/${slug}`, {
      method: 'PATCH',
      body: data,
    });
  },

  // ─── PROMPT VERSION ───

  async createVersion(slug: string, data: CreatePromptVersionRequest): Promise<PromptVersion> {
    return apiRequest<PromptVersion>(`/admin/prompts/${slug}/versions`, {
      method: 'POST',
      body: data,
    });
  },

  async getVersions(slug: string): Promise<PromptVersionInfo[]> {
    return apiRequest<PromptVersionInfo[]>(`/admin/prompts/${slug}/versions`, {
      method: 'GET',
    });
  },

  async getVersion(slug: string, version: number): Promise<PromptVersion> {
    return apiRequest<PromptVersion>(`/admin/prompts/${slug}/versions/${version}`, {
      method: 'GET',
    });
  },

  async updateVersion(versionId: string, data: UpdatePromptVersionRequest): Promise<PromptVersion> {
    return apiRequest<PromptVersion>(`/admin/prompts/versions/${versionId}`, {
      method: 'PATCH',
      body: data,
    });
  },

  async activateVersion(versionId: string, archiveCurrent: boolean = true): Promise<PromptVersion> {
    return apiRequest<PromptVersion>(`/admin/prompts/versions/${versionId}/activate`, {
      method: 'POST',
      body: { archive_current: archiveCurrent },
    });
  },

  async archiveVersion(versionId: string): Promise<PromptVersion> {
    return apiRequest<PromptVersion>(`/admin/prompts/versions/${versionId}/archive`, {
      method: 'POST',
    });
  },

  // ─── RENDER ───

  async renderActive(slug: string, variables: Record<string, any>): Promise<{ rendered: string }> {
    return apiRequest<{ rendered: string }>(`/admin/prompts/${slug}/render`, {
      method: 'POST',
      body: { variables },
    });
  },

  async renderVersion(slug: string, version: number, variables: Record<string, any>): Promise<{ rendered: string }> {
    return apiRequest<{ rendered: string }>(`/admin/prompts/${slug}/versions/${version}/render`, {
      method: 'POST',
      body: { variables },
    });
  },
};
