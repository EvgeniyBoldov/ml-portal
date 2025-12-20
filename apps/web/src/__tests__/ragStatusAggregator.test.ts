import { describe, it, expect } from 'vitest';
import { calculateAggregateStatus } from '@shared/lib/ragStatusAggregator';
import type { StatusGraph } from '@shared/api/types/rag';

describe('ragStatusAggregator', () => {
  describe('calculateAggregateStatus()', () => {
    describe('pipeline failures', () => {
      it('should return failed if any pipeline stage failed', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'failed' },
            { key: 'normalize', status: 'pending' },
            { key: 'chunk', status: 'pending' },
          ],
          embeddings: [],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.status).toBe('failed');
        expect(result.details.policy).toBe('pipeline_error');
      });

      it('should return failed even if only one stage failed', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'completed' },
            { key: 'normalize', status: 'completed' },
            { key: 'chunk', status: 'failed' },
          ],
          embeddings: [],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.status).toBe('failed');
      });
    });

    describe('uploaded status', () => {
      it('should return uploaded when only upload is completed', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'pending' },
            { key: 'normalize', status: 'pending' },
            { key: 'chunk', status: 'pending' },
          ],
          embeddings: [],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.status).toBe('uploaded');
        expect(result.details.policy).toBe('uploaded');
      });
    });

    describe('processing status', () => {
      it('should return processing when pipeline is running', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'processing' },
            { key: 'normalize', status: 'pending' },
            { key: 'chunk', status: 'pending' },
          ],
          embeddings: [],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.status).toBe('processing');
        expect(result.details.policy).toBe('pipeline_running');
      });

      it('should return processing when stage is queued', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'queued' },
            { key: 'normalize', status: 'pending' },
            { key: 'chunk', status: 'pending' },
          ],
          embeddings: [],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.status).toBe('processing');
      });
    });

    describe('embedding status', () => {
      it('should return ready when all embeddings completed', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'completed' },
            { key: 'normalize', status: 'completed' },
            { key: 'chunk', status: 'completed' },
          ],
          embeddings: [
            { model: 'text-embedding-ada-002', status: 'completed' },
            { model: 'custom-embed', status: 'completed' },
          ],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.status).toBe('ready');
      });

      it('should return partial when some embeddings completed', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'completed' },
            { key: 'normalize', status: 'completed' },
            { key: 'chunk', status: 'completed' },
          ],
          embeddings: [
            { model: 'text-embedding-ada-002', status: 'completed' },
            { model: 'custom-embed', status: 'failed' },
          ],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.status).toBe('partial');
      });

      it('should return failed when all embeddings failed', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'completed' },
            { key: 'normalize', status: 'completed' },
            { key: 'chunk', status: 'completed' },
          ],
          embeddings: [
            { model: 'text-embedding-ada-002', status: 'failed' },
            { model: 'custom-embed', status: 'failed' },
          ],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.status).toBe('failed');
      });

      it('should return processing when embeddings are pending', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'completed' },
            { key: 'normalize', status: 'completed' },
            { key: 'chunk', status: 'completed' },
          ],
          embeddings: [
            { model: 'text-embedding-ada-002', status: 'processing' },
          ],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.status).toBe('processing');
      });
    });

    describe('with target models', () => {
      it('should check only target models for ready status', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'completed' },
            { key: 'normalize', status: 'completed' },
            { key: 'chunk', status: 'completed' },
          ],
          embeddings: [
            { model: 'text-embedding-ada-002', status: 'completed' },
            { model: 'other-model', status: 'failed' },
          ],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph, ['text-embedding-ada-002']);

        expect(result.status).toBe('ready');
        expect(result.details.policy).toBe('all_ready');
      });

      it('should return partial when some target models ready', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'completed' },
            { key: 'normalize', status: 'completed' },
            { key: 'chunk', status: 'completed' },
          ],
          embeddings: [
            { model: 'model-a', status: 'completed' },
            { model: 'model-b', status: 'processing' },
          ],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph, ['model-a', 'model-b']);

        expect(result.status).toBe('partial');
        expect(result.details.policy).toBe('partial_ready');
      });

      it('should return processing when target models are pending', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'completed' },
            { key: 'normalize', status: 'completed' },
            { key: 'chunk', status: 'completed' },
          ],
          embeddings: [],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph, ['model-a']);

        expect(result.status).toBe('processing');
        expect(result.details.policy).toBe('embedding_pending');
      });
    });

    describe('no embeddings', () => {
      it('should return ready when pipeline complete and no embeddings', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'completed' },
            { key: 'normalize', status: 'completed' },
            { key: 'chunk', status: 'completed' },
          ],
          embeddings: [],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.status).toBe('ready');
        expect(result.details.policy).toBe('pipeline_complete');
      });
    });

    describe('details', () => {
      it('should include pipeline statuses in details', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'processing' },
          ],
          embeddings: [],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.details.pipeline).toEqual({
          upload: 'completed',
          extract: 'processing',
        });
      });

      it('should include embedding statuses in details', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'completed' },
            { key: 'normalize', status: 'completed' },
            { key: 'chunk', status: 'completed' },
          ],
          embeddings: [
            { model: 'model-a', status: 'completed' },
            { model: 'model-b', status: 'processing' },
          ],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.details.embedding).toEqual({
          'model-a': 'completed',
          'model-b': 'processing',
        });
      });

      it('should include counters in details', () => {
        const statusGraph: StatusGraph = {
          pipeline: [
            { key: 'upload', status: 'completed' },
            { key: 'extract', status: 'completed' },
            { key: 'normalize', status: 'completed' },
            { key: 'chunk', status: 'completed' },
          ],
          embeddings: [
            { model: 'model-a', status: 'completed' },
            { model: 'model-b', status: 'failed' },
            { model: 'model-c', status: 'processing' },
          ],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph, ['model-a', 'model-b', 'model-c']);

        expect(result.details.counters).toEqual({
          target_models: 3,
          ready_models: 1,
          error_models: 1,
          missing_models: 1,
        });
      });

      it('should include updated_at timestamp', () => {
        const statusGraph: StatusGraph = {
          pipeline: [{ key: 'upload', status: 'completed' }],
          embeddings: [],
          indexes: [],
        };

        const result = calculateAggregateStatus(statusGraph);

        expect(result.details.updated_at).toBeDefined();
        expect(new Date(result.details.updated_at).getTime()).toBeLessThanOrEqual(Date.now());
      });
    });
  });
});
