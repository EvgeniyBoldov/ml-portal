/** Shared API types */
export interface Pagination {
  page?: number;
  size?: number;
  total?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor?: string | null;
  pagination?: Pagination;
}

export interface ApiResponse<T = any> {
  data?: T;
  error?: {
    code: string;
    message: string;
  };
  request_id?: string;
}

export interface Chat {
  id: string;
  name?: string | null;
  tags?: string[] | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_message_at?: string | null;
}

export interface ChatMessage {
  id: string;
  chat_id: string;
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  created_at?: string | null;
}

export interface ChatCreateRequest {
  name?: string | null;
  tags?: string[] | null;
}

export interface ChatUpdateRequest {
  name?: string | null;
}

export interface ChatTagsUpdateRequest {
  tags: string[];
}

export interface ChatMessageCreateRequest {
  content: string;
  use_rag?: boolean;
  response_stream?: boolean;
}

export interface ChatMessageResponse {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string | Record<string, any>;
  model?: string;
  tokens_in?: number;
  tokens_out?: number;
  meta?: Record<string, any>;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  name?: string;
  role?: string;
  created_at?: string;
  updated_at?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
  refresh_token?: string;
  expires_in?: number;
}

export interface AuthTokens {
  access_token: string;
  token_type: string;
  refresh_token?: string;
  expires_in?: number;
}

export interface AnalyzeDocument {
  id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
  error?: string;
  date_upload?: string;
  result?: any;
  url_canonical_file?: string;
}

export interface RagDocument {
  id: string;
  title: string;
  content: string;
  created_at: string;
  updated_at: string;
  name?: string;
  status?: string;
  progress?: number;
  date_upload?: string;
  tags?: string[];
  url_canonical_file?: string;
}
