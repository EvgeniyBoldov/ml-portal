import { describe, expect, it } from 'vitest';
import {
  presentToolData,
  TOOL_RESULT_PREVIEW_LIMIT,
} from './toolDataPresentation';

describe('presentToolData', () => {
  it('represents an empty successful payload as empty, not as a failure', () => {
    expect(presentToolData([])).toEqual({ kind: 'empty' });
  });

  it('bounds a record preview while keeping the source array untouched for full viewing', () => {
    const original = Array.from({ length: 25 }, (_, index) => ({
      id: index + 1,
      title: `Issue ${index + 1}`,
    }));
    const presentation = presentToolData(original);
    expect(presentation.kind).toBe('records');
    if (presentation.kind !== 'records') return;
    expect(presentation.rows).toHaveLength(TOOL_RESULT_PREVIEW_LIMIT);
    expect(presentation.shown).toBe(20);
    expect(presentation.available).toBe(25);
    expect(original).toHaveLength(25);
  });

  it('uses payload length for availability instead of a stored result row count', () => {
    const preview = presentToolData([{ title: 'sample' }], { returnedCount: 500, sourceTotal: 1200 });
    expect(preview.kind).toBe('records');
    if (preview.kind === 'records') {
      expect(preview.shown).toBe(1);
      expect(preview.available).toBe(1);
    }
  });

  it('recognizes ResultPage but keeps an arbitrary data field as a record value', () => {
    expect(
      presentToolData({ value: [{ key: 'A' }], meta: { total: 1 } }).kind
    ).toBe('records');
    const arbitrary = presentToolData({
      data: [{ key: 'A' }],
      note: 'domain object',
    });
    expect(arbitrary.kind).toBe('record');
    if (arbitrary.kind === 'record')
      expect(
        arbitrary.entries.find(entry => entry.key === 'data')?.value
      ).toEqual([{ key: 'A' }]);
  });

  it('does not mistake a stored result descriptor for a dataset', () => {
    expect(
      presentToolData(
        { payload_type: 'rows', row_count: 400 },
        { delivery: 'stored', resultId: 'opaque' }
      ).kind
    ).toBe('descriptor');
    expect(
      presentToolData(
        { result_id: 'domain-id', title: 'Issue' },
        { delivery: 'stored' }
      ).kind
    ).toBe('record');
    expect(
      presentToolData(
        { result_id: 'opaque', payload_type: 'rows', row_count: 400 },
        { delivery: 'stored' }
      ).kind
    ).toBe('descriptor');
    expect(
      presentToolData(
        { payload_type: 'rows', row_count: 400 },
        { delivery: 'direct' }
      ).kind
    ).toBe('record');
  });

  it('unwraps only an explicitly marked runtime envelope and filters metadata fields', () => {
    const model = presentToolData({
      _runtime_result: { row_count: 1, next_arguments: { secret: 'binding' } },
      data: [{ issue_key: 'OPS-4' }],
    });
    expect(model.kind).toBe('records');
    if (model.kind === 'records')
      expect(model.pageMetadata).toEqual({ row_count: 1 });
  });

  it('retains an expandable fallback for unknown scalar values', () => {
    expect(presentToolData(7).kind).toBe('scalars');
    expect(
      presentToolData({ external_schema: { unexpected: true } }).kind
    ).toBe('record');
    expect(presentToolData({ result_id: 'hidden-ref' }).kind).toBe('fallback');
  });
});
