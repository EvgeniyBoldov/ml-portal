/**
 * Sandbox domain types — mirrors backend schemas.
 */

// ── Session ─────────────────────────────────────────────────────────────────

export interface SandboxSessionListItem {
  id: string;
  owner_id: string;
  owner_email: string;
  name: string;
  status: 'active' | 'archived';
  ttl_days: number;
  expires_at: string;
  last_activity_at: string;
  overrides_count: number;
  runs_count: number;
  created_at: string;
}

export interface SandboxSessionDetail {
  id: string;
  owner_id: string;
  owner_email: string;
  name: string;
  status: 'active' | 'archived';
  ttl_days: number;
  expires_at: string;
  last_activity_at: string;
  overrides: SandboxOverride[];
  runs: SandboxRunListItem[];
  created_at: string;
  updated_at: string;
}

export interface SandboxSessionCreate {
  name?: string;
  ttl_days?: number;
}

export interface SandboxSessionUpdate {
  name?: string;
  ttl_days?: number;
}

// ── Override ────────────────────────────────────────────────────────────────

export type OverrideEntityType =
  | 'agent_version'
  | 'discovered_tool'
  | 'tool_release'
  | 'orchestration'
  | 'policy'
  | 'limit'
  | 'model';

export interface SandboxOverride {
  id: string;
  entity_type: OverrideEntityType;
  entity_id: string | null;
  label: string;
  is_active: boolean;
  config_snapshot: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SandboxBranchListItem {
  id: string;
  session_id: string;
  name: string;
  parent_branch_id: string | null;
  parent_run_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface SandboxBranchOverride {
  id: string;
  branch_id: string;
  entity_type: string;
  entity_id: string | null;
  field_path: string;
  value_json: unknown;
  value_type: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

// ── Run ─────────────────────────────────────────────────────────────────────

export interface SandboxRunListItem {
  id: string;
  branch_id: string | null;
  snapshot_id: string | null;
  parent_run_id: string | null;
  request_text: string;
  status: 'running' | 'completed' | 'failed' | 'waiting_confirmation' | 'waiting_input';
  started_at: string;
  finished_at: string | null;
  steps_count: number;
}

export interface SandboxRunDetail {
  id: string;
  branch_id: string | null;
  snapshot_id: string | null;
  parent_run_id: string | null;
  request_text: string;
  status: string;
  effective_config: Record<string, unknown>;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  steps: SandboxRunStep[];
}

export interface SandboxRunCreate {
  request_text: string;
  branch_id?: string | null;
  parent_run_id?: string | null;
  attachment_ids?: string[] | null;
}

// ── Run Step ────────────────────────────────────────────────────────────────

export interface SandboxRunStep {
  id: string;
  step_type: string;
  step_data: Record<string, unknown>;
  order_num: number;
  created_at: string;
}

// ── SSE events (streamed from backend) ──────────────────────────────────────

export interface SandboxSSEEvent {
  type: string;
  run_id?: string;
  [key: string]: unknown;
}

// ── Confirm ─────────────────────────────────────────────────────────────────

export interface SandboxConfirmAction {
  confirmed: boolean;
}

// ── Catalog (sidebar data) ──────────────────────────────────────────────────

export interface SandboxCatalogToolVersion {
  id: string;
  version: number;
  status: string;
}

export interface SandboxCatalogTool {
  id: string;
  tool_id: string | null;
  slug: string;
  name: string;
  description?: string | null;
  source: string;
  domains: string[];
  input_schema?: Record<string, unknown> | null;
  output_schema?: Record<string, unknown> | null;
  published: boolean;
  current_version_id: string | null;
  versions: SandboxCatalogToolVersion[];
}

export interface SandboxCatalogDomainGroup {
  domain: string;
  tools: SandboxCatalogTool[];
}

export interface SandboxResolverFieldSpec {
  key: string;
  label: string;
  field_path: string;
  field_type: 'tags' | 'select' | 'json' | 'text' | 'integer' | 'float' | 'boolean';
  editable: boolean;
  options: string[];
  help_text?: string | null;
  source_key?: string | null;
}

export interface SandboxResolverSectionSpec {
  title: string;
  fields: SandboxResolverFieldSpec[];
}

export interface SandboxResolverBlueprint {
  key: string;
  title: string;
  entity_type: string;
  entity_id: string | null;
  description: string | null;
  sections: SandboxResolverSectionSpec[];
}

export interface SandboxCatalogAgentVersion {
  id: string;
  version: number;
  status: string;
}

export interface SandboxCatalogAgent {
  id: string;
  slug: string;
  name: string;
  current_version_id: string | null;
  versions: SandboxCatalogAgentVersion[];
}

export interface SandboxCatalogRouter {
  id: string;
  name: string;
  description: string;
  config?: Record<string, unknown>;
}

export interface SandboxCatalog {
  tools: SandboxCatalogTool[];
  domain_groups: SandboxCatalogDomainGroup[];
  agents: SandboxCatalogAgent[];
  system_routers: SandboxCatalogRouter[];
  resolver_blueprints: SandboxResolverBlueprint[];
}

export type SandboxSelectableType = 'agent' | 'tool' | 'router' | 'parameter' | 'run';

export interface SandboxSelectedItem {
  type: SandboxSelectableType;
  id: string;
  name: string;
  versionId?: string | null;
}
