import { apiFetch } from './base'
import { parseSSE } from '@shared/lib/sse'

export async function listChats(params: { cursor?: string; limit?: number; q?: string } = {}) {
  const qs = new URLSearchParams()
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.cursor) qs.set('cursor', params.cursor)
  if (params.q) qs.set('q', params.q)
  const res = await apiFetch(`/chats?${qs.toString()}`, { method: 'GET' })
  return res.json() as Promise<{ items: any[]; next_cursor?: string | null }>
}

export async function createChat(name?: string, tags?: string[]) {
  const body = { name, tags }
  const res = await apiFetch('/chats', { method: 'POST', body: JSON.stringify(body) })
  return res.json() as Promise<{ chat_id: string }>
}

export async function listMessages(chat_id: string, params: { cursor?: string; limit?: number } = {}) {
  const qs = new URLSearchParams()
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.cursor) qs.set('cursor', params.cursor)
  const res = await apiFetch(`/chats/${chat_id}/messages?${qs.toString()}`, { method: 'GET' })
  return res.json() as Promise<{ items: any[]; next_cursor?: string | null }>
}

export async function sendMessage(chat_id: string, body: { content: string; use_rag?: boolean; response_stream?: boolean }) {
  const res = await apiFetch(`/chats/${chat_id}/messages`, { method: 'POST', body: JSON.stringify(body), idempotencyKey: crypto.randomUUID() })
  return res.json()
}

export async function* sendMessageStream(chat_id: string, body: { content: string; use_rag?: boolean }) {
  const res = await apiFetch(`/chats/${chat_id}/messages`, {
    method: 'POST',
    body: JSON.stringify({ ...body, response_stream: true }),
    idempotencyKey: crypto.randomUUID()
  })
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('text/event-stream')) {
    for await (const ev of parseSSE(res.body!)) {
      if (ev.data) yield ev.data
    }
  } else {
    // Fallback: NDJSON or chunked text
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
  const res = await apiFetch(`/chats/${chat_id}`, { method: 'PATCH', body: JSON.stringify({ name }) })
  return res.json()
}

export async function updateChatTags(chat_id: string, tags: string[]) {
  const res = await apiFetch(`/chats/${chat_id}/tags`, { method: 'PUT', body: JSON.stringify({ tags }) })
  return res.json()
}

export async function deleteChat(chat_id: string) {
  await apiFetch(`/chats/${chat_id}`, { method: 'DELETE' })
}
