import { cleanStreamingText, normalizeText } from '@/shared/lib/textNormalize';

describe('textNormalize', () => {
  it('removes only [DONE] marker', () => {
    expect(normalizeText('hello[DONE] world')).toBe('hello world');
  });

  it('does not trim or alter regular text', () => {
    expect(normalizeText('  keep   spaces  ')).toBe('  keep   spaces  ');
  });

  it('returns empty string for empty input', () => {
    expect(normalizeText('')).toBe('');
  });

  it('cleanStreamingText is an alias of normalizeText', () => {
    expect(cleanStreamingText('A[DONE]B')).toBe('AB');
  });
});
