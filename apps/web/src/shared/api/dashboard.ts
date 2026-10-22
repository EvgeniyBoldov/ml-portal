import { apiRequest } from './http';

export type DashboardPeriod = 1 | 7 | 30;

export interface UsageSummary {
  requests: number;
  chat_requests: number;
  shadow_requests: number;
  active_users: number;
  active_agents: number;
  failed_requests: number;
  completed_requests: number;
  error_rate: number | null;
}
export interface UsageBucket {
  at: string;
  requests: number;
  errors: number;
}
export interface DashboardModel {
  alias: string;
  id: string | null;
  name: string;
  type: string;
  enabled: boolean;
  health: string;
  checked_at: string | null;
  assignments: string[];
  calls: number;
  errors: number;
  tokens_in: number | null;
  tokens_out: number | null;
  estimated_calls: number;
  metered_calls: number;
  avg_duration_ms: number | null;
}
export interface DashboardAgent {
  slug: string;
  id: string | null;
  name: string;
  origin: string;
  executions: number;
  users: number;
  errors: number;
  avg_duration_ms: number | null;
}
export interface DashboardCollection {
  id: string;
  slug: string;
  name: string;
  documents: number;
  source_bytes: number;
  unknown_sizes: number;
  chunks: number;
  ready: number;
  processing: number;
  partial: number;
  failed: number;
  embedding_models: string[];
}
export interface DashboardMemoryScope {
  key: string;
  name: string;
  documents: number;
  pending: number;
  failed: number;
  status: string;
  nodes: number | null;
  edges: number | null;
  indexed_at: string | null;
}
export interface DashboardProblem {
  key: string;
  severity: 'warning' | 'danger';
  title: string;
  detail: string;
  count: number;
  last_at: string | null;
  href: string;
}
export interface DashboardOverview {
  days: DashboardPeriod;
  generated_at: string;
  period_start: string;
  coverage_started_at: string;
  current: UsageSummary;
  previous: UsageSummary;
  timeline: UsageBucket[];
  models: DashboardModel[];
  agents: DashboardAgent[];
  collections: DashboardCollection[];
  memory_scopes: DashboardMemoryScope[];
  memory_available: boolean;
  problems: DashboardProblem[];
}
export function getDashboard(
  days: DashboardPeriod
): Promise<DashboardOverview> {
  return apiRequest(`/admin/dashboard?days=${days}`);
}
