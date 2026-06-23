import { describe, expect, it } from 'vitest';
import { buildAgentData } from './entityDataBuilders';
import type { SemanticEvent } from './types';

function event(raw: Record<string, unknown>): SemanticEvent {
  return {
    id: 'evt-1',
    raw_type: 'user_request',
    category: 'input',
    title: 'user_request',
    summary: '',
    status: 'info',
    phase: 'agent',
    iteration: 0,
    raw: {
      id: 'raw-1',
      raw_type: 'user_request',
      raw,
    },
  };
}

describe('buildAgentData', () => {
  it('preserves structured available operations and collections from context snapshot', () => {
    const data = buildAgentData([
      event({
        context_snapshot: {
          meta: {
            available_operations: [
              {
                operation_slug: 'instance.template.collection.template.fill',
                canonical_name: 'collection.template.fill',
                scope_kind: 'collection',
                title: 'Fill Template',
                description: 'Fill a template',
                result_kind: 'file',
                collection_slug: 'template',
              },
            ],
            available_collections: [
              {
                collection_slug: 'template',
                collection_type: 'template',
                purpose: 'Заполнять заявки',
                readiness_status: 'ready',
              },
            ],
          },
        },
      }),
    ]);

    expect(data.toolsAvailable).toEqual(['instance.template.collection.template.fill']);
    expect(data.availableOperations?.[0]?.canonical_name).toBe('collection.template.fill');
    expect(data.availableCollections?.[0]?.collection_slug).toBe('template');
    expect(data.availableCollections?.[0]?.purpose).toBe('Заполнять заявки');
  });
});
