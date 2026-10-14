import { describe, expect, it } from 'vitest';
import { modelCharacteristicFields } from './modelPageFields';

describe('Model characteristics', () => {
  it('locks each reported field and allows missing characteristics independently', () => {
    const fields = modelCharacteristicFields('embedding', { dimensions: 1024 });
    expect(fields.find(f => f.key === 'embedding_dimensions')?.editable).toBe(
      false
    );
    expect(fields.find(f => f.key === 'max_input_tokens')?.editable).toBe(true);
    expect(fields.find(f => f.key === 'model_version')?.editable).toBe(true);
  });
  it('shows only the characteristics applicable to the model type', () => {
    expect(modelCharacteristicFields('llm_chat', {}).map(f => f.key)).toEqual([
      'model_version',
      'context_window_tokens',
    ]);
    expect(
      modelCharacteristicFields('reranker', { dimensions: 0 }).map(f => f.key)
    ).toEqual(['model_version', 'max_input_tokens']);
  });
  it('allows manual values when discovery is absent or invalid', () => {
    expect(
      modelCharacteristicFields('embedding', {
        dimensions: 0,
        max_tokens: -1,
        version: '',
      }).every(f => f.editable)
    ).toBe(true);
  });
});
