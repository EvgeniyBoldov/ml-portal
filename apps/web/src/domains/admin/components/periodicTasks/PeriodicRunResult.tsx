import { useId, useState } from 'react';
import { Button, JSONDisplay } from '@/shared/ui';
import styles from './PeriodicRunResult.module.css';

const modes = [
  { value: 'collapsed', label: 'Свёрнуто' },
  { value: 'brief', label: 'Кратко' },
  { value: 'full', label: 'Просмотр' },
] as const;

type ResultMode = (typeof modes)[number]['value'];
const previewLimit = 6;
const fieldNames: Readonly<Record<string, string>> = {
  status: 'Статус',
  reachable: 'Доступен',
  checked: 'Проверено',
  healthy: 'Доступно',
  unhealthy: 'Недоступно',
  error: 'Ошибка',
  timestamp: 'Время проверки',
};

function previewValue(value: unknown): string {
  if (value == null) return '—';
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  if (typeof value === 'number')
    return value.toLocaleString('ru-RU', { maximumSignificantDigits: 21 });
  if (typeof value === 'string')
    return value.length > 140
      ? `${value.slice(0, 140)}…`
      : value || 'Пустая строка';
  if (Array.isArray(value)) return `Элементов: ${value.length}`;
  if (typeof value === 'object') return `Полей: ${Object.keys(value).length}`;
  return String(value);
}

function ResultPreview({
  value,
  scalarLabel,
}: {
  value: unknown;
  scalarLabel?: string;
}) {
  const entries: [string, unknown][] =
    value !== null && typeof value === 'object'
      ? Object.entries(value)
      : [[scalarLabel ?? 'Значение', value]];
  if (!entries.length) {
    return (
      <p className={styles.note}>
        {Array.isArray(value) ? 'Пустой список' : 'Нет полей'}
      </p>
    );
  }

  return (
    <>
      <dl className={styles.fields}>
        {entries.slice(0, previewLimit).map(([key, item]) => (
          <div key={key}>
            <dt>
              {Array.isArray(value)
                ? `Элемент ${Number(key) + 1}`
                : Object.prototype.hasOwnProperty.call(fieldNames, key)
                  ? fieldNames[key]
                  : key}
            </dt>
            <dd>
              {key === 'status' && item === 'disabled'
                ? 'Выключен'
                : previewValue(item)}
            </dd>
          </div>
        ))}
      </dl>
      {entries.length > previewLimit && (
        <p className={styles.note}>
          Показано {previewLimit} из {entries.length}
        </p>
      )}
    </>
  );
}

export function PeriodicRunResult({
  value,
  scalarLabel,
}: {
  value: unknown;
  scalarLabel?: string;
}) {
  const contentId = useId();
  const [mode, setMode] = useState<ResultMode>(
    scalarLabel ? 'collapsed' : 'brief'
  );

  return (
    <div className={styles.result}>
      <div className={styles.controls}>
        <span className={styles.label}>Данные результата</span>
        <div
          role="group"
          aria-label="Режим отображения результата"
          className={styles.modes}
        >
          {modes.map(item => (
            <Button
              key={item.value}
              type="button"
              size="sm"
              variant="ghost"
              className={styles.modeButton}
              aria-pressed={mode === item.value}
              aria-controls={contentId}
              onClick={() => setMode(item.value)}
            >
              {item.label}
            </Button>
          ))}
        </div>
      </div>
      <div
        id={contentId}
        hidden={mode === 'collapsed'}
        className={styles.content}
      >
        {mode === 'brief' && (
          <ResultPreview value={value} scalarLabel={scalarLabel} />
        )}
        {mode === 'full' && (
          <JSONDisplay
            value={JSON.stringify(value, null, 2)}
            showHeader={false}
            showCopy={false}
          />
        )}
      </div>
    </div>
  );
}
