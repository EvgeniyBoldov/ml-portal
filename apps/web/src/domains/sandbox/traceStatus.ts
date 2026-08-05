export type TraceStatusTone = 'neutral' | 'success' | 'warn' | 'danger' | 'info';

export function normalizeTraceStatus(status: string | null | undefined): string {
  const value = String(status ?? '').toLowerCase();
  if (['completed', 'complete', 'success', 'succeeded'].includes(value)) return 'completed';
  if (['failed', 'fail', 'error'].includes(value)) return 'failed';
  if (value === 'unfulfillable') return 'unfulfillable';
  if (['waiting', 'waiting_input'].includes(value)) return 'waiting_input';
  if (value === 'waiting_confirmation') return 'waiting_confirmation';
  if (value === 'paused') return 'paused';
  if (['aborted', 'cancelled', 'canceled'].includes(value)) return 'aborted';
  if (value === 'stalled') return 'stalled';
  if (value === 'running') return 'running';
  return value || 'unknown';
}

export function traceStatusLabel(status: string | null | undefined): string {
  return ({
    completed: 'Готово', failed: 'Ошибка', unfulfillable: 'Неисполнимо',
    waiting_input: 'Ожидает данных', waiting_confirmation: 'Ожидает подтверждения',
    paused: 'На паузе', stalled: 'Остановлено', aborted: 'Прервано', running: 'Выполняется', unknown: 'Нет результата',
  } as Record<string, string>)[normalizeTraceStatus(status)] ?? String(status);
}

export function traceStatusTone(status: string | null | undefined): TraceStatusTone {
  const normalized = normalizeTraceStatus(status);
  if (['failed', 'unfulfillable', 'stalled', 'aborted'].includes(normalized)) return 'danger';
  if (['waiting_input', 'waiting_confirmation', 'paused'].includes(normalized)) return 'warn';
  if (normalized === 'completed') return 'success';
  return normalized === 'unknown' ? 'neutral' : 'info';
}
