/**
 * API client for Tool Groups, Tools, and Releases
 */
import { apiRequest } from './http';

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export interface ToolGroupListItem {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  type: string | null;
  tools_count: number;
  instances_count: number;
}

export interface ToolGroupDetail {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  type: string | null;
  description_for_router: string | null;
  created_at: string;
  tools: ToolListItem[];
  instances_count: number;
}

export interface ToolGroupCreate {
  slug: string;
  name: string;
  description?: string | null;
  type?: string | null;
  description_for_router?: string | null;
}

export interface ToolGroupUpdate {
  name?: string;
  description?: string | null;
  type?: string | null;
  description_for_router?: string | null;
}

export interface ToolListItem {
  id: string;
  slug: string;
  name: string;
  kind: string;
  tags: string[] | null;
  backend_releases_count: number;
  releases_count: number;
  has_current_version: boolean;
}

export interface ToolDetail {
  id: string;
  slug: string;
  name: string;
  kind: string;
  tags: string[] | null;
  tool_group_id: string;
  tool_group_slug: string | null;
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
  backend_release_id: string;
  backend_version: string | null;
  category: string | null;
  tags: string[];
  notes: string | null;
  created_at: string;
  expected_schema_hash: string | null;
  parent_release_id: string | null;
}

export interface ToolReleaseResponse {
  id: string;
  tool_id: string;
  version: number;
  backend_release_id: string;
  status: 'draft' | 'active' | 'archived';
  config: Record<string, unknown>;
  description_for_llm: string | null;
  category: string | null;
  tags: string[];
  field_hints: Record<string, string>;
  examples: Array<Record<string, unknown>>;
  return_summary: string | null;
  meta_hash: string | null;
  notes: string | null;
  expected_schema_hash: string | null;
  parent_release_id: string | null;
  created_at: string;
  updated_at: string;
  backend_release: ToolBackendReleaseDetail | null;
}

export interface ToolReleaseCreate {
  backend_release_id: string;
  from_release_id?: string;
  config?: Record<string, unknown>;
  description_for_llm?: string | null;
  category?: string | null;
  tags?: string[];
  field_hints?: Record<string, string>;
  examples?: Array<Record<string, unknown>>;
  return_summary?: string | null;
  notes?: string | null;
}

