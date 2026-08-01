export type ChatRole = 'user' | 'assistant';

export interface ChatAttachmentRef {
  artifactId: string;
  fileName: string;
  contentType?: string;
  sizeBytes?: number;
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
}

export interface ChatTimelineMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  isOptimistic?: boolean;
  meta?: ChatMessageMeta;
}

export interface ChatRuntimeProgress {
  id: string;
  runId: string;
  phase: string;
  kind: string;
  description: string;
  status?: string;
  createdAt: string;
}

export interface ActiveChatRun {
  userMessageId: string;
  assistantMessageId: string;
  runId?: string;
  progress: ChatRuntimeProgress[];
  status: 'running' | 'waiting_confirmation' | 'waiting_input';
}
