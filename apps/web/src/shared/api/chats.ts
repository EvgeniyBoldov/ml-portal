import { API_BASE } from '@/shared/config';
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

type WindowWithAuthTokens = Window & {
  __auth_tokens?: { access_token?: string };
};

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

export async function* sendMessageStreamSSE(
  chatId: string,
  content: string,
  opts: {
    idempotencyKey?: string;
    useRag?: boolean;
    model?: string | null;
    agentSlug?: string | null;
    attachmentIds?: string[];
  } = {}
) {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  };

  // Add auth token if available
  const token =
    (window as WindowWithAuthTokens).__auth_tokens?.access_token ||
    localStorage.getItem('access_token');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Add idempotency key if provided
  if (opts?.idempotencyKey) {
    headers['Idempotency-Key'] = opts.idempotencyKey;
  }

  const res = await fetch(`${API_BASE}/chats/${chatId}/messages`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      content,
      use_rag: opts?.useRag ?? false,
      model: opts?.model ?? null,
      agent_slug: opts?.agentSlug ?? null,
      attachment_ids: opts?.attachmentIds ?? [],
    }),
  });

  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

  // Simple SSE parser
  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buf = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buf += decoder.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop() ?? '';

    for (const part of parts) {
      let event = 'message';
      const dataLines: string[] = [];

      for (const line of part.split('\n')) {
        if (line.startsWith('event:')) {
          event = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          const dataContent = line.slice(5).replace(/^ /, '');
          dataLines.push(dataContent);
        }
      }

      const data = dataLines.join('\n');

      // Emit structured events
      if (event === 'delta') {
        yield { type: 'delta' as const, data };
      } else if (event === 'final') {
        try {
          const parsed = JSON.parse(data) as { message_id?: string };
          yield { type: 'final' as const, message_id: parsed.message_id };
        } catch (error: unknown) {
          // Fallback if parsing fails
          yield { type: 'final' as const, message_id: data };
        }
      } else if (event === 'error') {
        yield { type: 'error' as const, data };
      } else if (data === '[DONE]') {
        yield { type: 'done' as const };
      }
    }
  }
}

export async function renameChat(chat_id: string, name: string) {
  const body: ChatUpdateRequest = { name };
  return apiRequest<Chat>(`/chats/${chat_id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
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

/** Resume a paused run (confirm action) */
export async function resumeRun(runId: string, action: 'confirm' | 'cancel' | 'input', input?: string) {
  const body: Record<string, string> = { action };
  if (action === 'input' && input) {
    body.input = input;
  }
  return apiRequest<{
    run_id: string;
    status: string;
    paused_action?: Record<string, unknown>;
    paused_context?: Record<string, unknown>;
    paused_again_reason?: string;
    paused_again_run_id?: string;
    paused_again_action?: Record<string, unknown>;
    paused_again_context?: Record<string, unknown>;
    user_input?: string;
  }>(`/chats/runs/${runId}/resume`, {
    method: 'POST',
    body: JSON.stringify(body),
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

export async function getChatAttachmentDownloadLink(attachmentId: string) {
  return apiRequest<{
    id: string;
    file_name: string;
    content_type?: string | null;
    size_bytes: number;
    url: string;
    expires_in: number;
  }>(`/chats/attachments/${attachmentId}/download`);
}
