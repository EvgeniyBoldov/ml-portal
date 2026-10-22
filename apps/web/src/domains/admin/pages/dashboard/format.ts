export const number = (value: number | null) =>
  value === null ? '—' : value.toLocaleString('ru-RU');
export const timestamp = (value: string) =>
  new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
export const duration = (value: number | null) =>
  value === null
    ? '—'
    : `${(value / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} с`;
export function bytes(value: number): string {
  if (!value) return '0 Б';
  const unit = Math.min(Math.floor(Math.log(value) / Math.log(1024)), 4);
  return `${(value / 1024 ** unit).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} ${['Б', 'КиБ', 'МиБ', 'ГиБ', 'ТиБ'][unit]}`;
}
const roles: Record<string, string> = {
  turn_preflight: 'Маршрутизатор',
  planner: 'Планер',
  synthesizer: 'Синтезатор',
  fact_extractor: 'Извлечение фактов',
  fact_compactor: 'Уплотнение фактов',
  chat_context_compactor: 'Сжатие контекста',
};
export function assignment(value: string): string {
  const role = value.startsWith('Роль: ') ? value.slice(6) : '';
  return roles[role] ?? value;
}
