import { apiRequest } from './http';

export interface PeriodicTask {
  slug: string;
  task_path: string;
  name: string;
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

export const periodicTasksApi = {
  async list(params: { category?: string; is_enabled?: boolean } = {}): Promise<PeriodicTaskListResponse> {
    const search = new URLSearchParams();
    if (params.category) search.set('category', params.category);
    if (typeof params.is_enabled === 'boolean') search.set('is_enabled', String(params.is_enabled));
    const query = search.toString();
    return apiRequest(`/admin/periodic-tasks${query ? `?${query}` : ''}`);
  },

  async toggle(slug: string, isEnabled: boolean): Promise<PeriodicTask> {
    return apiRequest(`/admin/periodic-tasks/${slug}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_enabled: isEnabled }),
    });
  },

  async runNow(slug: string): Promise<{ slug: string; queued: boolean; task_id?: string | null }> {
    return apiRequest(`/admin/periodic-tasks/${slug}/run`, { method: 'POST' });
  },
};
