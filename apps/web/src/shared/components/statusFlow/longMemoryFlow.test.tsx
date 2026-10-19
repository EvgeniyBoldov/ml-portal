import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { adaptStatusGraphToDocStatus } from '@/shared/lib/documentStatusAdapter';
import { adaptDocumentStatusToFlowModel } from './documentFlowAdapter';
import { StatusFlowView } from './StatusFlowView';
import { resolveSelectedNode } from './statusFlowUtils';

it('shows LongMemory as an independent branch after normalize with selectable metrics', () => {
  const model = adaptDocumentStatusToFlowModel(
    adaptStatusGraphToDocStatus({
      doc_id: 'doc',
      agg_status: 'processing',
      agg_details: {},
      pipeline: [
        { key: 'normalize', status: 'completed', updated_at: '2026-10-15' },
        { key: 'chunk', status: 'processing', updated_at: '2026-10-15' },
      ],
      embeddings: [],
      index: [],
      memory: [
        {
          key: 'knowledge',
          status: 'completed',
          metrics: { facts: 12 },
          updated_at: '2026-10-15',
        },
        {
          key: 'graph',
          status: 'processing',
          metrics: { encoded_texts: 20 },
          updated_at: '2026-10-15',
        },
      ],
    })
  );
  expect(model.parallel?.after).toBe('normalize');
  const onSelect = vi.fn();
  render(
    <StatusFlowView
      model={model}
      selection={{ nodeKey: null }}
      onSelect={onSelect}
    />
  );
  expect(screen.getByText('LongMemory')).toBeInTheDocument();
  fireEvent.click(screen.getByText('Извлечение знаний'));
  const selection = onSelect.mock.calls[0][0];
  expect(resolveSelectedNode(model, selection).node?.metrics?.facts).toBe(12);
  expect(screen.getByText('Индекс LongMemory')).toBeInTheDocument();
});
