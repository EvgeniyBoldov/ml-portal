/**
 * API client for tool registry/release pages and releases
 */
import { apiRequest } from './http';

export interface ToolListItem {
  id: string;
  slug: string;
  name: string;
  domains: string[];
  tags: string[] | null;
  backend_releases_count: number;
  releases_count: number;
  has_current_version: boolean;
}

export interface ToolDetail {
  id: string;
  slug: string;
  name: string;
  domains: string[];
  tags: string[] | null;
  current_version_id: string | null;
  created_at: string;
  backend_releases: ToolBackendReleaseListItem[];
  releases: ToolReleaseListItem[];
  current_version: ToolReleaseResponse | null;
}

export interface ToolBackendReleaseListItem {
  id: string;
  version: string;
  description: string | null;
  deprecated: boolean;
  synced_at: string;
  schema_hash: string | null;
  worker_build_id: string | null;
  last_seen_at: string | null;
}

export interface ToolBackendReleaseDetail {
  id: string;
  tool_id: string;
  version: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown> | null;
  description: string | null;
  method_name: string;
  deprecated: boolean;
  deprecation_message: string | null;
  synced_at: string;
  schema_hash: string | null;
  worker_build_id: string | null;
  last_seen_at: string | null;
}

export interface ToolReleaseListItem {
  id: string;
  version: number;
  status: 'draft' | 'active' | 'archived';
  backend_release_id: string | null;
  backend_version: string | null;
  created_at: string;
  expected_schema_hash: string | null;
  parent_release_id: string | null;
}

export interface ToolSemanticProfile {
  summary: string;
  when_to_use: string;
  limitations: string;
  examples: string[];
}

export interface ToolPolicyHints {
  dos: string[];
  donts: string[];
  guardrails: string[];
  sensitive_inputs: string[];
}

export interface ToolReleaseResponse {
  id: string;
  tool_id: string;
  version: number;
  backend_release_id: string | null;
  status: 'draft' | 'active' | 'archived';
  semantic_profile: ToolSemanticProfile;
  policy_hints: ToolPolicyHints;
  // Meta
  meta_hash: string | null;
  expected_schema_hash: string | null;
  parent_release_id: string | null;
  created_at: string;
  updated_at: string;
  backend_release: ToolBackendReleaseDetail | null;
}

export interface ToolReleaseCreate {
  backend_release_id?: string | null;
  from_release_id?: string;
  semantic_profile?: Partial<ToolSemanticProfile> | null;
  policy_hints?: Partial<ToolPolicyHints> | null;
}

export interface ToolReleaseUpdate {
  backend_release_id?: string | null;
  semantic_profile?: Partial<ToolSemanticProfile> | null;
  policy_hints?: Partial<ToolPolicyHints> | null;
}

export interface ToolUpdateRequest {
  name?: string;
  domains?: string[] | null;
  tags?: string[] | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// API CLIENT
// ─────────────────────────────────────────────────────────────────────────────

export const toolReleasesApi = {
  // ─────────────────────────────────────────────────────────────────────────
  // TOOLS — UUID-based detail/profile surface
  // ─────────────────────────────────────────────────────────────────────────

  getTool: async (id: string): Promise<ToolDetail> => {
    return apiRequest<ToolDetail>(`/admin/tools/${id}`, { method: 'GET' });
  },

  updateTool: async (
    id: string,
    data: ToolUpdateRequest,
  ): Promise<ToolDetail> => {
    return apiRequest<ToolDetail>(`/admin/tools/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
  },

  setCurrentVersion: async (toolId: string, releaseId: string): Promise<ToolDetail> => {
    return apiRequest<ToolDetail>(`/admin/tools/${toolId}/current-version?release_id=${releaseId}`, { method: 'PUT' });
  },

  // ─────────────────────────────────────────────────────────────────────────
  // BACKEND RELEASES (read-only) — all by tool UUID
  // ─────────────────────────────────────────────────────────────────────────

  listBackendReleases: async (toolId: string): Promise<ToolBackendReleaseListItem[]> => {
    return apiRequest<ToolBackendReleaseListItem[]>(`/admin/tools/${toolId}/backend-releases`, { method: 'GET' });
  },

  getBackendRelease: async (toolId: string, version: string): Promise<ToolBackendReleaseDetail> => {
    return apiRequest<ToolBackendReleaseDetail>(`/admin/tools/${toolId}/backend-releases/${version}`, { method: 'GET' });
  },

  // ─────────────────────────────────────────────────────────────────────────
  // TOOL RELEASES (CRUD) — all by tool UUID
  // ─────────────────────────────────────────────────────────────────────────

  listReleases: async (toolId: string): Promise<ToolReleaseListItem[]> => {
    return apiRequest<ToolReleaseListItem[]>(`/admin/tools/${toolId}/releases`, { method: 'GET' });
  },

  getRelease: async (toolId: string, version: number): Promise<ToolReleaseResponse> => {
    return apiRequest<ToolReleaseResponse>(`/admin/tools/${toolId}/releases/${version}`, { method: 'GET' });
  },

  createRelease: async (toolId: string, data: ToolReleaseCreate): Promise<ToolReleaseResponse> => {
    return apiRequest<ToolReleaseResponse>(`/admin/tools/${toolId}/releases`, { method: 'POST', body: data });
  },

  updateRelease: async (toolId: string, version: number, data: ToolReleaseUpdate): Promise<ToolReleaseResponse> => {
    return apiRequest<ToolReleaseResponse>(`/admin/tools/${toolId}/releases/${version}`, { method: 'PATCH', body: data });
  },

  activateRelease: async (toolId: string, version: number): Promise<ToolReleaseResponse> => {
    return apiRequest<ToolReleaseResponse>(`/admin/tools/${toolId}/releases/${version}/activate`, { method: 'POST' });
  },

  archiveRelease: async (toolId: string, version: number): Promise<ToolReleaseResponse> => {
    return apiRequest<ToolReleaseResponse>(`/admin/tools/${toolId}/releases/${version}/archive`, { method: 'POST' });
  },

  deleteRelease: async (toolId: string, version: number): Promise<void> => {
    await apiRequest(`/admin/tools/${toolId}/releases/${version}`, { method: 'DELETE' });
  },

  rescanBackendReleases: async (toolId: string): Promise<{ message: string; stats: Record<string, number>; backend_releases: ToolBackendReleaseListItem[] }> => {
    return apiRequest<{ message: string; stats: Record<string, number>; backend_releases: ToolBackendReleaseListItem[] }>(`/admin/tools/${toolId}/rescan-backend`, { method: 'POST' });
  },
};

export const toolReleasesKeys = {
  all: ['tool-releases'] as const,

  // Tools
  tools: () => [...toolReleasesKeys.all, 'tools'] as const,
  toolDetail: (id: string) => [...toolReleasesKeys.tools(), 'detail', id] as const,
  
  // Backend Releases
  backendReleases: (toolId: string) => [...toolReleasesKeys.all, 'backend-releases', toolId] as const,
  backendReleaseDetail: (toolId: string, version: string) => 
    [...toolReleasesKeys.backendReleases(toolId), 'detail', version] as const,
  
  // Tool Releases
  releases: (toolId: string) => [...toolReleasesKeys.all, 'releases', toolId] as const,
  releaseDetail: (toolId: string, version: number) => 
    [...toolReleasesKeys.releases(toolId), 'detail', version] as const,
};
