import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { applyRagEvents } from '../app/providers/applyRagEvents';
import type { SSEMessage } from '@shared/lib/sse';
import { qk } from '@shared/api/keys';

describe('applyRagEvents', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  });

  describe('rag.status events', () => {
    it('should update detail cache with status event', () => {
      const docId = 'test-doc-123';
      
      // Set initial cache data
      queryClient.setQueryData(qk.rag.detail(docId), {
        pipeline: {
          extract: { status: 'pending' },
          normalize: { status: 'pending' },
          chunk: { status: 'pending' },
        },
        embeddings: {},
        indexes: {},
      });

      const messages: SSEMessage[] = [
        {
          type: 'rag.status',
          data: {
            doc_id: docId,
            stage: 'extract',
            status: 'processing',
            metrics: { word_count: 100 },
          },
          timestamp: Date.now(),
          seq: 1,
        },
      ];

      applyRagEvents(messages, queryClient);

      const cached = queryClient.getQueryData(qk.rag.detail(docId)) as any;
      expect(cached.pipeline.extract.status).toBe('processing');
    });

    it('should update list cache aggregate status', () => {
      const docId = 'test-doc-456';
      
      // Set initial list cache
      queryClient.setQueryData(qk.rag.list({ page: 1, size: 20 }), {
        items: [
          { id: docId, title: 'Test Doc', status: 'pending' },
        ],
        total: 1,
        page: 1,
        size: 20,
      });

      const messages: SSEMessage[] = [
        {
          type: 'rag.status',
          data: {
            doc_id: docId,
            stage: 'extract',
            status: 'completed',
            aggregate_status: 'processing',
          },
          timestamp: Date.now(),
          seq: 1,
        },
      ];

      applyRagEvents(messages, queryClient);

      const cached = queryClient.getQueryData(qk.rag.list({ page: 1, size: 20 })) as any;
      expect(cached.items[0].status).toBe('processing');
    });

    it('should ignore events without doc_id', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      
      const messages: SSEMessage[] = [
        {
          type: 'rag.status',
          data: { stage: 'extract', status: 'processing' },
          timestamp: Date.now(),
          seq: 1,
        },
      ];

      applyRagEvents(messages, queryClient);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('missing doc_id'),
        expect.anything()
      );
      
      consoleSpy.mockRestore();
    });
  });

  describe('rag.embed.progress events', () => {
    it('should update embed progress in detail cache', () => {
      const docId = 'test-doc-789';
      
      queryClient.setQueryData(qk.rag.detail(docId), {
        pipeline: {},
        embeddings: {
          'text-embedding-ada-002': { status: 'processing' },
        },
        indexes: {},
      });

      const messages: SSEMessage[] = [
        {
          type: 'rag.embed.progress',
          data: {
            doc_id: docId,
            model_alias: 'text-embedding-ada-002',
            done: 50,
            total: 100,
          },
          timestamp: Date.now(),
          seq: 2,
        },
      ];

      applyRagEvents(messages, queryClient);

      const cached = queryClient.getQueryData(qk.rag.detail(docId)) as any;
      expect(cached.embeddings['text-embedding-ada-002'].progress).toEqual({
        done: 50,
        total: 100,
      });
    });
  });

  describe('rag.deleted events', () => {
    it('should remove document from list cache', () => {
      const docId = 'test-doc-to-delete';
      
      queryClient.setQueryData(qk.rag.list({ page: 1, size: 20 }), {
        items: [
          { id: docId, title: 'Doc to Delete' },
          { id: 'other-doc', title: 'Other Doc' },
        ],
        total: 2,
        page: 1,
        size: 20,
      });

      const messages: SSEMessage[] = [
        {
          type: 'rag.deleted',
          data: { doc_id: docId },
          timestamp: Date.now(),
          seq: 3,
        },
      ];

      applyRagEvents(messages, queryClient);

      const cached = queryClient.getQueryData(qk.rag.list({ page: 1, size: 20 })) as any;
      expect(cached.items).toHaveLength(1);
      expect(cached.items[0].id).toBe('other-doc');
    });

    it('should invalidate detail cache for deleted document', () => {
      const docId = 'test-doc-deleted';
      
      queryClient.setQueryData(qk.rag.detail(docId), {
        pipeline: {},
        embeddings: {},
        indexes: {},
      });

      const messages: SSEMessage[] = [
        {
          type: 'rag.deleted',
          data: { doc_id: docId },
          timestamp: Date.now(),
          seq: 4,
        },
      ];

      applyRagEvents(messages, queryClient);

      const cached = queryClient.getQueryData(qk.rag.detail(docId));
      expect(cached).toBeUndefined();
    });
  });

  describe('rag.tags.updated events', () => {
    it('should update tags in list cache', () => {
      const docId = 'test-doc-tags';
      
      queryClient.setQueryData(qk.rag.list({ page: 1, size: 20 }), {
        items: [
          { id: docId, title: 'Doc', tags: ['old'] },
        ],
        total: 1,
        page: 1,
        size: 20,
      });

      const messages: SSEMessage[] = [
        {
          type: 'rag.tags.updated',
          data: {
            doc_id: docId,
            tags: ['new', 'updated'],
          },
          timestamp: Date.now(),
          seq: 5,
        },
      ];

      applyRagEvents(messages, queryClient);

      const cached = queryClient.getQueryData(qk.rag.list({ page: 1, size: 20 })) as any;
      expect(cached.items[0].tags).toEqual(['new', 'updated']);
    });
  });

  describe('error handling', () => {
    it('should continue processing after error in one event', () => {
      const docId = 'test-doc-error';
      
      queryClient.setQueryData(qk.rag.list({ page: 1, size: 20 }), {
        items: [{ id: docId, title: 'Doc', tags: [] }],
        total: 1,
        page: 1,
        size: 20,
      });

      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      const messages: SSEMessage[] = [
        // Invalid event that will cause error
        {
          type: 'rag.status',
          data: null as any, // Will cause error
          timestamp: Date.now(),
          seq: 1,
        },
        // Valid event that should still be processed
        {
          type: 'rag.tags.updated',
          data: {
            doc_id: docId,
            tags: ['processed'],
          },
          timestamp: Date.now(),
          seq: 2,
        },
      ];

      applyRagEvents(messages, queryClient);

      const cached = queryClient.getQueryData(qk.rag.list({ page: 1, size: 20 })) as any;
      expect(cached.items[0].tags).toEqual(['processed']);
      
      consoleSpy.mockRestore();
    });
  });
});
