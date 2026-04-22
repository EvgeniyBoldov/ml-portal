import { idempotencyKey } from '@/shared/lib/idempotency';

describe('idempotencyKey', () => {
  it('returns a non-empty key', () => {
    const key = idempotencyKey();
    expect(typeof key).toBe('string');
    expect(key.length).toBeGreaterThan(0);
  });

  it('returns unique keys across calls', () => {
    const first = idempotencyKey();
    const second = idempotencyKey();
    expect(first).not.toBe(second);
  });
});
