import type { ChatMessage } from '@/shared/api/types';
import type {
  ChatAttachmentRef,
  ChatMessageMeta,
  ChatRagSource,
  ChatTimelineMessage,
} from './types';

export function toAttachments(value: unknown): ChatAttachmentRef[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap(item => {
    if (!item || typeof item !== 'object') return [];
    const raw = item as Record<string, unknown>;
    const artifactId =
      typeof raw.artifact_id === 'string' ? raw.artifact_id : '';
    const fileName = typeof raw.file_name === 'string' ? raw.file_name : '';
    if (!artifactId || !fileName) return [];
    return [
      {
        artifactId,
        fileName,
        downloadUrl:
          typeof raw.download_url === 'string' ? raw.download_url : undefined,
        contentType:
          typeof raw.content_type === 'string' ? raw.content_type : undefined,
        sizeBytes:
          typeof raw.size_bytes === 'number' ? raw.size_bytes : undefined,
      },
    ];
  });
}

export function toRagSources(value: unknown): ChatRagSource[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is ChatRagSource => !!item && typeof item === 'object'
      )
    : [];
}

function toMessageMeta(value: unknown): ChatMessageMeta | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const raw = value as Record<string, unknown>;
  const meta: ChatMessageMeta = {
    attachments: toAttachments(raw.attachments),
    ragSources: toRagSources(raw.rag_sources),
    runtimeRunId:
      typeof raw.runtime_run_id === 'string' ? raw.runtime_run_id : undefined,
  };
  return meta.attachments?.length ||
    meta.ragSources?.length ||
    meta.runtimeRunId
    ? meta
    : undefined;
}

export function toRenderableMessage(
  message: ChatMessage
): ChatTimelineMessage | null {
  if (message.role !== 'user' && message.role !== 'assistant') return null;
  const status = message.meta?.runtime_status;
  return {
    id: message.id,
    role: message.role,
    content:
      typeof message.content === 'string'
        ? message.content
        : String(message.content ?? ''),
    createdAt: message.created_at ?? new Date().toISOString(),
    outcome: status === 'cancelled' || status === 'failed' ? status : undefined,
    meta: toMessageMeta(message.meta),
  };
}
