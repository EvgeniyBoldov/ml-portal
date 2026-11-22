import { describe, expect, it } from 'vitest';
import type { PeriodicRunDetail } from '@/shared/api/periodicTasks';
import {
  eventCleanupSummary,
  needsRunConfirmation,
} from './periodicRunPresentation';

const slug = 'runtime-events-expired-cleanup';
const date = '2026-11-21T09:07:17Z';
const run: PeriodicRunDetail = {
  id: 'run',
  source: 'manual',
  status: 'success',
  created_at: date,
  started_at: date,
  finished_at: date,
  duration_ms: 75,
  events: [
    {
      at: date,
      level: 'INFO',
      message:
        'Deleted 413 runtime events older than 2026-11-14 09:07:17.841637+00:00 (7-day retention)',
    },
  ],
  result: 413,
  result_limited: false,
  error: null,
};

describe('periodic run presentation', () => {
  it('explains the count and uses retention from the selected run', () => {
    expect(eventCleanupSummary(slug, run)).toEqual({
      label: 'Удалено 413 событий',
      retention: 'Срок хранения на момент запуска — 7 дней.',
    });
    expect(
      eventCleanupSummary(slug, { ...run, result: 0, events: [] })
    ).toEqual({
      label: 'Нет событий для удаления',
      retention: undefined,
    });
    expect(eventCleanupSummary(slug, { ...run, result: 21 })?.label).toBe(
      'Удалено 21 событие'
    );
    expect(eventCleanupSummary(slug, { ...run, result: 22 })?.label).toBe(
      'Удалено 22 события'
    );
  });

  it('leaves results with different semantics to the generic renderer', () => {
    expect(eventCleanupSummary('ldap-health-check', run)).toBeUndefined();
    expect(
      eventCleanupSummary(slug, { ...run, status: 'failure' })
    ).toBeUndefined();
    expect(
      eventCleanupSummary(slug, { ...run, result: { deleted: 413 } })
    ).toBeUndefined();
  });

  it('confirms data deletion tasks and leaves health checks direct', () => {
    expect(needsRunConfirmation(slug)).toBe(true);
    expect(needsRunConfirmation('ldap-health-check')).toBe(false);
  });
});
