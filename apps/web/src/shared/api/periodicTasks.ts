import { apiRequest } from './http';

export interface PeriodicTask {
  slug: string;
  task_path: string;
  name: string;
  description?: string | null;
  category: string;
  default_schedule: Record<string, unknown>;
  is_enabled: boolean;
  is_orphaned: boolean;
  last_run_at?: string | null;
  last_status?: string | null;
  last_duration_ms?: number | null;
  last_error?: string | null;
}

export interface PeriodicTaskListResponse {
  items: PeriodicTask[];
  total: number;
}

export interface PeriodicRunSummary {
  id: string;
  source: string;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
}

export interface PeriodicTaskDetail extends PeriodicTask {
  runs: PeriodicRunSummary[];
}

export interface PeriodicRunDetail extends PeriodicRunSummary {
  events: { at: string; level: string; message: string }[];
  result: unknown;
  result_limited: boolean;
  error: string | null;
}

function taskPath(slug: string) {
  return `/admin/periodic-tasks/${encodeURIComponent(slug)}`;
}

export const periodicTasksApi = {
  async list(
    params: { category?: string; is_enabled?: boolean } = {}
  ): Promise<PeriodicTaskListResponse> {
    const search = new URLSearchParams();
    if (params.category) search.set('category', params.category);
    if (typeof params.is_enabled === 'boolean')
      search.set('is_enabled', String(params.is_enabled));
    const query = search.toString();
    return apiRequest(`/admin/periodic-tasks${query ? `?${query}` : ''}`);
  },

  async get(slug: string): Promise<PeriodicTaskDetail> {
    return apiRequest(taskPath(slug));
  },

  async getRun(slug: string, id: string): Promise<PeriodicRunDetail> {
    return apiRequest(`${taskPath(slug)}/runs/${encodeURIComponent(id)}`);
  },

  async toggle(slug: string, isEnabled: boolean): Promise<PeriodicTask> {
    return apiRequest(taskPath(slug), {
      method: 'PATCH',
      body: JSON.stringify({ is_enabled: isEnabled }),
    });
  },

  async runNow(
    slug: string
  ): Promise<{ slug: string; queued: boolean; task_id?: string | null }> {
    return apiRequest(`${taskPath(slug)}/run`, { method: 'POST' });
  },
};
