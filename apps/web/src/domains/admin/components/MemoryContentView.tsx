import type { ReactNode } from 'react';
import { Badge, Toggle } from '@/shared/ui';
import styles from './MemoryContentView.module.css';

export const contentFieldLabels: Record<string, string> = {
  definition: 'Определение', summary: 'Описание', details: 'Подробности', statement: 'Формулировка',
  effect: 'Действие', conditions: 'Условия', required_approvals: 'Согласования', required_checks: 'Обязательные проверки',
  exceptions: 'Исключения', consequences: 'Последствия', limits: 'Ограничения', decision: 'Решение', rationale: 'Обоснование',
  goal: 'Цель', applicability_conditions: 'Условия применимости', prechecks: 'Предварительные проверки', steps: 'Шаги',
  verification: 'Проверка результата', rollback: 'Откат', instruction: 'Действие', expected_result: 'Ожидаемый результат',
  confirmation_required: 'Требуется подтверждение', mode: 'Режим', reason: 'Причина', order: 'Порядок',
};
export const memoryTypeLabels: Record<string, string> = {
  term: 'Термин', description: 'Описание', relationship: 'Связь', rule: 'Правило',
  constraint: 'Ограничение', procedure: 'Процедура', decision: 'Решение',
};
export const memoryStateLabels: Record<string, string> = {
  active: 'Активна', uncertain: 'Есть противоречия', stale: 'Устарела', extracted: 'Извлечена',
  needs_review: 'На проверке', conflict: 'Есть конфликт', resolved: 'Утверждена', rejected: 'Отклонена', superseded: 'Заменена',
};
type Field = { key: string; kind: 'text' | 'list' | 'effect' | 'steps' | 'rollback'; required?: boolean };
const text = (key: string): Field => ({ key, kind: 'text', required: true });
const list = (key: string, required = false): Field => ({ key, kind: 'list', required });
const schemas: Record<string, Field[]> = {
  term: [text('definition')], description: [text('summary'), list('details')], relationship: [text('summary')],
  rule: [text('statement'), { key: 'effect', kind: 'effect', required: true }, list('conditions'), list('required_approvals'), list('required_checks'), list('exceptions'), list('consequences')],
  constraint: [text('statement'), list('conditions'), list('limits', true), list('exceptions'), list('consequences')],
  decision: [text('decision'), list('conditions'), list('rationale'), list('consequences')],
  procedure: [text('goal'), list('applicability_conditions'), list('required_approvals'), list('prechecks', true),
    { key: 'steps', kind: 'steps', required: true }, list('verification', true), { key: 'rollback', kind: 'rollback', required: true }, list('exceptions')],
};
const effects: Record<string, string> = { require: 'Обязательно', forbid: 'Запрещено', allow: 'Разрешено' };
const isObject = (value: unknown): value is Record<string, unknown> => Boolean(value && typeof value === 'object' && !Array.isArray(value));
const present = (value: unknown) => value !== null && value !== undefined && value !== '' && !(Array.isArray(value) && !value.length);
const invalid = (value: unknown, message = 'Неверный формат поля') => <div className={styles.invalid}><span>{message}</span>{value !== undefined && <pre>{JSON.stringify(value, null, 2)}</pre>}</div>;
function strings(value: unknown, required = false): ReactNode {
  if (!present(value)) return required ? invalid(value, 'Обязательный список не заполнен') : <span className={styles.empty}>Не указано</span>;
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) return invalid(value, 'Ожидается список текстовых значений');
  return <ul className={styles.list}>{value.map((item, index) => <li key={index}>{item || 'Пустой пункт'}</li>)}</ul>;
}
function steps(value: unknown): ReactNode {
  if (!Array.isArray(value) || !value.length) return invalid(value, 'Шаги процедуры не указаны');
  return <ol className={styles.steps}>{value.map((step, index) => <li key={index}>
    {!isObject(step) ? invalid(step, 'Ожидается объект шага') : <>
      <strong>Шаг {typeof step.order === 'number' ? step.order : index + 1}</strong>
      <dl className={styles.fields}>
        {['instruction', 'expected_result'].map((key) => <div key={key}><dt>{contentFieldLabels[key]}</dt><dd>{typeof step[key] === 'string' && step[key] ? step[key] : invalid(step[key], 'Обязательный текст не заполнен или имеет неверный формат')}</dd></div>)}
        <div><dt>Подтверждение</dt><dd>{typeof step.confirmation_required === 'boolean'
          ? <Badge tone={step.confirmation_required ? 'warn' : 'neutral'}>{step.confirmation_required ? 'Требуется' : 'Не требуется'}</Badge>
          : invalid(step.confirmation_required, 'Требование подтверждения не указано или имеет неверный формат')}</dd></div>
      </dl>
      {step.order !== undefined && (typeof step.order !== 'number' || !Number.isInteger(step.order) || step.order < 1) && invalid(step.order, 'Неверный номер шага')}
      {Object.keys(step).some((key) => !['order', 'instruction', 'expected_result', 'confirmation_required'].includes(key)) && invalid(step, 'Шаг содержит поля вне контракта')}
    </>}
  </li>)}</ol>;
}
function rollback(value: unknown): ReactNode {
  if (!isObject(value)) return invalid(value, 'Обязательный план отката не указан или имеет неверный формат');
  return <div className={styles.rollback}>
    {value.mode === 'steps' ? <><p>Выполнить действия отката:</p>{strings(value.steps, true)}</>
      : value.mode === 'not_applicable' ? <><Badge tone="neutral">Откат не применим</Badge>{typeof value.reason === 'string' && value.reason ? <p>{value.reason}</p> : invalid(value.reason, 'Обязательная причина не указана')}</>
      : invalid(value.mode, 'Неизвестный режим отката')}
    {value.mode !== 'not_applicable' && present(value.reason) && <div><strong>Причина</strong>{typeof value.reason === 'string' ? <p>{value.reason}</p> : invalid(value.reason)}</div>}
    {value.mode === 'not_applicable' && present(value.steps) && <div><strong>Дополнительные действия</strong>{strings(value.steps)}</div>}
    {Object.keys(value).some((key) => !['mode', 'steps', 'reason'].includes(key)) && invalid(value, 'План отката содержит поля вне контракта')}
  </div>;
}
function fieldValue(field: Field, value: unknown): ReactNode {
  if (field.kind === 'text' && !field.required && !present(value)) return <span className={styles.empty}>Не указано</span>;
  if (field.kind === 'steps') return steps(value);
  if (field.kind === 'rollback') return rollback(value);
  if (field.kind === 'list') return strings(value, field.required);
  if (field.kind === 'effect') return typeof value === 'string' && effects[value]
    ? <Badge tone={value === 'forbid' ? 'danger' : value === 'require' ? 'warn' : 'info'}>{effects[value]}</Badge> : invalid(value, 'Действие правила не указано или имеет неверный формат');
  return typeof value === 'string' && value ? value : invalid(value, 'Обязательный текст не заполнен или имеет неверный формат');
}
/** A bounded textual overview of the same canonical fields shown in the content tab. */
export function memoryContentPreview(type: string, content: Record<string, unknown>): string {
  const lines: string[] = [];
  const append = (label: string, value: unknown) => {
    if (!present(value)) return;
    if (typeof value === 'string') lines.push(`${label}: ${effects[value] ?? value}`);
    else if (Array.isArray(value)) {
      lines.push(`${label}:`);
      value.forEach((item, index) => {
        if (typeof item === 'string') lines.push(`• ${item}`);
        else if (isObject(item)) {
          lines.push(`${item.order ?? index + 1}. ${String(item.instruction ?? '')}`);
          if (present(item.expected_result)) lines.push(`Ожидаемый результат: ${String(item.expected_result)}`);
          lines.push(`Подтверждение: ${item.confirmation_required ? 'требуется' : 'не требуется'}`);
        }
      });
    } else if (isObject(value)) {
      lines.push(`${label}:`);
      Object.entries(value).forEach(([key, item]) => append(contentFieldLabels[key] ?? key, item));
    } else lines.push(`${label}: ${String(value)}`);
  };
  (schemas[type] ?? Object.keys(content).map(text)).forEach(({ key }) => append(contentFieldLabels[key] ?? key, content[key]));
  const allLines = lines.join('\n').split('\n');
  return allLines.slice(0, 24).join('\n') + (allLines.length > 24 ? '\n…' : '');
}
export function MemoryContentViewToggle({ jsonMode, onChange }: { jsonMode: boolean; onChange: (value: boolean) => void }) {
  return <Toggle checked={jsonMode} onChange={onChange} size="small" label="JSON" />;
}
export default function MemoryContentView({ type, content, error, jsonMode = false }: { type: string; content: Record<string, unknown>; error?: string | null; jsonMode?: boolean }) {
  const fields = schemas[type];
  const extras = Object.keys(content).filter((key) => !fields?.some((field) => field.key === key));
  return <div className={styles.content}>
    {error && <p role="alert" className={styles.invalid}>{error.replace(/\b[a-z_]+\b/g, (key) => contentFieldLabels[key] ?? key)}</p>}
    {jsonMode ? <pre className={styles.json}>{JSON.stringify(content, null, 2)}</pre>
      : fields ? <dl className={styles.fields}>{fields.filter((field) => field.required || present(content[field.key])).map((field) => <div key={field.key}>
      <dt>{contentFieldLabels[field.key]}</dt><dd>{fieldValue(field, content[field.key])}</dd>
    </div>)}</dl> : <p>Неизвестный тип знания: {type || 'не указан'}. Проверьте исходное содержание.</p>}
    {!jsonMode && extras.length > 0 && <section className={styles['extra-fields']}><h3>Дополнительные поля</h3>{extras.map((key) => <p key={key}><strong>{contentFieldLabels[key] ?? key}</strong>: {typeof content[key] === 'string' ? content[key] : JSON.stringify(content[key])}</p>)}</section>}
  </div>;
}
