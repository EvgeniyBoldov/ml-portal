// apps/web/src/shared/api/hooks/useRagDocuments.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getRagDocuments,
  uploadRagDocument,
  deleteRagDocument,
  resetRagDocument,
  cancelRagDocument,
} from '@shared/api/rag';
import type { RagDocumentsResponse, StatusGraph } from '@shared/api/types/rag';
import type { DocStatus } from '@/domains/rag/types';
import { qk } from '@shared/api/keys';
import { adaptStatusGraphToDocStatus } from '@shared/api/rag';

export interface UseRagDocumentsParams {
  page?: number;
  size?: number;
  status?: string;
  search?: string;
  scope?: 'local' | 'global';
}

export function useRagDocuments(params: UseRagDocumentsParams = {}) {
  const { page = 1, size = 100, status, search, scope } = params;

  return useQuery<RagDocumentsResponse>({
    queryKey: qk.rag.list({ page, size, status, q: search }),
    queryFn: () => getRagDocuments(page, size, status, search),
    staleTime: 60000, // 1 minute
    keepPreviousData: true,
  });
}

export function useRagDocument(id: string | undefined) {
  return useQuery<StatusGraph, Error, DocStatus>({
    queryKey: id ? qk.rag.detail(id) : ['rag', 'doc', 'undefined'],
    queryFn: async () => {
      if (!id) throw new Error('Document ID is required');
      const { getRagDocumentRaw } = await import('@shared/api/rag');
      return getRagDocumentRaw(id);
    },
    select: (data: StatusGraph) => adaptStatusGraphToDocStatus(data),
    enabled: !!id,
    staleTime: 30000, // 30 seconds for detail
  });
}

export function useUploadRagDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      file,
      filename,
      tags,
    }: {
      file: File;
      filename: string;
      tags?: string[];
    }) => uploadRagDocument(file, filename, tags || []),
    onSuccess: () => {
      // Invalidate list to fetch new document
      queryClient.invalidateQueries({ queryKey: ['rag', 'list'] });
    },
  });
}

export function useDeleteRagDocument() {
  const queryClient = useQueryClient();

  return useMutation<{ id: string; deleted: boolean }, Error, string>({
    mutationFn: deleteRagDocument,
    onSuccess: (_response: { id: string; deleted: boolean }, docId: string) => {
      // Update list - remove deleted document
      queryClient.setQueriesData<RagDocumentsResponse>(
        { queryKey: ['rag', 'list'] },
        (old?: RagDocumentsResponse) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.filter(doc => doc.id !== docId),
            pagination: {
              ...old.pagination,
              total: old.pagination.total - 1,
            },
          };
        }
      );

      // Remove document query
      queryClient.removeQueries({ queryKey: ['rag', 'detail', docId] });
    },
  });
}


/**
 * Hook for resetting RAG document processing
 * Does not invalidate queries - relies on SSE events for updates
 */
export function useResetRagDocument() {
  return useMutation({
    mutationFn: resetRagDocument,
    // No onSuccess - updates come from SSE
  });
}

/**
 * Hook for canceling RAG document processing
 * Does not invalidate queries - relies on SSE events for updates
 */
export function useCancelRagDocument() {
  return useMutation({
    mutationFn: cancelRagDocument,
    // No onSuccess - updates come from SSE
  });
}

/**
 * Hook for updating RAG document tags
 * Optimistically updates cache, then waits for SSE confirmation
 */
export function useUpdateRagTags() {
  const queryClient = useQueryClient();

  return useMutation<
    { id: string; tags: string[] },
    Error,
    { docId: string; tags: string[] }
  >({
    mutationFn: ({ docId, tags }) =>
      import('@shared/api/rag').then(m => m.updateRagDocumentTags(docId, tags)),
    onMutate: async ({ docId, tags }) => {
      // Optimistic update
      queryClient.setQueriesData<RagDocumentsResponse>(
        { queryKey: ['rag', 'list'] },
        old => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map(item =>
              item.id === docId ? { ...item, tags } : item
            ),
          };
        }
      );
    },
    // SSE will send confirmation, no need to invalidate
  });
}

/**
 * Hook for updating RAG document scope
 * Invalidates list after success
 */
export function useUpdateRagScope() {
  const queryClient = useQueryClient();

  return useMutation<
    { id: string; scope: string; message: string },
    Error,
    { docId: string; scope: 'local' | 'global' }
  >({
    mutationFn: ({ docId, scope }) =>
      import('@shared/api/rag').then(m => m.updateRagDocumentScope(docId, scope)),
    onSuccess: (_data, { docId, scope }) => {
      // Update cache immediately
      queryClient.setQueriesData<RagDocumentsResponse>(
        { queryKey: ['rag', 'list'] },
        old => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map(item =>
              item.id === docId ? { ...item, scope } : item
            ),
          };
        }
      );
    },
  });
}
