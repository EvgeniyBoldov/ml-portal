import { API_BASE } from '@/shared/config';

export function buildFileDownloadUrl(fileId: string): string {
  return `${API_BASE}/files/${encodeURIComponent(fileId)}/download`;
}

export function buildArtifactDownloadUrl(artifactId: string): string {
  return `${API_BASE}/files/${encodeURIComponent(artifactId)}/download`;
}

export function buildRagDocFileId(docId: string, kind: 'original' | 'canonical'): string {
  return `ragdoc_${docId}_${kind}`;
}
