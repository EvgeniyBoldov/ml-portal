/**
 * Tool Instances API v3
 *
 * Connector classification axes:
 * - connector_type: data | mcp | model
 * - connector_subtype: sql | api (for data connectors)
 * - placement: local | remote
 */
import { apiRequest } from './http';

// ── Types ────────────────────────────────────────────────────────────

export interface ToolInstance {
  id: string;
  slug: string;
  name: string;
  description?: string;
  instance_kind: string;   // "data" | "service"
  connector_type: string;  // "data" | "mcp" | "model"
  connector_subtype?: string | null; // "sql" | "api" for data connectors
  placement: string;       // "local" | "remote"
  provider_kind?: string | null;
  url: string;
  config?: Record<string, unknown>;
  is_active: boolean;
  health_status?: string;
  access_via_instance_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RuntimeOperation {
  operation_slug: string;
  operation: string;
  source: string;
  discovered_tool_slug: string;
  provider_instance_slug?: string | null;
  risk_level: string;
  side_effects: string;
  idempotent: boolean;
  requires_confirmation: boolean;
}

export interface ToolInstanceDetail extends ToolInstance {
  access_via_name?: string | null;
  runtime_operations?: RuntimeOperation[];
}

export interface ToolInstanceCreate {
  slug?: string;
  name: string;
  description?: string;
  instance_kind?: string;
  connector_type?: string;
  connector_subtype?: string;
  url?: string;
  provider_kind?: string | null;
  config?: Record<string, unknown>;
  access_via_instance_id?: string;
}

export interface ToolInstanceUpdate {
  name?: string;
  description?: string;
  instance_kind?: string;
  connector_type?: string;
  connector_subtype?: string | null;
  url?: string;
  provider_kind?: string | null;
  config?: Record<string, unknown>;
  is_active?: boolean;
  access_via_instance_id?: string | null;
}

export interface HealthCheckResult {
  status: string;
  message?: string;
  details?: Record<string, unknown>;
}

export interface RescanResponse {
  created: number;
  updated: number;
  deleted: number;
  errors: number;
}

export interface InstanceRuntimeOnboardRequest {
  enable_all_in_runtime?: boolean;
  include_local_tools?: boolean;
  include_inactive_linked?: boolean;
}

export interface LinkedDataInstanceRuntimeSummary {
  instance_id: string;
  slug: string;
  connector_subtype?: string | null;
  is_runtime_ready: boolean;
  runtime_readiness_reason: string;
  semantic_source: string;
  discovered_tools_count: number;
  runtime_operations_count: number;
}

export interface InstanceRuntimeOnboardResponse {
  provider_instance_id: string;
  provider_slug: string;
  onboarding: Record<string, unknown>;
  linked_instances_total: number;
  linked_ready_count: number;
  linked_not_ready_count: number;
  linked_runtime_operations_total: number;
  linked_instances: LinkedDataInstanceRuntimeSummary[];
}

// ── API ──────────────────────────────────────────────────────────────

export const toolInstancesApi = {
  // ── Instance CRUD ─────────────────────────────────────────────────

  async list(params: {
    skip?: number;
    limit?: number;
    is_active?: boolean;
    instance_kind?: string;
    connector_type?: string;
    connector_subtype?: string;
    placement?: string;
    } = {}): Promise<ToolInstance[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.is_active !== undefined) searchParams.set('is_active', String(params.is_active));
    if (params.instance_kind) searchParams.set('instance_kind', params.instance_kind);
    if (params.connector_type) searchParams.set('connector_type', params.connector_type);
    if (params.connector_subtype) searchParams.set('connector_subtype', params.connector_subtype);
    if (params.placement) searchParams.set('placement', params.placement);

    return apiRequest(`/admin/connectors?${searchParams.toString()}`);
  },

  async get(id: string): Promise<ToolInstanceDetail> {
    return apiRequest(`/admin/connectors/${id}`);
  },

  async create(data: ToolInstanceCreate): Promise<ToolInstance> {
    return apiRequest('/admin/connectors', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(id: string, data: ToolInstanceUpdate): Promise<ToolInstance> {
    return apiRequest(`/admin/connectors/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(id: string): Promise<void> {
    return apiRequest(`/admin/connectors/${id}`, {
      method: 'DELETE',
    });
  },

  async healthCheck(id: string): Promise<HealthCheckResult> {
    return apiRequest(`/admin/connectors/${id}/health-check`, {
      method: 'POST',
    });
  },

  async rescan(): Promise<RescanResponse> {
    return apiRequest('/admin/connectors/rescan', {
      method: 'POST',
    });
  },

  async onboardRuntime(
    id: string,
    data: InstanceRuntimeOnboardRequest = {},
  ): Promise<InstanceRuntimeOnboardResponse> {
    return apiRequest(`/admin/connectors/${id}/onboard-runtime`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
