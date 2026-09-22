import { apiRequest } from './http';
import type {
  PaginatedResponse,
  Chat,
  ChatCreateRequest,
  ChatUpdateRequest,
  ChatTagsUpdateRequest,
  ChatMessageCreateRequest,
  ChatMessageResponse,
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
  cursor?: string
) {
  const qs = new URLSearchParams();
  if (limit) qs.set('limit', String(limit));
  if (cursor) qs.set('cursor', cursor);
  return apiRequest<{
    items: ChatMessage[];
    next_cursor: string | null;
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
  return apiRequest<{ pause: ChatPausedRun | null }>(`/chats/${chatId}/paused-run`);
}

export async function sendMessage(
  chat_id: string,
  body: ChatMessageCreateRequest
) {
  return apiRequest<ChatMessageResponse>(`/chats/${chat_id}/messages`, {
    method: 'POST',
    body: JSON.stringify(body),
    idempotent: true,
  });
}

export async function issueConfirmationToken(chatId: string, operationFingerprint: string) {
  return apiRequest<{ token: string; expires_at: string }>(`/chats/${chatId}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ operation_fingerprint: operationFingerprint }),
  });
}

export async function renameChat(chat_id: string, name: string) {
  const body: ChatUpdateRequest = { name };
  return apiRequest<Chat>(`/chats/${chat_id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function generateChatTitle(chatId: string) {
  return apiRequest<{ title: string | null; generated: boolean }>(`/chats/${chatId}/title-generation`, {
    method: 'POST',
  });
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
  action: 'confirm' | 'cancel' | 'input',
  input?: string,
  signal?: AbortSignal,
): Promise<Response> {
  const { fetchStreamWithAuth } = await import('@/shared/api/streamAuth');
  const body: Record<string, string> = { action };
  if (action === 'input' && input) {
    body.input = input;
  }
  return fetchStreamWithAuth(`/chats/runs/${runId}/resume`, {
    body,
    signal,
  });
}

/** Chat agent info for UI selection */
export interface ChatAgent {
  slug: string;
  name: string;
  description?: string;
  has_rag: boolean;
  has_collections: boolean;
  tools: string[];
}

/** Get list of available agents for chat */
export async function listChatAgents() {
  return apiRequest<{ agents: ChatAgent[] }>('/chats/agents');
}

export async function getChatUploadPolicy() {
  return apiRequest<ChatUploadPolicy>('/chats/uploads/policy');
}

export async function uploadChatAttachment(chatId: string, file: File) {
  const form = new FormData();
  form.append('file', file);
  return apiRequest<ChatAttachment>(`/chats/${chatId}/uploads`, {
    method: 'POST',
    body: form,
    headers: {},
  });
}
