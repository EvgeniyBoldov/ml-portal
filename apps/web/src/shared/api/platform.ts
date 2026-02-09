import { apiRequest } from './http';

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export interface PlatformSettings {
  id: string;
  default_policy_id?: string | null;
  default_limit_id?: string | null;
  default_rbac_policy_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlatformSettingsUpdate {
  default_policy_id?: string | null;
  default_limit_id?: string | null;
  default_rbac_policy_id?: string | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────

export const platformApi = {
  async get(): Promise<PlatformSettings> {
    return apiRequest('/admin/platform');
  },

  async update(data: PlatformSettingsUpdate): Promise<PlatformSettings> {
    return apiRequest('/admin/platform', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },
};
