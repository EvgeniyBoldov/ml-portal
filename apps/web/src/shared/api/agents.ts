/**
 * Agents API v2 - container + versions architecture
 */
import { apiRequest } from './http';

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export interface Agent {
  id: string;
  slug: string;
  name: string;
  description?: string;
  current_version_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentVersionInfo {
  id: string;
  version: number;
  status: string;
  prompt: string;
  policy_id?: string | null;
  limit_id?: string | null;
  notes?: string | null;
  created_at: string;
}

export interface AgentDetail extends Agent {
  versions: AgentVersionInfo[];
  current_version?: AgentVersionInfo | null;
}

export interface AgentVersion {
  id: string;
  agent_id: string;
  version: number;
  status: string;
  prompt: string;
  policy_id?: string | null;
  limit_id?: string | null;
  parent_version_id?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentBindingInput {
  tool_id: string;
  tool_instance_id?: string | null;
  credential_strategy?: string;
}

export interface AgentBindingResponse {
  id: string;
  agent_version_id: string;
  tool_id: string;
  tool_instance_id?: string | null;
  credential_strategy: string;
  created_at: string;
  tool_slug?: string | null;
  tool_name?: string | null;
  tool_group_slug?: string | null;
  instance_slug?: string | null;
  instance_name?: string | null;
}

export interface AgentBindingCreate {
  agent_version_id: string;
  tool_id: string;
  tool_instance_id?: string | null;
  credential_strategy?: string;
}

export interface AgentBindingUpdate {
  tool_instance_id?: string | null;
  credential_strategy?: string;
}

export interface AgentCreate {
  slug: string;
  name: string;
  description?: string;
}

export interface AgentUpdate {
  name?: string;
  description?: string;
}

export interface AgentVersionCreate {
  prompt?: string | null;
  policy_id?: string | null;
  limit_id?: string | null;
  notes?: string | null;
  parent_version_id?: string | null;
}

export interface AgentVersionUpdate {
  prompt?: string;
  policy_id?: string | null;
  limit_id?: string | null;
  notes?: string | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────

export const agentsApi = {
  // Container CRUD
  async list(params: { skip?: number; limit?: number } = {}): Promise<Agent[]> {
    const sp = new URLSearchParams();
    if (params.skip) sp.set('skip', String(params.skip));
    if (params.limit) sp.set('limit', String(params.limit));
    return apiRequest(`/admin/agents?${sp.toString()}`);
  },

  async get(slug: string): Promise<AgentDetail> {
    return apiRequest(`/admin/agents/${slug}`);
  },

  async create(data: AgentCreate): Promise<Agent> {
    return apiRequest('/admin/agents', { method: 'POST', body: JSON.stringify(data) });
  },

  async update(slug: string, data: AgentUpdate): Promise<Agent> {
    return apiRequest(`/admin/agents/${slug}`, { method: 'PUT', body: JSON.stringify(data) });
  },

  async delete(slug: string): Promise<void> {
    return apiRequest(`/admin/agents/${slug}`, { method: 'DELETE' });
  },

  // Version CRUD
  async listVersions(slug: string): Promise<AgentVersion[]> {
    return apiRequest(`/admin/agents/${slug}/versions`);
  },

  async getVersion(slug: string, version: number): Promise<AgentVersion> {
    return apiRequest(`/admin/agents/${slug}/versions/${version}`);
  },

  async createVersion(slug: string, data: AgentVersionCreate): Promise<AgentVersion> {
    return apiRequest(`/admin/agents/${slug}/versions`, { method: 'POST', body: JSON.stringify(data) });
  },

  async updateVersion(slug: string, version: number, data: AgentVersionUpdate): Promise<AgentVersion> {
    return apiRequest(`/admin/agents/${slug}/versions/${version}`, { method: 'PATCH', body: JSON.stringify(data) });
  },

  async deleteVersion(slug: string, version: number): Promise<void> {
    return apiRequest(`/admin/agents/${slug}/versions/${version}`, { method: 'DELETE' });
  },

  async activateVersion(slug: string, version: number): Promise<AgentVersion> {
    return apiRequest(`/admin/agents/${slug}/versions/${version}/activate`, { method: 'POST' });
  },

  async deactivateVersion(slug: string, version: number): Promise<AgentVersion> {
    return apiRequest(`/admin/agents/${slug}/versions/${version}/deactivate`, { method: 'POST' });
  },

  // Bindings CRUD
  async listBindings(slug: string, version: number): Promise<AgentBindingResponse[]> {
    return apiRequest(`/admin/agents/${slug}/versions/${version}/bindings`);
  },

  async createBinding(slug: string, version: number, data: AgentBindingCreate): Promise<AgentBindingResponse> {
    return apiRequest(`/admin/agents/${slug}/versions/${version}/bindings`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateBinding(
    slug: string,
    version: number,
    bindingId: string,
    data: AgentBindingUpdate,
  ): Promise<AgentBindingResponse> {
    return apiRequest(`/admin/agents/${slug}/versions/${version}/bindings/${bindingId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async deleteBinding(slug: string, version: number, bindingId: string): Promise<void> {
    return apiRequest(`/admin/agents/${slug}/versions/${version}/bindings/${bindingId}`, {
      method: 'DELETE',
    });
  },
};
