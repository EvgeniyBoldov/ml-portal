// Simple in-app fetch mock. Works when VITE_USE_MOCKS=true
// Emulates a subset of backend endpoints used by the app, including SSE for chat and simple queues.
type Opts = RequestInit & { idempotencyKey?: string };
const encoder = new TextEncoder();

type User = {
  id: string;
  login: string;
  fio?: string;
  role?: string;
  password?: string;
};
type Message = { role: 'user' | 'assistant'; content: string };
type Chat = { id: string; name: string; messages: Message[] };
type RagDoc = {
  id: string;
  name: string;
  status: 'uploaded' | 'processing' | 'ready' | 'error';
  tags: string[];
  created_at: string;
};
type AnalyzeTask = {
  id: string;
  source?: string;
  status: 'queued' | 'processing' | 'done' | 'error';
  result?: string;
  created_at: string;
};

const db = {
  users: [
    {
      id: 'u1',
      login: 'admin',
      password: 'admin',
      fio: 'Администратор',
      role: 'admin',
    } as User,
  ],
  chats: new Map<string, Chat>(),
  tokens: new Map<string, string>(), // access_token -> userId
  rag: [] as RagDoc[],
  analyze: [] as AnalyzeTask[],
};

function jsonResponse(body: any, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}
function noContent() {
  return new Response(null, { status: 204 });
}
function unauthorized() {
  return new Response('unauthorized', { status: 401 });
}
function notFound() {
  return new Response('not found', { status: 404 });
}
function badRequest(msg = 'bad request') {
  return new Response(msg, { status: 400 });
}

function parseUrl(url: string) {
  // Works with relative like "/api/..." and absolute like "http://x/api/..."
  try {
    const u = new URL(url, window.location.origin);
    return u;
  } catch {
    return new URL(window.location.origin + url.replace(/^\//, ''));
  }
}

async function readJson(body?: BodyInit | null) {
  if (!body) return null;
  if (typeof body === 'string') {
    try {
      return JSON.parse(body);
    } catch {
      return null;
    }
  }
  if (body instanceof FormData) {
    return body;
  }
  // Other types: ignore for simplicity
  return null;
}

function requireAuth(headers: Headers): User | null {
  const auth = headers.get('Authorization') || '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : null;
  if (!token) return null;
  const uid = db.tokens.get(token || '');
  const user = db.users.find(u => u.id === uid);
  return user || null;
}

function sseStream(lines: string[], delayMs = 40) {
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const part of lines) {
        const chunk = `data: ${part}\n\n`;
        controller.enqueue(encoder.encode(chunk));
        await new Promise(r => setTimeout(r, delayMs));
      }
      controller.close();
    },
  });
}

function paginate<T extends { id?: string }>(
  arr: T[],
  cursor?: string | null,
  limit = 20
) {
  let start = 0;
  if (cursor) {
    const idx = (arr as any[]).findIndex(
      (it: any) => (it.id || it.chat_id) === cursor
    );
    start = idx >= 0 ? idx + 1 : 0;
  }
  const items = (arr as any[]).slice(start, start + limit);
  const next_cursor =
    start + limit < (arr as any[]).length
      ? ((arr as any[])[start + limit - 1] as any).id
      : null;
  return { items, next_cursor };
}

// Seed some RAG docs on first GET
function seedRag() {
  if (db.rag.length > 0) return;
  const now = new Date().toISOString();
  db.rag.push(
    {
      id: 'doc1',
      name: 'Guide.pdf',
      status: 'ready',
      tags: ['guide'],
      created_at: now,
    },
    {
      id: 'doc2',
      name: 'Spec.md',
      status: 'processing',
      tags: ['spec'],
      created_at: now,
    },
    {
      id: 'doc3',
      name: 'Manual.txt',
      status: 'uploaded',
      tags: ['manual'],
      created_at: now,
    }
  );
}

// Simple background progression helper (uploaded -> processing -> ready)
function progressRag(doc: RagDoc) {
  setTimeout(() => {
    doc.status = 'processing';
  }, 600);
  setTimeout(() => {
    doc.status = 'ready';
  }, 1400);
}

// Analyze progression (queued -> processing -> done with text result)
function progressAnalyze(task: AnalyzeTask) {
  setTimeout(() => {
    task.status = 'processing';
  }, 500);
  setTimeout(() => {
    task.status = 'done';
    task.result = `Результат анализа: «${task.source || 'file'}» обработан.`;
  }, 1500);
}

