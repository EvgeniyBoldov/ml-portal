// apps/web/src/app/providers/applyRagEvents.ts
import { QueryClient } from '@tanstack/react-query';
import {
  StatusGraph,
  RagEvent,
  RagDocument,
  EmbeddingProgress,
  RagDocumentsResponse,
} from '@shared/api/types/rag';
import type { SSEMessage } from '@shared/lib/sse';
import { calculateAggregateStatus } from '@shared/lib/ragStatusAggregator';
import { qk } from '@shared/api/keys';

/**
 * Apply SSE events to TanStack Query cache
 * Idempotent: ignore events with seq <= last processed seq for each document
 */
export function applyRagEvents(
  messages: SSEMessage[],
  queryClient: QueryClient
): void {
  for (const msg of messages) {
    try {
      // Transform SSEMessage to RagEvent format
      const event = transformMessageToRagEvent(msg);
      if (!event) {
        continue;
      }

      switch (event.type) {
        case 'rag.status':
          applyStatusEvent(event, queryClient);
          break;

        case 'rag.embed.progress':
          applyEmbedProgressEvent(event, queryClient);
          break;

        case 'rag.tags.updated':
          applyTagsUpdatedEvent(event, queryClient);
          break;

        case 'rag.deleted':
          applyDeletedEvent(event, queryClient);
          break;

        default:
          console.warn('Unknown SSE event type:', event.type);
      }
    } catch (error) {
      console.error(`Error applying SSE event ${msg.type}:`, error);
    }
  }
}

function transformMessageToRagEvent(msg: SSEMessage): RagEvent | null {
  const data = msg.data;

  // Extract doc_id from data or metadata
  const doc_id = data.doc_id || data.document_id || data.id;
  if (!doc_id) {
    console.warn('SSE message missing doc_id:', msg);
    return null;
  }

  const base = {
    doc_id,
    timestamp:
      typeof msg.timestamp === 'number'
        ? new Date(msg.timestamp).toISOString()
        : (data.timestamp || msg.timestamp),
    seq: msg.seq || 0,
  };

  switch (msg.type) {
    case 'rag.status':
      // Backend sends: {event_type, document_id, stage, status, error, metrics, timestamp}
      // We need to transform this to invalidate/refetch the document status
      return {
        ...base,
        type: 'rag.status',
        data: {
          // Stage-level status from backend (e.g., "extract", "chunk", "embed.model-name", "index.model-name")
          stage: data.stage,
          // Status of the stage (e.g., "processing", "completed", "failed")
          stageStatus: data.status,
          // Aggregate status (if provided by backend, otherwise we'll refetch)
          status: data.agg_status || data.new_status,
          details: data.agg_details || data.agg_details_json || data.details,
          error: data.error,
          metrics: data.metrics,
          // Event type from backend
          eventType: data.event_type,
        },
      };

    case 'rag.embed.progress':
      return {
        ...base,
        type: 'rag.embed.progress',
        data: {
          model: data.model || data.model_alias,
          version: data.version,
          progress:
            data.progress ||
            (data.done_count && data.total_count
              ? data.done_count / data.total_count
              : 0),
          status: data.status,
          metrics: data.metrics,
          error: data.error || data.last_error,
        },
      };

    case 'rag.tags.updated':
      return {
        ...base,
        type: 'rag.tags.updated',
        data: { tags: data.tags },
      };

    case 'rag.deleted':
      return {
        ...base,
        type: 'rag.deleted',
        data: {},
      };

    default:
      return null;
  }
}

type StatusGraphCache = StatusGraph & {
  __last_seq?: number;
};

type RagListCache = {
  items: RagDocument[];
  pagination?: RagDocumentsResponse['pagination'];
  total?: number;
};

const getLastSequence = (graph?: StatusGraph): number => {
  if (!graph) {
    return 0;
  }

  if ('__last_seq' in graph) {
    const candidate = (graph as StatusGraphCache).__last_seq;
    return typeof candidate === 'number' ? candidate : 0;
  }

  return 0;
};

function applyStatusEvent(
  event: RagEvent & { type: 'rag.status' },
  queryClient: QueryClient
): void {
  const { doc_id } = event;
  const { stage, stageStatus, eventType } = event.data;


  // For stage-level updates, we invalidate the detail query to refetch fresh data
  // This ensures the StatusGraph is always in sync with backend
  if (stage) {
    // Invalidate detail query to get fresh StatusGraph from backend
    queryClient.invalidateQueries({ 
      queryKey: qk.rag.detail(doc_id),
      exact: true 
    });
    
    // Also invalidate list to update aggregate status
    queryClient.invalidateQueries({ 
      queryKey: ['rag', 'list'], 
      exact: false 
    });
    
    return;
  }

  // For aggregate status updates (if backend sends them), update cache directly
  const { status } = event.data;
  if (!status) {
    return;
  }

  // Update document status in StatusGraph cache and recalculate aggregate on frontend
  queryClient.setQueriesData<StatusGraph>(
    { queryKey: ['rag', 'detail'], exact: false },
    old => {
    if (!old) return undefined;
    if ((old as any).doc_id && (old as any).doc_id !== doc_id) {
      return old;
    }

    // Idempotency check: ignore if event is older than cached data
    const lastSeq = getLastSequence(old);
    if (event.seq <= lastSeq) {
      return old; // Already processed
    }

    // Update status graph with event data
    const updated = {
      ...old,
      updated_at: event.timestamp,
      __last_seq: event.seq,
    } as StatusGraphCache;

    // Recalculate aggregate status on frontend for instant updates
    const targetModels = old.agg_details?.target_models || [];
    const aggResult = calculateAggregateStatus(updated, targetModels);

    return {
      ...updated,
      agg_status: aggResult.status,
      agg_details: aggResult.details,
    };
  });

  // Update status in list queries (all tenants)
  queryClient.setQueriesData<RagListCache>(
    { queryKey: ['rag', 'list'], exact: false },
    data => {
      if (!data) {
        console.debug('[SSE] No list data in cache');
        return undefined;
      }

      const itemExists = data.items.some(item => item.id === doc_id);
      
      // If document doesn't exist in list, invalidate to fetch it
      if (!itemExists) {
        console.debug('[SSE] Document not in list, invalidating:', doc_id);
        queryClient.invalidateQueries({ queryKey: ['rag', 'list'], exact: false });
        return data;
      }

      console.debug('[SSE] Updating document in list:', doc_id, '->', status);

      const updatedItems = data.items.map(item => {
        if (item.id === doc_id) {
          return {
            ...item,
            // Update both fields to keep UI in sync regardless of which one it reads
            status: status as RagDocument['agg_status'],
            agg_status: status as RagDocument['agg_status'],
            updated_at: event.timestamp,
          };
        }
        return item;
      });

      return {
        ...data,
        items: updatedItems,
      };
    }
  );
}

