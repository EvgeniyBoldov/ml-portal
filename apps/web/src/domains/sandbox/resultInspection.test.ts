import { describe, expect, it } from 'vitest';
import { resultStatusLabel } from './resultInspection';

describe('result inspection projection', () => {
  it('uses user-facing labels for terminal runtime states', () => {
    expect(resultStatusLabel('completed')).toBe('Готово');
    expect(resultStatusLabel('failed')).toBe('Ошибка');
    expect(resultStatusLabel('aborted')).toBe('Прервано');
  });
});