export async function mockFetch(url: string, opts: Opts = {}) {
  const u = parseUrl(url);
  const path = u.pathname;
  const method = (opts.method || 'GET').toUpperCase();
  const body = await readJson(opts.body || null);

  // AUTH
  if (path === '/api/auth/login' && method === 'POST') {
    const { login, password } = (body as any) || {};
    const user = db.users.find(
      u => u.login === login && u.password === password
    );
    if (!user) return badRequest('invalid credentials');
    const access = crypto.randomUUID();
    db.tokens.set(access, user.id);
    return jsonResponse({
      access_token: access,
      refresh_token: 'refresh_' + user.id,
      expires_in: 3600,
    });
  }
  if (path === '/api/auth/refresh' && method === 'POST') {
    // accept any refresh token that starts with "refresh_"
    const { refresh_token } = (body as any) || {};
    if (!refresh_token || !String(refresh_token).startsWith('refresh_'))
      return unauthorized();
    const uid = String(refresh_token).slice('refresh_'.length);
    const user = db.users.find(u => u.id === uid);
    if (!user) return unauthorized();
    const access = crypto.randomUUID();
    db.tokens.set(access, user.id);
    return jsonResponse({ access_token: access, expires_in: 3600 });
  }
  if (path === '/api/auth/me' && method === 'GET') {
    const user = requireAuth(new Headers(opts.headers || {}));
    if (!user) return unauthorized();
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { password, ...safe } = user as any;
    return jsonResponse(safe);
  }
  if (path === '/api/auth/logout' && method === 'POST') {
    const auth = new Headers(opts.headers || {}).get('Authorization') || '';
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
    db.tokens.delete(token);
    return noContent();
  }

  // CHATS
  if (path === '/api/chats' && method === 'POST') {
    const id = crypto.randomUUID();
    const name = (body && (body as any).name) || 'New chat';
    db.chats.set(id, { id, name, messages: [] });
    return jsonResponse({ chat_id: id });
  }
  if (path === '/api/chats' && method === 'GET') {
    const list = Array.from(db.chats.values()).map(c => ({
      id: c.id,
      name: c.name,
    }));
    return jsonResponse({ items: list, next_cursor: null });
  }
  const chatIdMatch = path.match(/^\/api\/chats\/([^/]+)(?:\/(messages))?$/);
  if (chatIdMatch) {
    const chatId = chatIdMatch[1];
    const sub = chatIdMatch[2]; // 'messages' or undefined
    const chat = db.chats.get(chatId || '');
    if (!chat && method !== 'PATCH' && method !== 'DELETE') return notFound();

    if (!sub && method === 'PATCH') {
      const name = (body as any)?.name || 'Untitled';
      const c = db.chats.get(chatId || '');
      if (!c) return notFound();
      c.name = name;
      return jsonResponse({ ok: true });
    }
    if (!sub && method === 'DELETE') {
      db.chats.delete(chatId || '');
      return noContent();
    }

    if (sub === 'messages' && method === 'GET') {
      const msgs = chat ? chat.messages : [];
      return jsonResponse({ items: msgs, next_cursor: null });
    }

    if (sub === 'messages' && method === 'POST') {
      const payload = (body as any) || {};
      const userMsg = payload.messages?.[0]?.content || '';
      if (chat) chat.messages.push({ role: 'user', content: userMsg });

      const canned = `Привет! Это моковый ответ на: "${userMsg}".\nМоки включены, бэкенд не требуется.`;

      if (payload.response_stream) {
        const tokens = Array.from(canned);
        const stream = sseStream(tokens, 18);
        // also push the final assistant message into history (joined)
        const full = tokens.join('');
        if (chat) chat.messages.push({ role: 'assistant', content: full });
        const headers = new Headers({
          'Content-Type': 'text/event-stream; charset=utf-8',
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        });
        return new Response(stream, { status: 200, headers });
      } else {
        if (chat) chat.messages.push({ role: 'assistant', content: canned });
        return jsonResponse({
          message: { role: 'assistant', content: canned },
        });
      }
    }
  }

  // RAG
  if (path === '/api/rag' && method === 'GET') {
    seedRag();
    const q = u.searchParams.get('q')?.toLowerCase() || '';
    const status = u.searchParams.get('status') || '';
    const cursor = u.searchParams.get('cursor') || undefined;
    let data = db.rag.slice();
    if (q) data = data.filter(d => d.name.toLowerCase().includes(q));
    if (status) data = data.filter(d => d.status === status);
    const { items, next_cursor } = paginate(data, cursor, 20);
    return jsonResponse({ items, next_cursor });
  }
  if (path === '/api/rag/upload' && method === 'POST') {
    const name =
      body instanceof FormData
        ? (body.get('name') as string) ||
          (body.get('file') as File)?.name ||
          'document'
        : 'document';
    const doc: RagDoc = {
      id: crypto.randomUUID(),
      name,
      status: 'uploaded',
      tags: [],
      created_at: new Date().toISOString(),
    };
    db.rag.unshift(doc);
    progressRag(doc);
    return jsonResponse({ id: doc.id, status: doc.status });
  }
  if (path === '/api/rag/search' && method === 'POST') {
    const q = (body as any)?.text || '';
    return jsonResponse({
      items: [
        {
          document_id: db.rag[0]?.id || 'doc1',
          chunk_id: '1',
          score: 0.92,
          snippet: `Найдено по запросу "${q}" — фрагмент №1`,
        },
        {
          document_id: db.rag[0]?.id || 'doc1',
          chunk_id: '2',
          score: 0.87,
          snippet: `Найдено по запросу "${q}" — фрагмент №2`,
        },
      ],
    });
  }

  // ANALYZE
  if (path === '/api/analyze' && method === 'GET') {
    const items = db.analyze
      .slice()
      .sort((a, b) => (b.created_at > a.created_at ? 1 : -1));
    return jsonResponse({ items });
  }
  if (path === '/api/analyze' && method === 'POST') {
    let source = '';
    if (body instanceof FormData) {
      source = (body.get('file') as File)?.name || 'file';
    } else {
      source = (body as any)?.url || '';
    }
    if (!source) return badRequest('source required');
    const task: AnalyzeTask = {
      id: crypto.randomUUID(),
      source,
      status: 'queued',
      created_at: new Date().toISOString(),
    };
    db.analyze.unshift(task);
    progressAnalyze(task);
    return jsonResponse({ id: task.id, status: task.status });
  }
  const analyzeMatch = path.match(/^\/api\/analyze\/([^/]+)$/);
  if (analyzeMatch && method === 'GET') {
    const id = analyzeMatch[1];
    const t = db.analyze.find(x => x.id === id);
    if (!t) return notFound();
    return jsonResponse(t);
  }

  // Unknown: pass-through to real fetch (allows gradual mocking)
  return fetch(url, opts);
}
