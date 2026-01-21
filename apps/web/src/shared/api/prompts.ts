import { apiRequest } from './http';

export interface Prompt {
  id: string;
  slug: string;
  name: string;
  description?: string;
  template: string;
  input_variables: string[];
  model_config?: Record<string, any>;
  version: number;
  is_active: boolean;
  type: 'chat' | 'agent' | 'task';
  created_at: string;
  updated_at: string;
  used_by_agents?: string[];
}

export interface PromptCreate {
  slug: string;
  name: string;
  description?: string;
  template: string;
  input_variables?: string[];
  model_config?: Record<string, any>;
  type?: string;
}

export interface PromptRenderRequest {
  variables: Record<string, any>;
}

export interface PromptRenderResponse {
  rendered: string;
}

export const promptsApi = {
  async list(params: {
    skip?: number;
    limit?: number;
    type?: string;
  } = {}): Promise<Prompt[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.type) searchParams.set('type', params.type);
    
    return apiRequest(`/admin/prompts?${searchParams.toString()}`);
  },

  async get(slug: string): Promise<Prompt> {
    return apiRequest(`/admin/prompts/${slug}`);
  },

  async create(data: PromptCreate): Promise<Prompt> {
    return apiRequest('/admin/prompts', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async render(slug: string, variables: Record<string, any>): Promise<PromptRenderResponse> {
    return apiRequest(`/admin/prompts/${slug}/render`, {
      method: 'POST',
      body: JSON.stringify({ variables }),
    });
  },

  async preview(template: string, variables: Record<string, any>): Promise<PromptRenderResponse> {
    // For preview, we send a dummy create payload
    return apiRequest('/admin/prompts/preview', {
      method: 'POST',
      body: JSON.stringify({ 
        slug: 'preview',
        name: 'preview',
        template,
        variables 
      }), // Backend expects PromptCreate schema + variables param
    });
  }
};
