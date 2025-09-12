import { api } from './client'
import { parseSSE } from '@shared/lib/sse'
import type { 
  PaginatedResponse, 
  Chat, 
  ChatCreateRequest, 
  ChatUpdateRequest, 
  ChatTagsUpdateRequest,
  ChatMessageRequest,
  ChatMessageResponse,
  ChatMessage
} from './types'

export async function listChats(params: { cursor?: string; limit?: number; q?: string } = {}) {
  const qs = new URLSearchParams()
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.cursor) qs.set('cursor', params.cursor)
  if (params.q) qs.set('q', params.q)
  return api.get<PaginatedResponse<Chat>>(`/chats?${qs.toString()}`)
}

export async function createChat(name?: string | null, tags?: string[] | null) {
  const body: ChatCreateRequest = { name: name ?? null, tags: tags ?? null }
  return api.post<{ chat_id: string }>('/chats', body)
}

export async function listMessages(chat_id: string, params: { cursor?: string; limit?: number } = {}) {
  const qs = new URLSearchParams()
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.cursor) qs.set('cursor', params.cursor)
  return api.get<PaginatedResponse<ChatMessage>>(`/chats/${chat_id}/messages?${qs.toString()}`)
}

export async function sendMessage(chat_id: string, body: ChatMessageRequest) {
  return api.post<ChatMessageResponse>(`/chats/${chat_id}/messages`, body, { idempotent: true })
}

export async function* sendMessageStream(chat_id: string, body: { content: string; use_rag?: boolean }) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  // Add auth token if available
  const token = (window as any).__auth_tokens?.access_token || localStorage.getItem('access_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  
  const res = await fetch(`/api/chats/${chat_id}/messages`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ ...body, response_stream: true })
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)

  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('text/event-stream')) {
    for await (const ev of parseSSE(res.body!)) {
      if (ev.data) yield ev.data
    }
  } else {
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let pending = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      pending += decoder.decode(value, { stream: true })
      let idx
      while ((idx = pending.indexOf('\n')) !== -1) {
        const line = pending.slice(0, idx).trim()
        pending = pending.slice(idx + 1)
        if (line) yield line
      }
    }
    if (pending.trim()) yield pending.trim()
  }
}

export async function renameChat(chat_id: string, name: string) {
  const body: ChatUpdateRequest = { name }
  return api.patch<Chat>(`/chats/${chat_id}`, body)
}

export async function updateChatTags(chat_id: string, tags: string[]) {
  const body: ChatTagsUpdateRequest = { tags }
  return api.put<{ id: string; tags: string[] }>(`/chats/${chat_id}/tags`, body)
}

export async function deleteChat(chat_id: string) {
  return api.delete<{ id: string; deleted: boolean }>(`/chats/${chat_id}`)
}
