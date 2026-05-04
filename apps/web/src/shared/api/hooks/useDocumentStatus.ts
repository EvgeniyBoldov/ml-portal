/**
 * Shared hook: fetch document status graph and transform to DocStatus.
 * Used by collections and (temporarily) legacy RAG StatusModal.
 */
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '@shared/api/http';
import type { StatusGraph, DocStatus } from '@shared/api/types/documentStatus';
import { adaptStatusGraphToDocStatus } from '@shared/lib/documentStatusAdapter';

export function useDocumentStatus(
  docId: string | undefined,
  statusGraphUrl?: string,
) {
  return useQuery<StatusGraph, Error, DocStatus>({
    queryKey: statusGraphUrl
      ? ['collections', 'doc-status', docId]
      : docId
        ? ['document-status', docId]
        : ['document-status', 'undefined'],
    queryFn: async () => {
      if (!docId) throw new Error('Document ID is required');
      if (statusGraphUrl) {
        return apiRequest<StatusGraph>(statusGraphUrl);
      }
      return apiRequest<StatusGraph>(`/rag/${docId}/status-graph`);
    },
    select: (data: StatusGraph) => adaptStatusGraphToDocStatus(data),
    enabled: !!docId,
    staleTime: 0,
  });
}
