import { apiRequest } from './http';

export interface IntegrationSettings {
  name: string;
  connector_id: string;
  is_active: boolean;
}

export interface IntegrationCreate extends IntegrationSettings {
  source: string;
}

export interface AssignmentIntegration extends IntegrationCreate {
  id: string;
}

export interface IntegrationToken {
  id: string;
  name: string;
  token_prefix: string;
  is_active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

const path = '/admin/integrations';

export const assignmentIntegrationsApi = {
  list: () => apiRequest<AssignmentIntegration[]>(path),
  get: (id: string) => apiRequest<AssignmentIntegration>(`${path}/${id}`),
  create: (data: IntegrationCreate) => apiRequest<AssignmentIntegration>(path, { method: 'POST', body: data }),
  update: (id: string, data: IntegrationSettings) =>
    apiRequest<AssignmentIntegration>(`${path}/${id}`, { method: 'PUT', body: data }),
  tokens: (id: string) => apiRequest<IntegrationToken[]>(`${path}/${id}/tokens`),
  issue: (id: string, data: { name: string; expires_days: number | null }) =>
    apiRequest<IntegrationToken & { token: string }>(`${path}/${id}/tokens`, { method: 'POST', body: data }),
  revoke: (id: string, tokenId: string) =>
    apiRequest<void>(`${path}/${id}/tokens/${tokenId}`, { method: 'DELETE' }),
};
