// Frontend aggregate status calculator - mirrors backend logic for instant updates via SSE
import { StatusGraph } from '@shared/api/types/rag';

export interface AggregateStatusResult {
  status: string;
  details: Record<string, any>;
}

/**
 * Calculate aggregate status on frontend for instant updates via SSE
 * Mirrors backend calculate_aggregate_status logic
 */
export function calculateAggregateStatus(
  statusGraph: StatusGraph,
  targetModels: string[] = []
): AggregateStatusResult {
  const pipeline = statusGraph.pipeline;
  const embeddings = statusGraph.embeddings;

  // Build pipeline statuses map
  const pipelineStatuses: Record<string, string> = {};
  for (const stage of pipeline) {
    pipelineStatuses[stage.key] = stage.status;
  }

  // 1. If any pipeline stage has failed → failed
  if (Object.values(pipelineStatuses).some(status => status === 'failed')) {
    return {
      status: 'failed',
      details: {
        pipeline: pipelineStatuses,
        embedding: {},
        policy: 'pipeline_error',
        updated_at: new Date().toISOString(),
      },
    };
  }

  // 2. Special case: uploaded (upload=completed, others=pending)
  if (
    pipelineStatuses['upload'] === 'completed' &&
    Object.entries(pipelineStatuses)
      .filter(([key]) => key !== 'upload')
      .every(([, status]) => status === 'pending')
  ) {
    return {
      status: 'uploaded',
      details: {
        pipeline: pipelineStatuses,
        embedding: {},
        policy: 'uploaded',
        updated_at: new Date().toISOString(),
      },
    };
  }

  // 3. If any pipeline stage is pending/queued/processing → processing
  if (
    Object.values(pipelineStatuses).some(
      status => status === 'pending' || status === 'queued' || status === 'processing'
    )
  ) {
    return {
      status: 'processing',
      details: {
        pipeline: pipelineStatuses,
        embedding: {},
        policy: 'pipeline_running',
        updated_at: new Date().toISOString(),
      },
    };
  }

  // 4. Pipeline is complete, check embedding status
  const embeddingStatuses: Record<string, string> = {};
  for (const emb of embeddings) {
    embeddingStatuses[emb.model] = emb.status;
  }

  // Count target models and completed embeddings
  const N = targetModels.length || embeddings.length; // Total target models
  const R =
    targetModels.length > 0
      ? targetModels.filter(model => embeddingStatuses[model] === 'completed').length
      : embeddings.filter(emb => emb.status === 'completed').length;
  const E =
    targetModels.length > 0
      ? targetModels.filter(model => embeddingStatuses[model] == 'failed').length
      : embeddings.filter(emb => emb.status == 'failed').length;
  const MISSING = N - (R + E);

  // Calculate aggregate status
  let aggStatus: string;
  let policy: string;

  if (N === 0) {
    // No target models - check if pipeline completed successfully
    if (Object.values(pipelineStatuses).every(s => s === 'completed')) {
      if (embeddings.length > 0) {
        const successful = embeddings.filter(emb => emb.status === 'completed').length;
        const error = embeddings.filter(emb => emb.status === 'failed').length;

        if (successful > 0) {
          if (error === 0) {
            aggStatus = 'ready';
            policy = 'pipeline_complete_all_embeddings_ok';
          } else {
            aggStatus = 'partial';
            policy = 'pipeline_complete_some_embeddings_ok';
          }
        } else if (error > 0) {
          aggStatus = 'failed';
          policy = 'pipeline_complete_all_embeddings_failed';
        } else {
          aggStatus = 'processing';
          policy = 'pipeline_complete_embeddings_pending';
        }
      } else {
        aggStatus = 'ready';
        policy = 'pipeline_complete';
      }
    } else {
      aggStatus = 'missing';
      policy = 'no_target_models';
    }
  } else if (R === N) {
    aggStatus = 'ready';
    policy = 'all_ready';
  } else if (R > 0 && R < N) {
    aggStatus = 'partial';
    policy = 'partial_ready';
  } else if (R === 0 && MISSING > 0) {
    aggStatus = 'processing';
    policy = 'embedding_pending';
  } else if (R === 0 && E > 0 && MISSING === 0) {
    aggStatus = 'failed';
    policy = 'all_failed';
  } else {
    aggStatus = 'processing';
    policy = 'unknown';
  }

  // Build details
  const details: Record<string, any> = {
    pipeline: pipelineStatuses,
    embedding: embeddingStatuses,
    policy,
    counters: {
      target_models: N,
      ready_models: R,
      error_models: E,
      missing_models: MISSING,
    },
    target_models:
      targetModels.length > 0 ? targetModels : embeddings.map(emb => emb.model),
    updated_at: new Date().toISOString(),
  };

  return {
    status: aggStatus,
    details,
  };
}
