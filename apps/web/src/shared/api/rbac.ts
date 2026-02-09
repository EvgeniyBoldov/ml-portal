import { apiRequest } from './http';

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export type RbacLevel = 'platform' | 'tenant' | 'user';
export type ResourceType = 'agent' | 'toolgroup' | 'tool' | 'instance';
export type RbacEffect = 'allow' | 'deny';

export interface RbacRule {
  id: string;
  rbac_policy_id: string;
  level: RbacLevel;
  level_id?: string | null;
  resource_type: ResourceType;
  resource_id: string;
  effect: RbacEffect;
  created_at: string;
  created_by_user_id?: string | null;
}

export interface RbacPolicy {
  id: string;
  slug: string;
  name: string;
  description?: string | null;
  rules_count: number;
  created_at: string;
  updated_at: string;
}

export interface RbacPolicyDetail {
  id: string;
  slug: string;
  name: string;
  description?: string | null;
  rules: RbacRule[];
  created_at: string;
  updated_at: string;
}

export interface RbacPolicyCreate {
  slug: string;
  name: string;
  description?: string;
}

export interface RbacPolicyUpdate {
  name?: string;
  description?: string;
}

export interface RbacRuleCreate {
  level: RbacLevel;
  level_id?: string | null;
  resource_type: ResourceType;
  resource_id: string;
  effect: RbacEffect;
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

export interface EnrichedRulePolicyInfo {
  id: string;
  slug: string;
  name: string;
}

export interface EnrichedRuleResourceInfo {
  type: ResourceType;
  id: string;
  name: string;
}

export interface EnrichedRuleInfo {
  effect: RbacEffect;
  level: RbacLevel;
  level_id?: string | null;
  context_name?: string | null;
  created_at: string;
  created_by_user_id?: string | null;
}

export interface EnrichedRule {
  id: string;
  policy: EnrichedRulePolicyInfo;
  resource: EnrichedRuleResourceInfo;
  rule: EnrichedRuleInfo;
}

export interface EnrichedRulesFilters {
  rbac_policy_id?: string;
  level?: RbacLevel;
  level_id?: string;
  resource_type?: ResourceType;
  effect?: RbacEffect;
  skip?: number;
  limit?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────

export const rbacApi = {
  // Policy CRUD
  async listPolicies(params: { skip?: number; limit?: number } = {}): Promise<RbacPolicy[]> {
    const sp = new URLSearchParams();
    if (params.skip) sp.set('skip', String(params.skip));
    if (params.limit) sp.set('limit', String(params.limit));
    return apiRequest(`/admin/rbac?${sp.toString()}`);
  },

  async getPolicy(slug: string): Promise<RbacPolicyDetail> {
    return apiRequest(`/admin/rbac/${slug}`);
  },

  async createPolicy(data: RbacPolicyCreate): Promise<RbacPolicyDetail> {
    return apiRequest('/admin/rbac', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updatePolicy(slug: string, data: RbacPolicyUpdate): Promise<RbacPolicyDetail> {
    return apiRequest(`/admin/rbac/${slug}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async deletePolicy(slug: string): Promise<void> {
    return apiRequest(`/admin/rbac/${slug}`, {
      method: 'DELETE',
    });
  },

  // Rule CRUD
  async listRules(
    policySlug: string,
    params: { level?: string; resource_type?: string } = {},
  ): Promise<RbacRule[]> {
    const sp = new URLSearchParams();
    if (params.level) sp.set('level', params.level);
    if (params.resource_type) sp.set('resource_type', params.resource_type);
    return apiRequest(`/admin/rbac/${policySlug}/rules?${sp.toString()}`);
  },

  async createRule(policySlug: string, data: RbacRuleCreate): Promise<RbacRule> {
    return apiRequest(`/admin/rbac/${policySlug}/rules`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateRule(policySlug: string, ruleId: string, data: RbacRuleUpdate): Promise<RbacRule> {
    return apiRequest(`/admin/rbac/${policySlug}/rules/${ruleId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async deleteRule(policySlug: string, ruleId: string): Promise<void> {
    return apiRequest(`/admin/rbac/${policySlug}/rules/${ruleId}`, {
      method: 'DELETE',
    });
  },

  // Access check
  async checkAccess(policySlug: string, data: CheckAccessRequest): Promise<CheckAccessResponse> {
    return apiRequest(`/admin/rbac/${policySlug}/check-access`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Enriched rules (cross-policy, with resource names)
  async listEnrichedRules(params: EnrichedRulesFilters = {}): Promise<EnrichedRule[]> {
    const sp = new URLSearchParams();
    if (params.rbac_policy_id) sp.set('rbac_policy_id', params.rbac_policy_id);
    if (params.level) sp.set('level', params.level);
    if (params.level_id) sp.set('level_id', params.level_id);
    if (params.resource_type) sp.set('resource_type', params.resource_type);
    if (params.effect) sp.set('effect', params.effect);
    if (params.skip) sp.set('skip', String(params.skip));
    if (params.limit) sp.set('limit', String(params.limit));
    return apiRequest(`/admin/rbac/rules?${sp.toString()}`);
  },
};
