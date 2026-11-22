import type { PeriodicRunDetail } from '@/shared/api/periodicTasks';

const deletionTasks = new Set([
  'sandbox-sessions-expired-cleanup',
  'runtime-tool-results-expired-cleanup',
  'runtime-events-expired-cleanup',
  'complete-tool-payloads-expired-cleanup',
  'orphaned-chat-attachments-cleanup',
  'expired-chat-attachments-cleanup',
  'private-file-indexes-expired-cleanup',
  'deprecated-entities-cleanup',
]);

export function needsRunConfirmation(slug: string) {
  return deletionTasks.has(slug);
}

export function isActivePeriodicRun(status: string) {
  return status === 'queued' || status === 'running' || status === 'retry';
}

export function runSourceLabel(source: string) {
  return source === 'manual' ? 'Ручной запуск' : 'По расписанию';
}

const russianPlural = new Intl.PluralRules('ru-RU');

export function eventCleanupSummary(slug: string, run: PeriodicRunDetail) {
  if (
    slug !== 'runtime-events-expired-cleanup' ||
    run.status !== 'success' ||
    typeof run.result !== 'number' ||
    !Number.isSafeInteger(run.result) ||
    run.result < 0
  ) {
    return undefined;
  }
  const count = run.result;
  const noun = {
    one: 'событие',
    few: 'события',
    many: 'событий',
    other: 'события',
  };
  const retention = run.events
    .map(event =>
      /^Deleted \d+ runtime events older than .+ \((\d+)-day retention\)$/.exec(
        event.message
      )
    )
    .find(Boolean);
  const days = retention && Number(retention[1]);
  const day = { one: 'день', few: 'дня', many: 'дней', other: 'дня' };

  return {
    label:
      count === 0
        ? 'Нет событий для удаления'
        : `Удалено ${count.toLocaleString('ru-RU')} ${noun[russianPlural.select(count) as keyof typeof noun]}`,
    retention: days
      ? `Срок хранения на момент запуска — ${days} ${day[russianPlural.select(days) as keyof typeof day]}.`
      : undefined,
  };
}
