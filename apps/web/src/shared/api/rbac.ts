import { apiRequest } from './http';

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export type RbacLevel = 'platform' | 'tenant' | 'user';
export type ResourceType = 'agent' | 'tool' | 'instance';
export type RbacEffect = 'allow' | 'deny';

export interface RbacRule {
  id: string;
  level: RbacLevel;
  owner_user_id?: string | null;
  owner_tenant_id?: string | null;
  owner_platform: boolean;
  resource_type: ResourceType;
  resource_id: string;
  effect: RbacEffect;
  created_at: string;
  created_by_user_id?: string | null;
}

export interface RbacRuleCreate {
  level: RbacLevel;
  resource_type: ResourceType;
  resource_id: string;
  effect: RbacEffect;
  owner_user_id?: string | null;
  owner_tenant_id?: string | null;
  owner_platform?: boolean;
}

export interface RbacRuleUpdate {
  effect: RbacEffect;
}

export interface CheckAccessRequest {
  user_id: string;
  tenant_id: string;
  resource_type: ResourceType;
  resource_id: string;
}

export interface CheckAccessResponse {
  effect: RbacEffect;
  resource_type: ResourceType;
  resource_id: string;
}

// ─── Enriched Rules ──────────────────────────────────────────────────────────

export interface EnrichedOwnerInfo {
  level: RbacLevel;
  name: string;
  user_id?: string | null;
  tenant_id?: string | null;
  platform: boolean;
}

export interface EnrichedResourceInfo {
  type: ResourceType;
  id: string;
  name: string;
  slug?: string | null;
}

export interface EnrichedRule {
  id: string;
  owner: EnrichedOwnerInfo;
  resource: EnrichedResourceInfo;
  effect: RbacEffect;
  created_at: string;
  created_by_user_id?: string | null;
  created_by_name?: string | null;
}

export interface EnrichedRulesFilters {
  level?: RbacLevel;
  owner_user_id?: string;
  owner_tenant_id?: string;
  owner_platform?: boolean;
  resource_type?: ResourceType;
  resource_id?: string;
  effect?: RbacEffect;
  skip?: number;
  limit?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────

export const rbacApi = {
  // Rule CRUD
  async listRules(params: EnrichedRulesFilters = {}): Promise<RbacRule[]> {
    const sp = new URLSearchParams();
    if (params.level) sp.set('level', params.level);
    if (params.owner_user_id) sp.set('owner_user_id', params.owner_user_id);
    if (params.owner_tenant_id) sp.set('owner_tenant_id', params.owner_tenant_id);
    if (params.owner_platform !== undefined) sp.set('owner_platform', String(params.owner_platform));
    if (params.resource_type) sp.set('resource_type', params.resource_type);
    if (params.resource_id) sp.set('resource_id', params.resource_id);
    if (params.effect) sp.set('effect', params.effect);
    if (params.skip) sp.set('skip', String(params.skip));
    if (params.limit) sp.set('limit', String(params.limit));
    return apiRequest(`/admin/rbac?${sp.toString()}`);
  },

  async getRule(ruleId: string): Promise<RbacRule> {
    return apiRequest(`/admin/rbac/${ruleId}`);
  },

  async createRule(data: RbacRuleCreate): Promise<RbacRule> {
    return apiRequest('/admin/rbac', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateRule(ruleId: string, data: RbacRuleUpdate): Promise<RbacRule> {
    return apiRequest(`/admin/rbac/${ruleId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async deleteRule(ruleId: string): Promise<void> {
    return apiRequest(`/admin/rbac/${ruleId}`, {
      method: 'DELETE',
    });
  },

  // Access check
  async checkAccess(data: CheckAccessRequest): Promise<CheckAccessResponse> {
    return apiRequest('/admin/rbac/check-access', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Enriched rules (with owner and resource names)
  async listEnrichedRules(params: EnrichedRulesFilters = {}): Promise<EnrichedRule[]> {
    const sp = new URLSearchParams();
    if (params.level) sp.set('level', params.level);
    if (params.owner_user_id) sp.set('owner_user_id', params.owner_user_id);
    if (params.owner_tenant_id) sp.set('owner_tenant_id', params.owner_tenant_id);
    if (params.owner_platform !== undefined) sp.set('owner_platform', String(params.owner_platform));
    if (params.resource_type) sp.set('resource_type', params.resource_type);
    if (params.resource_id) sp.set('resource_id', params.resource_id);
    if (params.effect) sp.set('effect', params.effect);
    if (params.skip) sp.set('skip', String(params.skip));
    if (params.limit) sp.set('limit', String(params.limit));
    return apiRequest(`/admin/rbac/rules?${sp.toString()}`);
  },
};
