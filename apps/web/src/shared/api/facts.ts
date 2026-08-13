import { apiRequest } from './http';

export interface Fact {
  id: string;
  owner_type?: string;
  owner_id?: string;
  scope: string;
  subject: string;
  value: string;
  confidence: number;
  source: string;
  status?: string;
  support_count?: number;
  observed_at: string;
  created_at: string;
}

export interface FactInput {
  subject: string;
  value: string;
}

export type FactOwner = 'user' | 'tenant';

export const factsApi = {
  listProfile: () => apiRequest<Fact[]>('/profile/facts'),
  createProfile: (data: FactInput) => apiRequest<Fact>('/profile/facts', { method: 'POST', body: data }),
  updateProfile: (id: string, data: FactInput) => apiRequest<Fact>(`/profile/facts/${id}`, { method: 'PUT', body: data }),
  deleteProfile: (ids: string[]) => apiRequest<{ deleted: number }>('/profile/facts', { method: 'DELETE', body: { ids } }),
  listAdmin: (owner: FactOwner, ownerId: string) => apiRequest<Fact[]>(`/admin/${owner === 'user' ? 'users' : 'tenants'}/${ownerId}/facts`),
  createAdmin: (owner: FactOwner, ownerId: string, data: FactInput) => apiRequest<Fact>(`/admin/${owner === 'user' ? 'users' : 'tenants'}/${ownerId}/facts`, { method: 'POST', body: data }),
  updateAdmin: (owner: FactOwner, ownerId: string, factId: string, data: FactInput) => apiRequest<Fact>(`/admin/${owner === 'user' ? 'users' : 'tenants'}/${ownerId}/facts/${factId}`, { method: 'PUT', body: data }),
  deleteAdmin: (owner: FactOwner, ownerId: string, factId: string) => apiRequest<void>(`/admin/${owner === 'user' ? 'users' : 'tenants'}/${ownerId}/facts/${factId}`, { method: 'DELETE' }),
};