export interface ToolReleaseUpdate {
  backend_release_id?: string;
  config?: Record<string, unknown>;
  description_for_llm?: string | null;
  category?: string | null;
  tags?: string[];
  field_hints?: Record<string, string>;
  examples?: Array<Record<string, unknown>>;
  return_summary?: string | null;
  notes?: string | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// API CLIENT
// ─────────────────────────────────────────────────────────────────────────────

export const toolReleasesApi = {
  // ─────────────────────────────────────────────────────────────────────────
  // TOOL GROUPS
  // ─────────────────────────────────────────────────────────────────────────
  
  listGroups: async (): Promise<ToolGroupListItem[]> => {
    return apiRequest<ToolGroupListItem[]>('/admin/tool-groups', { method: 'GET' });
  },

  getGroup: async (slug: string): Promise<ToolGroupDetail> => {
    return apiRequest<ToolGroupDetail>(`/admin/tool-groups/${slug}`, { method: 'GET' });
  },

  createGroup: async (data: ToolGroupCreate): Promise<ToolGroupDetail> => {
    return apiRequest<ToolGroupDetail>('/admin/tool-groups', { method: 'POST', body: data });
  },

  updateGroup: async (slug: string, data: ToolGroupUpdate): Promise<ToolGroupDetail> => {
    return apiRequest<ToolGroupDetail>(`/admin/tool-groups/${slug}`, { method: 'PATCH', body: data });
  },

  deleteGroup: async (slug: string): Promise<void> => {
    return apiRequest<void>(`/admin/tool-groups/${slug}`, { method: 'DELETE' });
  },

  // ─────────────────────────────────────────────────────────────────────────
  // TOOLS
  // ─────────────────────────────────────────────────────────────────────────

  listToolsByGroup: async (groupSlug: string): Promise<ToolListItem[]> => {
    return apiRequest<ToolListItem[]>(`/admin/tool-groups/${groupSlug}/tools`, { method: 'GET' });
  },

  getTool: async (slug: string): Promise<ToolDetail> => {
    return apiRequest<ToolDetail>(`/admin/tools/${slug}`, { method: 'GET' });
  },

  setCurrentVersion: async (toolSlug: string, releaseId: string): Promise<ToolDetail> => {
    return apiRequest<ToolDetail>(`/admin/tools/${toolSlug}/current-version?release_id=${releaseId}`, { method: 'PUT' });
  },

  // ─────────────────────────────────────────────────────────────────────────
  // BACKEND RELEASES (read-only)
  // ─────────────────────────────────────────────────────────────────────────

  listBackendReleases: async (toolSlug: string): Promise<ToolBackendReleaseListItem[]> => {
    return apiRequest<ToolBackendReleaseListItem[]>(`/admin/tools/${toolSlug}/backend-releases`, { method: 'GET' });
  },

  getBackendRelease: async (toolSlug: string, version: string): Promise<ToolBackendReleaseDetail> => {
    return apiRequest<ToolBackendReleaseDetail>(`/admin/tools/${toolSlug}/backend-releases/${version}`, { method: 'GET' });
  },

  // ─────────────────────────────────────────────────────────────────────────
  // TOOL RELEASES (CRUD)
  // ─────────────────────────────────────────────────────────────────────────

  listReleases: async (toolSlug: string): Promise<ToolReleaseListItem[]> => {
    return apiRequest<ToolReleaseListItem[]>(`/admin/tools/${toolSlug}/releases`, { method: 'GET' });
  },

  getRelease: async (toolSlug: string, version: number): Promise<ToolReleaseResponse> => {
    return apiRequest<ToolReleaseResponse>(`/admin/tools/${toolSlug}/releases/${version}`, { method: 'GET' });
  },

  createRelease: async (toolSlug: string, data: ToolReleaseCreate): Promise<ToolReleaseResponse> => {
    return apiRequest<ToolReleaseResponse>(`/admin/tools/${toolSlug}/releases`, { method: 'POST', body: data });
  },

  updateRelease: async (toolSlug: string, version: number, data: ToolReleaseUpdate): Promise<ToolReleaseResponse> => {
    return apiRequest<ToolReleaseResponse>(`/admin/tools/${toolSlug}/releases/${version}`, { method: 'PATCH', body: data });
  },

  activateRelease: async (toolSlug: string, version: number): Promise<ToolReleaseResponse> => {
    return apiRequest<ToolReleaseResponse>(`/admin/tools/${toolSlug}/releases/${version}/activate`, { method: 'POST' });
  },

  archiveRelease: async (toolSlug: string, version: number): Promise<ToolReleaseResponse> => {
    return apiRequest<ToolReleaseResponse>(`/admin/tools/${toolSlug}/releases/${version}/archive`, { method: 'POST' });
  },

  // ─────────────────────────────────────────────────────────────────────────
  // SYNC / RESCAN
  // ─────────────────────────────────────────────────────────────────────────

  rescanAllTools: async (): Promise<{ message: string; stats: Record<string, number> }> => {
    return apiRequest<{ message: string; stats: Record<string, number> }>('/admin/tool-groups/rescan', { method: 'POST' });
  },

  rescanGroupTools: async (groupSlug: string): Promise<{ message: string; stats: Record<string, number>; group_id: string }> => {
    return apiRequest<{ message: string; stats: Record<string, number>; group_id: string }>(`/admin/tool-groups/${groupSlug}/rescan`, { method: 'POST' });
  },

  rescanBackendReleases: async (toolSlug: string): Promise<{ message: string; stats: Record<string, number>; backend_releases: ToolBackendReleaseListItem[] }> => {
    return apiRequest<{ message: string; stats: Record<string, number>; backend_releases: ToolBackendReleaseListItem[] }>(`/admin/tools/${toolSlug}/rescan-backend`, { method: 'POST' });
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// QUERY KEYS
// ─────────────────────────────────────────────────────────────────────────────

// Aliases for backward compatibility
export const toolGroupsApi = toolReleasesApi;
export const toolsApi = toolReleasesApi;

export const toolReleasesKeys = {
  all: ['tool-releases'] as const,
  
  // Tool Groups
  groups: () => [...toolReleasesKeys.all, 'groups'] as const,
  groupsList: () => [...toolReleasesKeys.groups(), 'list'] as const,
  groupDetail: (slug: string) => [...toolReleasesKeys.groups(), 'detail', slug] as const,
  
  // Tools
  tools: () => [...toolReleasesKeys.all, 'tools'] as const,
  toolsByGroup: (groupSlug: string) => [...toolReleasesKeys.tools(), 'by-group', groupSlug] as const,
  toolDetail: (slug: string) => [...toolReleasesKeys.tools(), 'detail', slug] as const,
  
  // Backend Releases
  backendReleases: (toolSlug: string) => [...toolReleasesKeys.all, 'backend-releases', toolSlug] as const,
  backendReleaseDetail: (toolSlug: string, version: string) => 
    [...toolReleasesKeys.backendReleases(toolSlug), 'detail', version] as const,
  
  // Tool Releases
  releases: (toolSlug: string) => [...toolReleasesKeys.all, 'releases', toolSlug] as const,
  releaseDetail: (toolSlug: string, version: number) => 
    [...toolReleasesKeys.releases(toolSlug), 'detail', version] as const,
};
