import { API_BASE } from '@/shared/config';

export function buildFileDownloadUrl(fileId: string): string {
  return `${API_BASE}/files/${encodeURIComponent(fileId)}/download`;
}

export function buildRagDocFileId(docId: string, kind: 'original' | 'canonical'): string {
  return `ragdoc_${docId}_${kind}`;
}

export function buildChatAttachmentFileId(attachmentId: string): string {
  return `chatatt_${attachmentId}`;
}
