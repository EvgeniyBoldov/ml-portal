import type { PeriodicTask } from '@/shared/api/periodicTasks';

export const PERIODIC_TASKS_PATH = '/admin/periodic-tasks';

export function formatSchedule(schedule: Record<string, unknown>) {
  if (schedule.type === 'interval') {
    const seconds = Number(schedule.seconds);
    if (!Number.isFinite(seconds) || seconds <= 0) return '—';
    if (seconds % 3600 === 0) return `Интервал ${seconds / 3600} ч`;
    if (seconds % 60 === 0) return `Интервал ${seconds / 60} мин`;
    return `Интервал ${seconds} с`;
  }
  if (schedule.type === 'crontab') {
    const {
      minute = '*',
      hour = '*',
      day_of_month = '*',
      month_of_year = '*',
      day_of_week = '*',
    } = schedule;
    if (
      day_of_month === '*' &&
      month_of_year === '*' &&
      day_of_week === '*' &&
      /^\d{1,2}$/.test(String(hour)) &&
      /^\d{1,2}$/.test(String(minute))
    ) {
      return `Ежедневно в ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')} UTC`;
    }
    return `Cron · ${minute} ${hour} ${day_of_month} ${month_of_year} ${day_of_week}`;
  }
  return '—';
}

export function formatTimestamp(value?: string | null) {
  if (!value) return '—';
  return new Date(value).toLocaleString('ru-RU', {
    dateStyle: 'short',
    timeStyle: 'medium',
  });
}

export function formatDuration(value?: number | null) {
  if (value == null) return '—';
  if (value < 1000) return `${value} мс`;
  return `${(value / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} с`;
}

export const scheduleStatuses = [
  { value: 'enabled', label: 'Включена', tone: 'success' },
  { value: 'disabled', label: 'Выключена', tone: 'neutral' },
  { value: 'orphaned', label: 'Нет в расписании', tone: 'warn' },
] as const;

export function scheduleStatus(task: PeriodicTask) {
  return scheduleStatuses[task.is_orphaned ? 2 : task.is_enabled ? 0 : 1];
}

export const runStatuses = {
  success: { label: 'Успешно', tone: 'success' },
  failure: { label: 'Ошибка', tone: 'danger' },
  running: { label: 'Выполняется', tone: 'info' },
  queued: { label: 'В очереди', tone: 'info' },
  retry: { label: 'Ожидает повтора', tone: 'warn' },
  skipped: { label: 'Пропущен', tone: 'neutral' },
} as const;

export function runStatus(status?: string | null) {
  if (status && Object.prototype.hasOwnProperty.call(runStatuses, status)) {
    return runStatuses[status as keyof typeof runStatuses];
  }
  return { label: status || 'Нет данных', tone: 'neutral' as const };
}

export const categories: Record<string, string> = {
  health: 'Доступность',
  cleanup: 'Очистка',
  reconcile: 'Восстановление',
  sync: 'Синхронизация',
  other: 'Системные',
};
