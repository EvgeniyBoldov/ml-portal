import { apiRequest } from './http';

// Types
export type PromptStatus = 'draft' | 'active' | 'archived';
export type PromptType = 'prompt' | 'baseline';

export interface PromptVersionInfo {
  id: string;
  version: number;
  status: PromptStatus;
  created_at: string;
}

export interface AgentUsingPrompt {
  slug: string;
  name: string;
  version: number;
}

export interface PromptListItem {
  slug: string;
  name: string;
  description?: string;
  type: PromptType;
  latest_version: number;
  active_version?: number;
  versions_count: number;
  updated_at: string;
}

export interface Prompt {
  id: string;
  slug: string;
  name: string;
  description?: string;
  template: string;
  input_variables: string[];
  generation_config?: Record<string, any>;
  type: PromptType;
  version: number;
  status: PromptStatus;
  parent_version_id?: string;
  created_at: string;
  updated_at: string;
}

export interface PromptCreate {
  slug: string;
  name: string;
  description?: string;
  template: string;
  input_variables?: string[];
  generation_config?: Record<string, any>;
  type?: PromptType;
}

export interface PromptVersionCreate {
  parent_version_id: string;
  name: string;
  description?: string;
  template: string;
  input_variables?: string[];
  generation_config?: Record<string, any>;
}

export interface PromptUpdate {
  name?: string;
  description?: string;
  template?: string;
  input_variables?: string[];
  generation_config?: Record<string, any>;
}

export interface PromptRenderRequest {
  variables: Record<string, any>;
}

export interface PromptRenderResponse {
  rendered: string;
}

export const promptsApi = {
  // List prompts (aggregated view)
  async list(params: {
    skip?: number;
    limit?: number;
    type?: PromptType;
  } = {}): Promise<PromptListItem[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.type) searchParams.set('type', params.type);
    
    return apiRequest(`/admin/prompts?${searchParams.toString()}`);
  },

  // Get all versions of a prompt
  async getVersions(slug: string): Promise<PromptVersionInfo[]> {
    return apiRequest(`/admin/prompts/${slug}/versions`);
  },

  // Get specific version
  async getVersion(slug: string, version: number): Promise<Prompt> {
    return apiRequest(`/admin/prompts/${slug}/versions/${version}`);
  },

  // Get agents using this prompt
  async getAgents(slug: string): Promise<AgentUsingPrompt[]> {
    return apiRequest(`/admin/prompts/${slug}/agents`);
  },

  // Create new prompt (first version as draft)
  async create(data: PromptCreate): Promise<Prompt> {
    return apiRequest('/admin/prompts', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Create new version from existing
  async createVersion(slug: string, data: PromptVersionCreate): Promise<Prompt> {
    return apiRequest(`/admin/prompts/${slug}/versions`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Update draft prompt
  async update(promptId: string, data: PromptUpdate): Promise<Prompt> {
    return apiRequest(`/admin/prompts/${promptId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  // Activate draft prompt
  async activate(promptId: string, archiveCurrent = true): Promise<Prompt> {
    return apiRequest(`/admin/prompts/${promptId}/activate`, {
      method: 'POST',
      body: JSON.stringify({ archive_current: archiveCurrent }),
    });
  },

  // Archive prompt version
  async archive(promptId: string): Promise<Prompt> {
    return apiRequest(`/admin/prompts/${promptId}/archive`, {
      method: 'POST',
    });
  },

  // Render prompt with variables
  async render(
    slug: string, 
    variables: Record<string, any>,
    version?: number
  ): Promise<PromptRenderResponse> {
    const searchParams = version ? `?version=${version}` : '';
    return apiRequest(`/admin/prompts/${slug}/render${searchParams}`, {
      method: 'POST',
      body: JSON.stringify({ variables }),
    });
  },

  // Preview template without saving
  async preview(template: string, variables: Record<string, any>): Promise<PromptRenderResponse> {
    const searchParams = new URLSearchParams();
    searchParams.set('template', template);
    return apiRequest(`/admin/prompts/preview?${searchParams.toString()}`, {
      method: 'POST',
      body: JSON.stringify(variables),
    });
  }
};
