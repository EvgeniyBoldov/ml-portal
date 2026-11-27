export const runStatusLabel: Record<string, string> = {
  completed: 'Завершён',
  failed: 'Ошибка',
  cancelled: 'Отменён',
  running: 'Выполняется',
  queued: 'В очереди',
  waiting_retry: 'Повтор',
  waiting_input: 'Ожидает ответа',
  waiting_confirmation: 'Ожидает подтверждения',
  waiting_timer: 'Ожидает по таймеру',
  paused: 'На паузе',
  unfulfillable: 'Не выполнено',
};
export const runStatusTone = (status: string): 'neutral' | 'success' | 'warn' | 'danger' | 'info' => {
  if (status === 'completed') return 'success';
  if (status === 'failed' || status === 'unfulfillable') return 'danger';
  if (status === 'cancelled' || status === 'waiting_retry' || status === 'waiting_input' || status === 'waiting_confirmation' || status === 'waiting_timer' || status === 'paused') return 'warn';
  if (status === 'running') return 'info';
  return 'neutral';
};
