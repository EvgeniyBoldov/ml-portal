/**
 * API client for Agent Runs observability
 */
import { apiRequest } from './http';

export interface AgentRunStep {
  id: string;
  step_number: number;
  step_type: 'llm_request' | 'tool_call' | 'tool_result' | 'final_response';
  data: Record<string, unknown>;
  tokens_in?: number;
  tokens_out?: number;
  duration_ms?: number;
  created_at: string;
}

export interface AgentRun {
  id: string;
  chat_id?: string;
  message_id?: string;
  user_id?: string;
  tenant_id: string;
  agent_slug: string;
  status: 'running' | 'completed' | 'failed';
  total_steps: number;
  total_tool_calls: number;
  tokens_in?: number;
  tokens_out?: number;
  duration_ms?: number;
  error?: string;
  started_at: string;
  finished_at?: string;
}

export interface AgentRunDetail extends AgentRun {
  steps: AgentRunStep[];
}

export interface AgentRunListResponse {
  items: AgentRun[];
  total: number;
  page: number;
  page_size: number;
}

export interface AgentRunFilter {
  tenant_id?: string;
  user_id?: string;
  chat_id?: string;
  agent_slug?: string;
  status?: string;
  from_date?: string;
  to_date?: string;
  page?: number;
  page_size?: number;
}

export interface AgentRunStats {
  total_runs: number;
  by_status: Record<string, number>;
  by_agent: Record<string, number>;
  avg_duration_ms?: number;
}

export const agentRunsApi = {
  async list(filters: AgentRunFilter = {}): Promise<AgentRunListResponse> {
    const params = new URLSearchParams();
    if (filters.tenant_id) params.set('tenant_id', filters.tenant_id);
    if (filters.user_id) params.set('user_id', filters.user_id);
    if (filters.chat_id) params.set('chat_id', filters.chat_id);
    if (filters.agent_slug) params.set('agent_slug', filters.agent_slug);
    if (filters.status) params.set('status', filters.status);
    if (filters.from_date) params.set('from_date', filters.from_date);
    if (filters.to_date) params.set('to_date', filters.to_date);
    if (filters.page) params.set('page', String(filters.page));
    if (filters.page_size) params.set('page_size', String(filters.page_size));
    
    const query = params.toString();
    const url = `/admin/agent-runs${query ? `?${query}` : ''}`;
    return apiRequest<AgentRunListResponse>(url);
  },

  async get(runId: string): Promise<AgentRunDetail> {
    return apiRequest<AgentRunDetail>(`/admin/agent-runs/${runId}`);
  },

  async delete(runId: string): Promise<{ status: string; run_id: string }> {
    return apiRequest(`/admin/agent-runs/${runId}`, { method: 'DELETE' });
  },

  async deleteOld(beforeDate: string, tenantId?: string): Promise<{ status: string; deleted_count: number }> {
    const params = new URLSearchParams({ before_date: beforeDate });
    if (tenantId) params.set('tenant_id', tenantId);
    return apiRequest(`/admin/agent-runs?${params.toString()}`, { method: 'DELETE' });
  },

  async getStats(filters: { tenant_id?: string; from_date?: string; to_date?: string } = {}): Promise<AgentRunStats> {
    const params = new URLSearchParams();
    if (filters.tenant_id) params.set('tenant_id', filters.tenant_id);
    if (filters.from_date) params.set('from_date', filters.from_date);
    if (filters.to_date) params.set('to_date', filters.to_date);
    
    const query = params.toString();
    return apiRequest<AgentRunStats>(`/admin/agent-runs/stats/summary${query ? `?${query}` : ''}`);
  },
};
