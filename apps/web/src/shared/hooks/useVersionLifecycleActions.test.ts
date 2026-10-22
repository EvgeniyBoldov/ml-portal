import { describe, expect, it } from 'vitest';
import { canDeleteVersion } from './useVersionLifecycleActions';

describe('canDeleteVersion', () => {
  it('allows deletion for archived versions', () => {
    expect(canDeleteVersion('archived', false)).toBe(true);
  });

  it('allows deletion for published versions only when they are not primary', () => {
    expect(canDeleteVersion('published', false)).toBe(true);
    expect(canDeleteVersion('published', true)).toBe(false);
  });

  it('does not allow deletion for drafts or unknown statuses', () => {
    expect(canDeleteVersion('draft', false)).toBe(false);
    expect(canDeleteVersion('unknown', false)).toBe(false);
  });
});
