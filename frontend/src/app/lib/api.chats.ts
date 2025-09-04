// src/lib/api.chats.ts
const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function auth(token?: string): HeadersInit {
  const h: HeadersInit = {};
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

export type ChatSummary = { id: number; title: string };

export type ChatMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

export type ChatSendRequest = {
  messages: ChatMessage[];
  use_rag: boolean;
  temperature?: number;
  top_k?: number;
};

// ответ при отправке в НОВЫЙ чат (без id):
export type ChatCreatedResponse = {
  chat: ChatSummary;
  assistant: ChatMessage; // role: "assistant"
  references?: Array<{ id: string; score?: number }>;
};

// ответ при отправке в СУЩЕСТВУЮЩИЙ чат:
export type ChatSendResponse = {
  assistant: ChatMessage; // role: "assistant"
  references?: Array<{ id: string; score?: number }>;
};

// ---------- список чатов ----------
export async function listChats(token: string): Promise<ChatSummary[]> {
  const r = await fetch(`${BASE}/chats`, { headers: auth(token) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ---------- (не используется с новой логикой) удалить чат, если понадобится ----------
export async function deleteChat(token: string, chatId: number): Promise<void> {
  const r = await fetch(`${BASE}/chats/${chatId}`, {
    method: "DELETE",
    headers: auth(token),
  });
  if (!r.ok && r.status !== 204) throw new Error(await r.text());
}

// ---------- отправка ПЕРВОГО сообщения (без id) ----------
export async function sendNewChat(
  token: string,
  payload: ChatSendRequest
): Promise<ChatCreatedResponse> {
  // основной путь: /chats/send
  let r = await fetch(`${BASE}/chats/send`, {
    method: "POST",
    headers: { ...auth(token), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  // fallback: если у тебя бек использует другой путь
  if (r.status === 404 || r.status === 405) {
    // иногда делают без /send — просто POST /chats с телом диалога
    r = await fetch(`${BASE}/chats`, {
      method: "POST",
      headers: { ...auth(token), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  // если FastAPI требует строгое тело — убедись, что messages/use_rag пришли
  if (r.status === 422) {
    throw new Error(await r.text()); // вернём подробную ошибку pydantic
  }
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ---------- отправка в СУЩЕСТВУЮЩИЙ чат (non-stream) ----------
export async function sendToChat(
  token: string,
  chatId: number,
  payload: ChatSendRequest
): Promise<ChatSendResponse> {
  const r = await fetch(`${BASE}/chats/${chatId}/send`, {
    method: "POST",
    headers: { ...auth(token), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ---------- отправка в СУЩЕСТВУЮЩИЙ чат (stream) ----------
export function sendToChatStream(
  token: string,
  chatId: number,
  payload: ChatSendRequest
): {
  textStream: AsyncGenerator<string, void, unknown>;
  done: Promise<ChatSendResponse>;
} {
  async function* readerToGenerator(res: Response) {
    const dec = new TextDecoder();
    const reader = res.body?.getReader();
    if (!reader) return;
    let buf = "";
    const isSSE = (res.headers.get("content-type") || "").includes("text/event-stream");

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });

      if (isSSE) {
        let idx;
        while ((idx = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, idx).trim();
          buf = buf.slice(idx + 1);
          if (line.startsWith("data:")) {
            const data = line.slice(5).trim();
            if (data && data !== "[DONE]") yield data;
          }
        }
      } else {
        // сырые чанки
        yield buf;
        buf = "";
      }
    }
    if (!isSSE && buf) yield buf;
  }

  const start = (async () => {
    // пробуем явный stream-эндпоинт
    let res = await fetch(`${BASE}/chats/${chatId}/send/stream`, {
      method: "POST",
      headers: { ...auth(token), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (res.status === 404 || res.status === 405) {
      // обычный эндпоинт как поток
      res = await fetch(`${BASE}/chats/${chatId}/send`, {
        method: "POST",
        headers: { ...auth(token), "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }

    if (!res.ok) throw new Error(await res.text());

    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const j = await res.json();
      const text = j?.assistant?.content ?? "";
      async function* one() { if (text) yield text; }
      return { gen: one(), done: j as ChatSendResponse };
    }

    return { gen: readerToGenerator(res), done: { assistant: { role: "assistant", content: "" } } as ChatSendResponse };
  })();

  return {
    textStream: (async function* () {
      const { gen } = await start;
      yield* gen;
    })(),
    done: (async () => {
      const { done } = await start;
      return done;
    })(),
  };
}
