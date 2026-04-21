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
  has_more?: boolean;
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
  meta?: Record<string, unknown>;
}

export interface ChatAttachment {
  id: string;
  file_id?: string;
  file_name: string;
  file_ext: string;
  content_type?: string | null;
  size_bytes: number;
  status: string;
}

export interface ChatUploadPolicy {
  max_bytes: number;
  allowed_extensions: string[];
  allowed_content_types_by_extension?: Record<string, string[]>;
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
  attachment_ids?: string[];
  confirmation_tokens?: string[];
}

export interface ChatMessageResponse {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string | Record<string, unknown>;
  model?: string;
  tokens_in?: number;
  tokens_out?: number;
  meta?: Record<string, unknown>;
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
