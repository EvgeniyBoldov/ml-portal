import { apiRequest } from './http';

export interface Agent {
  id: string;
  slug: string;
  name: string;
  description?: string;
  system_prompt_slug: string;
  tools: string[];
  available_collections: string[];
  generation_config?: Record<string, any>;
  is_active: boolean;
  enable_logging: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentCreate {
  slug: string;
  name: string;
  description?: string;
  system_prompt_slug: string;
  tools: string[];
  generation_config?: Record<string, any>;
  is_active?: boolean;
  enable_logging?: boolean;
}

export interface AgentUpdate {
  name?: string;
  description?: string;
  system_prompt_slug?: string;
  tools?: string[];
  generation_config?: Record<string, any>;
  is_active?: boolean;
  enable_logging?: boolean;
}

export const agentsApi = {
  async list(params: {
    skip?: number;
    limit?: number;
  } = {}): Promise<Agent[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    
    return apiRequest(`/admin/agents?${searchParams.toString()}`);
  },

  async get(slug: string): Promise<Agent> {
    return apiRequest(`/admin/agents/${slug}`);
  },

  async create(data: AgentCreate): Promise<Agent> {
    return apiRequest('/admin/agents', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(slug: string, data: AgentUpdate): Promise<Agent> {
    return apiRequest(`/admin/agents/${slug}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(slug: string): Promise<void> {
    return apiRequest(`/admin/agents/${slug}`, {
      method: 'DELETE',
    });
  },

  async getGeneratedPrompt(slug: string): Promise<{
    agent_slug: string;
    agent_name: string;
    base_prompt: string;
    base_prompt_slug: string;
    tools_section: string | null;
    collections_section: string | null;
    final_prompt: string;
    tools: string[];
    available_collections: string[];
  }> {
    return apiRequest(`/admin/agents/${slug}/generated-prompt`);
  }
};
