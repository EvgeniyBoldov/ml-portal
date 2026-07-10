import { describe, expect, it } from 'vitest';

import { adaptDocumentStatusToFlowModel } from './documentFlowAdapter';
import { adaptTemplateStatusGraphToFlowModel } from './templateFlowAdapter';
import { pickDefaultFlowSelection } from './statusFlowUtils';

describe('status flow adapters and selection', () => {
  it('prefers failed lane item over completed pipeline node', () => {
    const selection = pickDefaultFlowSelection({
      pipeline: [
        { key: 'upload', label: 'Upload', status: 'completed' },
        { key: 'extract', label: 'Extract', status: 'completed' },
      ],
      lanes: [
        {
          key: 'index',
          label: 'Index',
          items: [
            { key: 'idx.default', label: 'idx.default', status: 'failed' },
          ],
        },
      ],
    });

    expect(selection).toEqual({
      nodeKey: 'idx.default',
      laneKey: 'index',
      itemKey: 'idx.default',
    });
  });

  it('adapts document status into pipeline and lanes', () => {
    const model = adaptDocumentStatusToFlowModel({
      id: 'doc-1',
      name: 'doc-1',
      stages: {
        upload: { stage: 'upload', state: 'ok' },
        extract: { stage: 'extract', state: 'running' },
        normalize: { stage: 'normalize', state: 'pending' },
        chunk: { stage: 'chunk', state: 'pending' },
        embedding: { stage: 'embedding', state: 'pending' },
        index: { stage: 'index', state: 'pending' },
        archive: { stage: 'archive', state: 'pending' },
      },
      embed_models: [{ id: 'm1', name: 'm1', state: 'ok' }],
      index_models: [{ id: 'm1', name: 'm1', state: 'running' }],
    });

    expect(model.pipeline).toHaveLength(4);
    expect(model.lanes?.map((lane) => lane.key)).toEqual(['embedding', 'index']);
    expect(model.pipeline[1].status).toBe('processing');
  });

  it('adapts template graph into linear pipeline', () => {
    const model = adaptTemplateStatusGraphToFlowModel({
      row_id: 'row-1',
      collection_id: 'col-1',
      stages: [
        { key: 'uploaded', label: 'Загружен', state: 'completed', started_at: '2026-01-01T10:00:00Z' },
        { key: 'approval', label: 'Утверждение', state: 'pending', finished_at: '2026-01-01T10:05:00Z' },
      ],
    });

    expect(model.pipeline).toHaveLength(2);
    expect(model.pipeline[1].key).toBe('approval');
    expect(model.pipeline[1].status).toBe('pending');
    expect(model.pipeline[0].started_at).toBe('2026-01-01T10:00:00Z');
    expect(model.pipeline[1].finished_at).toBe('2026-01-01T10:05:00Z');
  });
});
