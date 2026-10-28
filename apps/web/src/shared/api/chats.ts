import { apiRequest } from './http';
import { fetchSseWithAuth, fetchStreamWithAuth } from './streamAuth';
import type {
  PaginatedResponse,
  Chat,
  ChatCreateRequest,
  ChatUpdateRequest,
  ChatTagsUpdateRequest,
  ChatMessage,
  ChatAttachment,
  ChatUploadPolicy,
} from './types';

/** Bounded user-safe projection of chat-local working context. */
export interface ChatContextInspection {
  revision: number;
  focus: Record<string, unknown>;
  active_goal: Record<string, unknown> | null;
  term_bindings: Array<Record<string, unknown>>;
  artifacts: Array<Record<string, unknown>>;
  open_loops: Array<Record<string, unknown>>;
  decisions: Array<Record<string, unknown>>;
  recent_anchor: Record<string, unknown> | null;
  task_results: Array<Record<string, unknown>>;
}

export interface ChatContextResetResult {
  revision: number;
  closed_items: number;
}

export async function listChats(
  params: { cursor?: string; limit?: number; q?: string } = {}
) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set('limit', String(params.limit));
  if (params.cursor) qs.set('cursor', params.cursor);
  if (params.q) qs.set('q', params.q);
  return apiRequest<PaginatedResponse<Chat>>(`/chats?${qs.toString()}`);
}

export async function createChat(name?: string | null, tags?: string[] | null) {
  const body: ChatCreateRequest = { name: name ?? null, tags: tags ?? null };
  return apiRequest<{ chat_id: string }>('/chats', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function listMessages(
  chatId: string,
  limit: number = 50,
  cursor?: string,
  options: { tail?: boolean; before?: string } = {}
) {
  const qs = new URLSearchParams();
  if (limit) qs.set('limit', String(limit));
  if (cursor) qs.set('cursor', cursor);
  if (options.tail) qs.set('tail', 'true');
  if (options.before) qs.set('before', options.before);
  return apiRequest<{
    items: ChatMessage[];
    next_cursor: string | null;
    previous_cursor?: string | null;
    limit: number;
  }>(`/chats/${chatId}/messages?${qs.toString()}`);
}

export interface ChatPausedRun {
  run_id: string;
  reason: string;
  action: Record<string, unknown>;
  context: Record<string, unknown>;
  contract_version: number;
}

/** Restore the current interaction after navigation or a page refresh. */
export async function getPausedRun(chatId: string) {
  return apiRequest<{ pause: ChatPausedRun | null }>(
    `/chats/${chatId}/paused-run`
  );
}

export interface ActiveChatRun {
  run_id: string;
  turn_id: string;
  status: 'running';
  user_message_id: string | null;
  stage?: 'preparing' | 'planning' | 'executing' | 'synthesizing' | 'finalizing' | null;
  activity?: {
    run_id: string;
    stage: 'preparing' | 'planning' | 'executing' | 'synthesizing' | 'finalizing';
    action: string;
    description: string;
    outcome?: string | null;
  } | null;
}

export type ChatLifecycleStatus =
  | 'running'
  | 'waiting_input'
  | 'waiting_confirmation'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type ChatExecutionStage =
  | 'preparing'
  | 'planning'
  | 'executing'
  | 'synthesizing'
  | 'finalizing';

/** Content-free lifecycle projection for the latest turn in one owned chat. */
export interface ChatStatusSnapshot {
  chat_id: string;
  run_id: string | null;
  status: ChatLifecycleStatus;
  stage: ChatExecutionStage | null;
  updated_at: string | null;
  stage_updated_at: string | null;
}

export function fetchChatStatusEvents(signal?: AbortSignal) {
  return fetchSseWithAuth('/chats/status-events', signal);
}

export async function getActiveChatRun(chatId: string) {
  return apiRequest<{ run: ActiveChatRun | null }>(
    `/chats/${chatId}/active-run`
  );
}

export function attachChatRun(
  chatId: string,
  runId: string,
  signal?: AbortSignal
) {
  return fetchSseWithAuth(`/chats/${chatId}/runs/${runId}/events`, signal);
}

export function stopChatRun(chatId: string, runId: string) {
  return apiRequest<{ run_id: string; accepted: boolean }>(
    `/chats/${chatId}/runs/${runId}/cancel`, { method: 'POST' }
  );
}

export async function renameChat(chat_id: string, name: string) {
  const body: ChatUpdateRequest = { name };
  return apiRequest<Chat>(`/chats/${chat_id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function generateChatTitle(chatId: string) {
  return apiRequest<{ title: string | null; generated: boolean }>(
    `/chats/${chatId}/title-generation`,
    {
      method: 'POST',
    }
  );
}

export async function updateChatTags(chat_id: string, tags: string[]) {
  const body: ChatTagsUpdateRequest = { tags };
  return apiRequest<{ id: string; tags: string[] }>(`/chats/${chat_id}/tags`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

export async function deleteChat(chat_id: string) {
  return apiRequest<{ id: string; deleted: boolean }>(`/chats/${chat_id}`, {
    method: 'DELETE',
  });
}

export async function getChatContext(chatId: string) {
  return apiRequest<ChatContextInspection>(`/chats/${chatId}/context`);
}

export async function resetChatContext(chatId: string) {
  return apiRequest<ChatContextResetResult>(`/chats/${chatId}/context`, {
    method: 'DELETE',
    idempotent: true,
  });
}

/** Resume a paused run (confirm/cancel/input action) - returns Response for SSE streaming */
export async function resumeRunStream(
  runId: string,
  action: 'confirm' | 'cancel' | 'input' | 'answer',
  input?: string | boolean,
  signal?: globalThis.AbortSignal,
  pauseId?: string | null,
  hasInteraction = false
): Promise<Response> {
  const body: Record<string, unknown> = { action };
  if (pauseId) body.pause_id = pauseId;
  if ((hasInteraction || action === 'answer') && action !== 'cancel') {
    body.action = 'answer';
    body.response = action === 'confirm' ? true : input;
  } else if (action === 'input' && input) {
    body.input = input;
  }
  return fetchStreamWithAuth(`/chats/runs/${runId}/resume`, {
    body,
    signal,
  });
}

export async function getChatUploadPolicy() {
  return apiRequest<ChatUploadPolicy>('/chats/uploads/policy');
}

export async function uploadChatAttachment(
  chatId: string,
  file: File,
  signal?: globalThis.AbortSignal
) {
  const form = new FormData();
  form.append('file', file);
  return apiRequest<ChatAttachment>(`/chats/${chatId}/uploads`, {
    method: 'POST',
    body: form,
    signal,
    headers: {},
  });
}
