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
  lifecycle_status?: string;
  deprecated_at?: string | null;
  retention_days?: number;
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
  level?: RbacLevel;
  effect?: RbacEffect;
  resource_type?: ResourceType;
  resource_id?: string;
  owner_user_id?: string | null;
  owner_tenant_id?: string | null;
  owner_platform?: boolean;
}

export interface ExplainAccessRequest {
  user_id?: string;
  tenant_id?: string;
  resource_type: ResourceType | 'collection' | 'operation';
  resource_id: string;
}

export interface AccessDecisionLayer {
  level: RbacLevel | 'default';
  owner_name: string | null;
  rule_id: string | null;
  effect: RbacEffect | null;
}

export interface ExplainAccessResponse {
  effect: RbacEffect;
  layers: AccessDecisionLayer[];
}

// ─── Enriched Rules ──────────────────────────────────────────────────────────

interface EnrichedOwnerInfo {
  level: RbacLevel;
  name: string;
  user_id?: string | null;
  tenant_id?: string | null;
  platform: boolean;
}

interface EnrichedResourceInfo {
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
  lifecycle_status?: string;
  deprecated_at?: string | null;
  retention_days?: number;
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
  include_deprecated?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────

export const rbacApi = {
  // Rule CRUD
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
  async getEnrichedRule(ruleId: string): Promise<EnrichedRule> {
    return apiRequest(`/admin/rbac/rules/${ruleId}`);
  },

  async explainAccess(data: ExplainAccessRequest): Promise<ExplainAccessResponse> {
    return apiRequest('/admin/rbac/explain-access', {
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
    if (params.include_deprecated !== undefined) sp.set('include_deprecated', String(params.include_deprecated));
    return apiRequest(`/admin/rbac/rules?${sp.toString()}`);
  },
};
