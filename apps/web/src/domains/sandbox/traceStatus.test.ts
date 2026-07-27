import { describe, expect, it } from 'vitest';
import { normalizeTraceStatus, traceStatusLabel, traceStatusTone } from './traceStatus';

describe('trace status presentation', () => {
  it('normalizes terminal and waiting runtime statuses', () => {
    expect(normalizeTraceStatus('success')).toBe('completed');
    expect(normalizeTraceStatus('error')).toBe('failed');
    expect(normalizeTraceStatus('waiting_confirmation')).toBe('waiting_confirmation');
  });

  it('provides shared labels and tones', () => {
    expect(traceStatusLabel('unfulfillable')).toBe('Неисполнимо');
    expect(traceStatusLabel('waiting_confirmation')).toBe('Ожидает подтверждения');
    expect(traceStatusTone('failed')).toBe('danger');
    expect(traceStatusTone('waiting_input')).toBe('warn');
  });
});
