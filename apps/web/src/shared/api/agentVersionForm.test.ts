import { describe, expect, it } from 'vitest';
import { buildAgentVersionPayload, parseTaskContracts } from './agentVersionForm';

describe('agent version form payload', () => {
  it('maps prompt, routing and execution fields into the API contract', () => {
    const payload = buildAgentVersionPayload({
      mission: '  Find records  ',
      tags: [' one ', '', 'two'],
      task_contracts_json: '[{"name":"lookup","inputs":["id"]}]',
      supports_dynamic_contracts: false,
      requires_fresh_retrieval: true,
      notes: ' note ',
    }, 'parent-id');

    expect(payload).toMatchObject({
      mission: 'Find records',
      tags: ['one', 'two'],
      task_contracts: [{ name: 'lookup', inputs: ['id'] }],
      supports_dynamic_contracts: false,
      requires_fresh_retrieval: true,
      notes: 'note',
      parent_version_id: 'parent-id',
    });
  });

  it('rejects malformed JSON and non-object contract entries', () => {
    expect(() => parseTaskContracts('{')).toThrow('корректный JSON');
    expect(() => parseTaskContracts('["lookup"]')).toThrow('массивом объектов');
    expect(() => parseTaskContracts('{}')).toThrow('массивом объектов');
  });

  it('accepts an empty contract list', () => {
    expect(parseTaskContracts('[]')).toEqual([]);
  });
});
