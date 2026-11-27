import { apiRequest } from './http';

interface ExternalRequestSummary {
  run_id: string;
  source: string;
  status: string;
  user_name: string;
  created_at: string;
  updated_at: string;
}

export interface ExternalRequestListItem extends ExternalRequestSummary {
  text_preview: string;
}

export interface ExternalRequestTimelineItem {
  id: string;
  kind: string;
  occurred_at: string;
  text: string | null;
  answer: string | boolean | null;
  wake_at: string | null;
  resolved_at: string | null;
  delivery_status: string | null;
  delivered_at: string | null;
  delivery_attempts: number;
}

export interface ExternalRequestDetail extends ExternalRequestSummary {
  text: string;
  completed_at: string | null;
  timeline: ExternalRequestTimelineItem[];
}

export function listExternalRequests(limit: number, offset: number) {
  return apiRequest<{ items: ExternalRequestListItem[]; total: number }>('/admin/agent-runs/external-requests', {
    query: { limit, offset },
  });
}

export function getExternalRequest(id: string) {
  return apiRequest<ExternalRequestDetail>(`/admin/agent-runs/external-requests/${encodeURIComponent(id)}`);
}
