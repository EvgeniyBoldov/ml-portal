import type { ReactNode } from 'react';
import styles from './MemoryReviewDialog.module.css';

export const contentFieldLabels: Record<string, string> = {
  definition: 'Определение', summary: 'Описание', details: 'Подробности', statement: 'Формулировка',
  effect: 'Действие', conditions: 'Условия', required_approvals: 'Согласования', required_checks: 'Обязательные проверки',
  exceptions: 'Исключения', consequences: 'Последствия', limits: 'Ограничения', decision: 'Решение', rationale: 'Обоснование',
  goal: 'Цель', applicability_conditions: 'Условия применимости', prechecks: 'Предварительные проверки', steps: 'Шаги',
  verification: 'Проверка результата', rollback: 'Откат', instruction: 'Действие', expected_result: 'Ожидаемый результат',
  confirmation_required: 'Требуется подтверждение', mode: 'Режим', reason: 'Причина', order: 'Порядок',
};
const valueLabels: Record<string, string> = { require: 'Обязательно', forbid: 'Запрещено', allow: 'Разрешено', steps: 'По шагам', not_applicable: 'Не применим' };
const hasValue = (value: unknown) => value !== null && value !== undefined && value !== '' && !(Array.isArray(value) && value.length === 0);
function renderValue(value: unknown): ReactNode {
  if (value === null || value === undefined || value === '') return 'Не указано';
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  if (Array.isArray(value)) return value.length ? <ol>{value.map((item, index) => <li key={index}>{renderValue(item)}</li>)}</ol> : 'Не указано';
  if (typeof value === 'object') return <dl className={styles.contentFields}>{Object.entries(value).filter(([key, item]) => key !== 'order' && hasValue(item)).map(([key, item]) => <div key={key}><dt>{contentFieldLabels[key] ?? key}</dt><dd>{renderValue(item)}</dd></div>)}</dl>;
  return typeof value === 'string' ? valueLabels[value] ?? value : String(value);
}
export default function MemoryContentView({ content }: { content: Record<string, unknown> }) {
  return Object.keys(content).length ? <>{renderValue(content)}</> : <p>Содержание не извлечено. Отклоните кандидата с причиной и повторите извлечение документа.</p>;
}
