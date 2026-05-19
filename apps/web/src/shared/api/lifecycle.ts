import { apiRequest } from './http';

export type LifecycleKind = 'tenant' | 'user' | 'collection' | 'agent' | 'rbac_rule';
export type LifecycleMode = 'soft' | 'hard';
export type DependencyWillBe =
  | 'cascade_deleted'
  | 'migrated'
  | 'set_null'
  | 'blocker'
  | 'already_deprecated';

export interface DependencyEntity {
  uuid: string;
  name: string;
  url?: string;
}

export interface DependencyEntry {
  resource_type: string;
  count: number;
  action: string;
  will_be: DependencyWillBe;
  entities: DependencyEntity[];
  migration_target?: string | null;
  details?: Record<string, unknown>;
}

export interface DependencyGraphResponse {
  kind: LifecycleKind;
  entity_id: string;
  dependencies: DependencyEntry[];
}

export interface LifecycleReportResponse {
  kind: LifecycleKind;
  entity_id: string;
  mode: 'soft' | 'hard' | 'restore';
  lifecycle_status: string;
  details: Record<string, unknown>;
  migrated: Record<string, number>;
  cascaded: Record<string, number>;
  set_null: Record<string, number>;
  rbac_rules_removed: number;
  renamed: Array<{ old: string; new: string }>;
}

export const lifecycleApi = {
  async getDependencies(kind: LifecycleKind, entityId: string): Promise<DependencyGraphResponse> {
    return apiRequest(`/admin/lifecycle/${kind}/${entityId}/dependencies`);
  },

  async deleteEntity(
    kind: LifecycleKind,
    entityId: string,
    params: {
      mode: LifecycleMode;
      force?: boolean;
      reason?: string;
      retention_days?: number;
    },
  ): Promise<LifecycleReportResponse> {
    const mode = params.mode;
    const force = Boolean(params.force);
    return apiRequest(`/admin/lifecycle/${kind}/${entityId}?mode=${mode}&force=${force}`, {
      method: 'DELETE',
      body:
        mode === 'soft'
          ? {
              reason: params.reason || null,
              retention_days: params.retention_days ?? null,
            }
          : null,
    });
  },

  async restoreEntity(kind: LifecycleKind, entityId: string): Promise<LifecycleReportResponse> {
    return apiRequest(`/admin/lifecycle/${kind}/${entityId}/restore`, {
      method: 'POST',
    });
  },
};

