/**
 * Discovered Tools API client
 */
import { apiRequest } from './http';

export type ToolRisk = 'safe' | 'risky';
export type ToolResultDelivery = 'direct' | 'store';
export type ToolSourceType =
  | 'system'
  | 'table'
  | 'document'
  | 'template'
  | 'sql'
  | 'api';

export interface DiscoveredToolListItem {
  id: string;
  tool_id?: string | null;
  slug: string;
  name: string;
  description: string | null;
  risk_level: ToolRisk | null;
  result_delivery: ToolResultDelivery;
  has_observed_data_schema: boolean;
  runtime_managed?: boolean;
  source: string;
  provider_instance_id: string | null;
  connector_slug: string | null;
  connector_name: string | null;
  domains: string[];
  source_types: ToolSourceType[];
  is_active: boolean;
  last_seen_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DiscoveredToolDetail extends DiscoveredToolListItem {
  input_schema: Record<string, unknown> | null;
  output_schema: Record<string, unknown> | null;
  observed_data_schema: Record<string, unknown> | null;
}

export interface RescanResponse {
  message: string;
  stats: {
    skipped?: boolean;
    local_upserted?: number;
    system_upserted?: number;
    mcp_upserted?: number;
    mcp_failed_providers?: { provider_slug: string }[];
    marked_inactive?: number;
    deleted_inactive?: number;
  };
}

export interface DiscoveredToolUpdateRequest {
  tool_id?: string | null;
  risk_level?: ToolRisk | null;
  result_delivery?: ToolResultDelivery;
}

interface McpProbeToolItem {
  slug: string;
  name: string;
  description?: string | null;
  has_input_schema: boolean;
  has_output_schema: boolean;
}

export interface McpProbeResponse {
  provider_instance_id: string;
  provider_slug: string;
  provider_url: string;
  tools_count: number;
  tools: McpProbeToolItem[];
}

export interface McpOnboardRequest {
  provider_instance_id: string;
  enable_all_in_runtime?: boolean;
  include_local?: boolean;
}

export interface McpOnboardResponse {
  provider_instance_id: string;
  probe_tools_count: number;
  rescan_stats: Record<string, unknown>;
  linked_tools_updated: number;
  active_discovered_tools: number;
  published_tools: number;
}

export const discoveredToolsApi = {
  list: async (params?: {
    source?: string;
    domain?: string;
    is_active?: boolean;
  }): Promise<DiscoveredToolListItem[]> => {
    const searchParams = new URLSearchParams();
    if (params?.source) searchParams.set('source', params.source);
    if (params?.domain) searchParams.set('domain', params.domain);
    if (params?.is_active !== undefined)
      searchParams.set('is_active', String(params.is_active));
    const qs = searchParams.toString();
    return apiRequest<DiscoveredToolListItem[]>(
      `/admin/discovered-tools${qs ? `?${qs}` : ''}`,
      { method: 'GET' }
    );
  },

  get: async (id: string): Promise<DiscoveredToolDetail> => {
    return apiRequest<DiscoveredToolDetail>(`/admin/discovered-tools/${id}`, {
      method: 'GET',
    });
  },

  update: async (
    id: string,
    data: DiscoveredToolUpdateRequest
  ): Promise<DiscoveredToolDetail> => {
    return apiRequest<DiscoveredToolDetail>(`/admin/discovered-tools/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  probeMcp: async (providerInstanceId: string): Promise<McpProbeResponse> => {
    const params = new URLSearchParams({
      provider_instance_id: providerInstanceId,
    });
    return apiRequest<McpProbeResponse>(
      `/admin/discovered-tools/probe-mcp?${params.toString()}`,
      {
        method: 'POST',
      }
    );
  },

  onboardMcp: async (data: McpOnboardRequest): Promise<McpOnboardResponse> => {
    return apiRequest<McpOnboardResponse>(
      '/admin/discovered-tools/onboard-mcp',
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  rescan: async (
    data: { include_local?: boolean; provider_instance_id?: string | null } = {
      include_local: true,
    }
  ): Promise<RescanResponse> => {
    return apiRequest<RescanResponse>('/admin/discovered-tools/rescan', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
