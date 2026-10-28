export type ChatRole = 'user' | 'assistant';

export interface ChatAttachmentRef {
  artifactId: string;
  fileName: string;
  downloadUrl?: string;
  contentType?: string;
  sizeBytes?: number;
  sourceLabel?: 'Gen' | 'RAG' | 'Templ';
}

export interface ChatRagSource {
  source_id?: string;
  source_name?: string;
  chunk_id?: string;
  text?: string;
  page?: number;
  score?: number;
  meta?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ChatMessageMeta {
  attachments?: ChatAttachmentRef[];
  ragSources?: ChatRagSource[];
  runtimeRunId?: string;
  deliveryError?: boolean;
}

export interface ChatTimelineMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  isOptimistic?: boolean;
  outcome?: 'cancelled' | 'interrupted' | 'failed' | 'partial';
  errorCode?: string;
  meta?: ChatMessageMeta;
}

export interface ChatHistory {
  items: ChatTimelineMessage[];
  loading: boolean;
  loaded?: boolean;
  error?: string;
  olderCursor?: string;
}

export interface ChatRuntimeProgress {
  id: string;
  runId: string;
  stage: 'preparing' | 'planning' | 'executing' | 'synthesizing' | 'finalizing';
  action: string;
  description: string;
  outcome?: string;
  createdAt: string;
  // Reserved for future safe runtime projections. These fields must only be
  // populated from the public chat SSE contract, never from a raw trace.
  title?: string;
  objective?: string;
  summary?: string;
}

export type ChatRuntimeProgressSnapshot = Omit<ChatRuntimeProgress, 'id' | 'createdAt' | 'outcome'> & {
  outcome?: string | null;
};

export interface ActiveChatRun {
  userMessageId: string;
  assistantMessageId: string;
  runId?: string;
  progress: ChatRuntimeProgress[];
  status: 'running' | 'waiting_confirmation' | 'waiting_input';
}

export type ChatLifecycleStatus =
  | 'running'
  | 'waiting_input'
  | 'waiting_confirmation'
  | 'completed'
  | 'failed'
  | 'cancelled';
