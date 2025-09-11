// === Auth ===
export type LoginResponse = {
  access_token: string;
  refresh_token: string;
  token_type?: string;
  expires_in?: number;
  user: {
    id: string;
    fio?: string;
    login: string;
    role?: string;
  };
};

export type User = LoginResponse["user"];

export type AuthTokens = {
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
};

// === Chats ===
export type Chat = {
  id: string;
  name?: string;
  owner_id?: string;
  created_at: string;
  updated_at?: string;
  last_message_at?: string | null;
};

export type ChatMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  created_at?: string | null;
};

export type ChatTurnRequest = {
  response_stream?: boolean; // default true
  use_rag?: boolean;         // default true
  rag_params?: {
    top_k?: number;
    min_score?: number;
  };
  messages?: ChatMessage[];
  temperature?: number;
  max_tokens?: number;
  idempotency_key?: string;
};

export type ChatTurnResponse = {
  chat_id: string;
  message_id: string;
  created_at: string;
  assistant_message: ChatMessage;
};

export type CursorPage<T> = {
  items: T[];
  next_cursor?: string | null;
};

// === RAG ===
export type RagDocument = {
  id: string;
  name?: string;
  status: "queued" | "processing" | "ready" | "error" | "archived";
  date_upload?: string;
  url_file?: string;
  url_canonical_file?: string;
  tags?: string[];
  progress?: number;
  created_at?: string;
  updated_at?: string;
};

export type RagUploadRequest = {
  url?: string;
  name?: string;
  tags?: string[];
};

export type RagSearchItem = {
  document_id: string;
  chunk_id: string;
  score: number;
  snippet: string;
};

// === Analyze ===
export type AnalyzeDocument = {
  id: string;
  status: "queued" | "processing" | "done" | "error" | "canceled";
  date_upload?: string;
  url_file?: string;
  url_canonical_file?: string;
  result?: any;
  error?: string;
  updated_at?: string;
};

export type AnalyzeResult = {
  id: string;
  status: string;
  progress?: number;
  result?: {
    summary?: string;
    entities?: { type: string; text: string }[];
    qa?: { q: string; a: string }[];
    metrics?: { pages?: number; chunks?: number; model?: string };
  };
  artifacts?: { canonical?: string; preview_pdf?: string };
};