function applyEmbedProgressEvent(
  event: RagEvent & { type: 'rag.embed.progress' },
  queryClient: QueryClient
): void {
  const { doc_id } = event;
  const { model, progress, status, metrics, error } = event.data;

  // Update embeddings progress in list items (all tenants)
  queryClient.setQueriesData<RagListCache>(
    { queryKey: ['rag', 'list'], exact: false },
    data => {
      if (!data) return undefined;

      const updatedItems = data.items.map(item => {
        if (item.id === doc_id) {
          // Update or add embedding progress
          const currentEmbs = item.emb_status || [];
          const embIndex = currentEmbs.findIndex(
            (embedding: EmbeddingProgress) => embedding.model === model
          );

          const newEmb: EmbeddingProgress = {
            model,
            done: Math.round((progress || 0) * 100),
            total: 100,
            status,
            hasError: !!error,
            lastError: error,
          };

          const updatedEmbs =
            embIndex >= 0
              ? currentEmbs.map((e, i) => (i === embIndex ? newEmb : e))
              : [...currentEmbs, newEmb];

          return {
            ...item,
            emb_status: updatedEmbs,
            updated_at: event.timestamp,
          };
        }
        return item;
      });

      return {
        ...data,
        items: updatedItems,
      };
    }
  );

  // Also update StatusGraph if it exists (all tenants)
  queryClient.setQueriesData<StatusGraph>(
    { queryKey: ['rag', 'detail'], exact: false },
    old => {
    if (!old) return undefined;
    if ((old as any).doc_id && (old as any).doc_id !== doc_id) {
      return old;
    }

    const lastSeq = getLastSequence(old);
    if (event.seq <= lastSeq) {
      return old;
    }

    // Update embedding in the status graph
    const updatedEmbeddings = old.embeddings.map(emb => {
      if (emb.model === model) {
        return {
          ...emb,
          status,
          updated_at: event.timestamp,
          metrics,
          error,
        };
      }
      return emb;
    });

    // Add if not exists
    if (!updatedEmbeddings.some(emb => emb.model === model)) {
      updatedEmbeddings.push({
        model,
        version: event.data.version,
        status,
        updated_at: event.timestamp,
        metrics,
        error,
      });
    }

    const updated = {
      ...old,
      embeddings: updatedEmbeddings,
      updated_at: event.timestamp,
      __last_seq: event.seq,
    } as StatusGraphCache;

    // Recalculate aggregate status on frontend for instant updates
    const targetModels = old.agg_details?.target_models || [];
    const aggResult = calculateAggregateStatus(updated, targetModels);

    return {
      ...updated,
      agg_status: aggResult.status,
      agg_details: aggResult.details,
    };
  });
}

function applyTagsUpdatedEvent(
  event: RagEvent & { type: 'rag.tags.updated' },
  queryClient: QueryClient
): void {
  const { doc_id } = event;
  const { tags } = event.data;

  // Update tags in list (all tenants)
  queryClient.setQueriesData<{ items: RagDocument[] }>(
    { queryKey: ['rag', 'list'], exact: false },
    data => {
      if (!data) return undefined;

      const updatedItems = data.items.map(item => {
        if (item.id === doc_id) {
          return {
            ...item,
            tags,
            updated_at: event.timestamp,
          };
        }
        return item;
      });

      return {
        ...data,
        items: updatedItems,
      };
    }
  );
}

function applyDeletedEvent(
  event: RagEvent & { type: 'rag.deleted' },
  queryClient: QueryClient
): void {
  const { doc_id } = event;

  // Remove from all list queries (all tenants)
  queryClient.setQueriesData<RagListCache>(
    { queryKey: ['rag', 'list'], exact: false },
    data => {
      if (!data) return undefined;

      return {
        ...data,
        items: data.items.filter(item => item.id !== doc_id),
        total: data.total !== undefined ? data.total - 1 : undefined,
      };
    }
  );

  // Remove document queries (all tenants)
  queryClient.removeQueries({ queryKey: ['rag', 'detail'], exact: false });
}
