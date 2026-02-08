import { apiRequest } from './http';

export interface AgentBindingInput {
  tool_id: string;
  tool_instance_id: string;
  credential_strategy: 'user_only' | 'tenant_only' | 'default_only' | 'prefer_user' | 'prefer_tenant' | 'any';
  required: boolean;
}

export interface AgentBindingResponse {
  id: string;
  tool_id: string;
  tool_slug: string;
  tool_name: string;
  tool_group_slug: string;
  tool_instance_id: string;
  instance_slug: string;
  instance_name: string;
  credential_strategy: string;
  required: boolean;
}

export interface Agent {
  id: string;
  slug: string;
  name: string;
  description?: string;
  system_prompt_slug: string;
  policy_id?: string | null;
  limit_id?: string | null;
  capabilities: string[];
  supports_partial_mode: boolean;
  generation_config?: Record<string, unknown>;
  is_active: boolean;
  enable_logging: boolean;
  created_at: string;
  updated_at: string;
  bindings?: AgentBindingResponse[];
}

export interface AgentCreate {
  slug: string;
  name: string;
  description?: string;
  system_prompt_slug: string;
  policy_id?: string | null;
  limit_id?: string | null;
  capabilities?: string[];
  supports_partial_mode?: boolean;
  generation_config?: Record<string, unknown>;
  is_active?: boolean;
  enable_logging?: boolean;
  bindings?: AgentBindingInput[];
}

export interface AgentUpdate {
  name?: string;
  description?: string;
  system_prompt_slug?: string;
  policy_id?: string | null;
  limit_id?: string | null;
  capabilities?: string[];
  supports_partial_mode?: boolean;
  generation_config?: Record<string, unknown>;
  is_active?: boolean;
  enable_logging?: boolean;
  bindings?: AgentBindingInput[];
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
    final_prompt: string;
    tools: string[];
    policy_id: string | null;
    limit_id: string | null;
    capabilities: string[];
  }> {
    return apiRequest(`/admin/agents/${slug}/generated-prompt`);
  }
};
