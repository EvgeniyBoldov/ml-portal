import { describe, expect, it } from 'vitest';
import { buildCoverage, extractContractKeys } from './responseContractCoverage';
import type { ResponseContract } from '@/shared/api/admin';

const plannerContract: ResponseContract = {
  format: 'json',
  schema: {
    type: 'object',
    properties: {
      kind: { type: 'string' },
      rationale: { type: 'string' },
      agent_slug: { type: 'string' },
    },
  },
  plain_text: null,
  markdown: null,
  examples: [],
  failure_policy: { on_invalid: 'retry_once_then_fallback' },
};

describe('responseContractCoverage', () => {
  it('extracts json property keys', () => {
    expect(extractContractKeys(plannerContract)).toEqual(['kind', 'rationale', 'agent_slug']);
  });

  it('builds described and missing key lists', () => {
    const coverage = buildCoverage(
      plannerContract,
      'Use kind and rationale fields',
      'agent_slug is optional',
    );
    expect(coverage.described).toEqual(['kind', 'rationale', 'agent_slug']);
    expect(coverage.missing).toEqual([]);
  });

  it('returns empty coverage for non-json contract', () => {
    const plain: ResponseContract = {
      format: 'plain_text',
      schema: null,
      plain_text: { criteria: ['x'], forbidden: ['y'] },
      markdown: null,
      examples: [],
      failure_policy: { on_invalid: 'accept_with_runtime_safety_filters' },
    };
    const coverage = buildCoverage(plain, 'kind', 'rationale');
    expect(coverage.keys).toEqual([]);
    expect(coverage.described).toEqual([]);
    expect(coverage.missing).toEqual([]);
  });
});

