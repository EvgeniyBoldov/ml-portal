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
  tags?: string[] | null;
  current_version_id?: string | null;
  model?: string | null;
  temperature?: number | null;
  max_tokens?: number | null;
  requires_confirmation_for_write?: boolean | null;
  risk_level?: string | null;
  logging_level?: string;
  allowed_collection_ids?: string[] | null;
  versions_count?: number;
  created_at: string;
  updated_at: string;
}

export interface AgentVersionInfo {
  id: string;
  version: number;
  status: string;
  // Prompt parts
  identity?: string | null;
  mission?: string | null;
  scope?: string | null;
  rules?: string | null;
  tool_use_rules?: string | null;
  output_format?: string | null;
  examples?: string | null;
  // Safety prompt constraints
  never_do?: string | null;
  allowed_ops?: string | null;
  // Routing
  short_info?: string | null;
  tags?: string[] | null;
  is_routable?: boolean;
  routing_keywords?: string[] | null;
  routing_negative_keywords?: string[] | null;
  // Meta
  parent_version_id?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface AgentDetail extends Agent {
  versions: AgentVersionInfo[];
}

export interface AgentVersion {
  id: string;
  agent_id: string;
  version: number;
  status: string;
  // Prompt parts
  identity?: string | null;
  mission?: string | null;
  scope?: string | null;
  rules?: string | null;
  tool_use_rules?: string | null;
  output_format?: string | null;
  examples?: string | null;
  // Execution config
  model?: string | null;
  timeout_s?: number | null;
  max_steps?: number | null;
  max_retries?: number | null;
  max_tokens?: number | null;
  temperature?: number | null;
  // Safety knobs
  requires_confirmation_for_write?: boolean | null;
  risk_level?: string | null;
  never_do?: string | null;
  allowed_ops?: string | null;
  // Routing
  short_info?: string | null;
  tags?: string[] | null;
  is_routable?: boolean;
  routing_keywords?: string[] | null;
  routing_negative_keywords?: string[] | null;
  // Meta
  parent_version_id?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentCreate {
  slug: string;
  name: string;
  description?: string;
  model?: string | null;
  temperature?: number | null;
  max_tokens?: number | null;
  requires_confirmation_for_write?: boolean | null;
  risk_level?: string | null;
  tags?: string[];
  logging_level?: string;
  allowed_collection_ids?: string[] | null;
}

export interface AgentUpdate {
  name?: string;
  description?: string;
  model?: string | null;
  temperature?: number | null;
  max_tokens?: number | null;
  requires_confirmation_for_write?: boolean | null;
  risk_level?: string | null;
  tags?: string[];
  logging_level?: string;
  allowed_collection_ids?: string[] | null;
}

export interface AgentRouteRequest {
  request_text: string;
}

export interface AgentRouteResponse {
  selected_agent: Agent;
}

export interface AgentVersionCreate {
  // Prompt parts
  identity?: string | null;
  mission?: string | null;
  scope?: string | null;
  rules?: string | null;
  tool_use_rules?: string | null;
  output_format?: string | null;
  examples?: string | null;
  // Execution config
  model?: string | null;
  timeout_s?: number | null;
  max_steps?: number | null;
  max_retries?: number | null;
  max_tokens?: number | null;
  temperature?: number | null;
  // Safety knobs
  requires_confirmation_for_write?: boolean | null;
  risk_level?: string | null;
  never_do?: string | null;
  allowed_ops?: string | null;
  // Routing
  short_info?: string | null;
  tags?: string[] | null;
  is_routable?: boolean;
  routing_keywords?: string[] | null;
  routing_negative_keywords?: string[] | null;
  // Meta
  notes?: string | null;
  parent_version_id?: string | null;
}

export interface AgentVersionUpdate {
  // Prompt parts
  identity?: string | null;
  mission?: string | null;
  scope?: string | null;
  rules?: string | null;
  tool_use_rules?: string | null;
  output_format?: string | null;
  examples?: string | null;
  // Execution config
  model?: string | null;
  timeout_s?: number | null;
  max_steps?: number | null;
  max_retries?: number | null;
  max_tokens?: number | null;
  temperature?: number | null;
  // Safety knobs
  requires_confirmation_for_write?: boolean | null;
  risk_level?: string | null;
  never_do?: string | null;
  allowed_ops?: string | null;
  // Routing
  short_info?: string | null;
  tags?: string[] | null;
  is_routable?: boolean;
  routing_keywords?: string[] | null;
  routing_negative_keywords?: string[] | null;
  // Meta
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

  async get(id: string): Promise<AgentDetail> {
    return apiRequest(`/admin/agents/${id}`);
  },

  async create(data: AgentCreate): Promise<Agent> {
    return apiRequest('/admin/agents', { method: 'POST', body: JSON.stringify(data) });
  },

  async update(id: string, data: AgentUpdate): Promise<Agent> {
    return apiRequest(`/admin/agents/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  },

  async delete(id: string): Promise<void> {
    return apiRequest(`/admin/agents/${id}`, { method: 'DELETE' });
  },

  async route(data: AgentRouteRequest): Promise<AgentRouteResponse> {
    return apiRequest('/admin/agents/router/route', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Version CRUD — all by agent UUID
  async listVersions(agentId: string): Promise<AgentVersion[]> {
    return apiRequest(`/admin/agents/${agentId}/versions`);
  },

  async getVersion(agentId: string, version: number): Promise<AgentVersion> {
    return apiRequest(`/admin/agents/${agentId}/versions/${version}`);
  },

  async createVersion(agentId: string, data: AgentVersionCreate): Promise<AgentVersion> {
    return apiRequest(`/admin/agents/${agentId}/versions`, { method: 'POST', body: JSON.stringify(data) });
  },

  async updateVersion(agentId: string, version: number, data: AgentVersionUpdate): Promise<AgentVersion> {
    return apiRequest(`/admin/agents/${agentId}/versions/${version}`, { method: 'PATCH', body: JSON.stringify(data) });
  },

  async deleteVersion(agentId: string, version: number): Promise<void> {
    return apiRequest(`/admin/agents/${agentId}/versions/${version}`, { method: 'DELETE' });
  },

  async publishVersion(agentId: string, version: number): Promise<AgentVersion> {
    return apiRequest(`/admin/agents/${agentId}/versions/${version}/publish`, { method: 'POST' });
  },

  async archiveVersion(agentId: string, version: number): Promise<AgentVersion> {
    return apiRequest(`/admin/agents/${agentId}/versions/${version}/archive`, { method: 'POST' });
  },

  async setCurrentVersion(agentId: string, versionId: string): Promise<AgentDetail> {
    return apiRequest(`/admin/agents/${agentId}/current-version?version_id=${versionId}`, { method: 'PUT' });
  },

};
