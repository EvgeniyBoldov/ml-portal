/**
 * Sandbox API client — session-first architecture.
 */
import { apiRequest } from '@/shared/api';
import { API_BASE } from '@/shared/config';
import { getAccessToken } from '@/shared/api/http';
import type { ChatAttachment } from '@/shared/api/types';
import type {
  SandboxSessionListItem,
  SandboxSessionDetail,
  SandboxSessionCreate,
  SandboxSessionUpdate,
  SandboxBranchListItem,
  SandboxBranchOverride,
  SandboxRunListItem,
  SandboxRunDetail,
  SandboxConfirmAction,
  SandboxCatalog,
} from './types';

const BASE = '/sandbox';

export const sandboxApi = {
  // ── Sessions ────────────────────────────────────────────────────────────

  listSessions: (params?: {
    status?: string;
    skip?: number;
    limit?: number;
  }): Promise<SandboxSessionListItem[]> => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.skip != null) qs.set('skip', String(params.skip));
    if (params?.limit != null) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return apiRequest(`${BASE}/sessions${q ? `?${q}` : ''}`);
  },

  createSession: (data: SandboxSessionCreate): Promise<SandboxSessionDetail> =>
    apiRequest(`${BASE}/sessions`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getSession: (id: string): Promise<SandboxSessionDetail> =>
    apiRequest(`${BASE}/sessions/${id}`),

  updateSession: (
    id: string,
    data: SandboxSessionUpdate,
  ): Promise<SandboxSessionDetail> =>
    apiRequest(`${BASE}/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteSession: (id: string): Promise<void> =>
    apiRequest(`${BASE}/sessions/${id}`, { method: 'DELETE' }),

  getCatalog: (sessionId: string): Promise<SandboxCatalog> =>
    apiRequest(`${BASE}/sessions/${sessionId}/catalog`),

  // ── Branches & branch overrides ────────────────────────────────────────

  listBranches: (sessionId: string): Promise<SandboxBranchListItem[]> =>
    apiRequest(`${BASE}/sessions/${sessionId}/branches`),

  createBranch: (
    sessionId: string,
    data: {
      name: string;
      parent_branch_id?: string | null;
      parent_run_id?: string | null;
    },
  ): Promise<SandboxBranchListItem> =>
    apiRequest(`${BASE}/sessions/${sessionId}/branches`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  forkBranch: (
    sessionId: string,
    branchId: string,
    data: {
      name: string;
      parent_run_id?: string | null;
      copy_overrides?: boolean;
    },
  ): Promise<SandboxBranchListItem> =>
    apiRequest(`${BASE}/sessions/${sessionId}/branches/${branchId}/fork`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listBranchOverrides: (sessionId: string, branchId: string): Promise<SandboxBranchOverride[]> =>
    apiRequest(`${BASE}/sessions/${sessionId}/branches/${branchId}/overrides`),

  upsertBranchOverride: (
    sessionId: string,
    branchId: string,
    data: {
      entity_type: string;
      entity_id?: string | null;
      field_path: string;
      value_json: unknown;
      value_type?: string;
    },
  ): Promise<SandboxBranchOverride> =>
    apiRequest(`${BASE}/sessions/${sessionId}/branches/${branchId}/overrides`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteBranchOverrides: (
    sessionId: string,
    branchId: string,
    params?: {
      entity_type?: string;
      entity_id?: string | null;
      field_path?: string;
    },
  ): Promise<void> => {
    const qs = new URLSearchParams();
    if (params?.entity_type) qs.set('entity_type', params.entity_type);
    if (params?.field_path) qs.set('field_path', params.field_path);
    if (params?.entity_id) qs.set('entity_id', params.entity_id);
    const suffix = qs.toString();
    return apiRequest(
      `${BASE}/sessions/${sessionId}/branches/${branchId}/overrides${suffix ? `?${suffix}` : ''}`,
      { method: 'DELETE' },
    );
  },

  // ── Runs ────────────────────────────────────────────────────────────────

  listRuns: (sessionId: string, branchId?: string): Promise<SandboxRunListItem[]> => {
    const qs = new URLSearchParams();
    if (branchId) qs.set('branch_id', branchId);
    const suffix = qs.toString();
    return apiRequest(`${BASE}/sessions/${sessionId}/runs${suffix ? `?${suffix}` : ''}`);
  },

  getRunDetail: (sessionId: string, runId: string): Promise<SandboxRunDetail> =>
    apiRequest(`${BASE}/sessions/${sessionId}/runs/${runId}`),

  confirmRunAction: (
    sessionId: string,
    runId: string,
    data: SandboxConfirmAction,
  ): Promise<{ status: string; run_id: string }> =>
    apiRequest(`${BASE}/sessions/${sessionId}/runs/${runId}/confirm`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  uploadAttachment: async (sessionId: string, file: File): Promise<ChatAttachment> => {
    const form = new FormData();
    form.append('file', file);
    return apiRequest(`${BASE}/sessions/${sessionId}/uploads`, {
      method: 'POST',
      body: form,
      headers: {},
    });
  },

  // ── Run SSE stream ──────────────────────────────────────────────────────

  getRunStreamUrl: (sessionId: string): string => {
    const base = API_BASE.replace(/\/$/, '');
    return `${base}${BASE}/sessions/${sessionId}/run`;
  },

  getRunStreamHeaders: (): Record<string, string> => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    };
    const token = getAccessToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return headers;
  },
};
