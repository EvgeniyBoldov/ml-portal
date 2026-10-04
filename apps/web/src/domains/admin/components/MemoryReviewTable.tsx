import { Badge, type DataTableColumn } from '@/shared/ui';
import type { ShadowMemoryCandidate } from '@/shared/api/admin';
import { contentFieldLabels, memoryContentPreview } from './MemoryContentView';
import styles from './MemoryReviewTable.module.css';

export const scopeLabels: Record<string, string> = { global: 'Вне проектов, без адресата', scoped: 'Выбранные области', project: 'Проект', multi_project: 'Несколько проектов', unknown: 'Не определена', glossary: 'Общий глоссарий' };
export const readinessLabels = { ready: 'Готов к утверждению', content: 'Ошибка содержания', conflict: 'Есть конфликт', dependencies: 'Ожидает зависимостей' };
export const candidateBlockers = (row: ShadowMemoryCandidate): string[] => [...new Set([
  ...(!row.content_valid ? [(row.content_error || 'Содержание не прошло проверку.').replace(/\b[a-z_]+\b/g, (field) => contentFieldLabels[field] ?? field)] : []),
  ...row.approval_blockers,
  ...(row.conflict_ids.length ? ['Сначала разрешите конфликт кандидата.'] : []),
])];
export const candidateReadiness = (row: ShadowMemoryCandidate): keyof typeof readinessLabels => !row.content_valid ? 'content' : row.conflict_ids.length ? 'conflict' : row.approval_blockers.length ? 'dependencies' : 'ready';

export const candidateTypeLabels: Record<string, string> = {
  term: 'Термин', description: 'Описание', relationship: 'Связь', rule: 'Правило',
  constraint: 'Ограничение', procedure: 'Процедура', decision: 'Решение',
};

const candidateContent = (row: ShadowMemoryCandidate): string => {
  if (row.candidate_type === 'term') return typeof row.content.definition === 'string' ? row.content.definition : 'Определение не указано';
  const preview = memoryContentPreview(row.candidate_type, row.content).split('\n').slice(0, 4).join(' · ');
  return preview.length > 300 ? `${preview.slice(0, 299)}…` : preview || 'Содержание не извлечено';
};

const candidateConfidence = (value: number): string => {
  if (!Number.isFinite(value) || value < 0 || value > 1) return '—';
  return `${Math.round(value * 100)}%${value >= 1 ? ' · максимум модели' : ''}`;
};

export const reviewColumns: DataTableColumn<ShadowMemoryCandidate>[] = [
  { key: 'subject', label: 'КАНДИДАТ', width: '14%', sortable: true, filter: { kind: 'text', placeholder: 'Название кандидата' }, className: styles.candidate, render: (row) => <strong>{row.subject}</strong> },
  { key: 'content', label: 'ЗНАЧЕНИЕ', width: '28%', filter: { kind: 'text', placeholder: 'Содержание', getValue: candidateContent }, className: styles.value, render: (row) => <div className={styles.preview}>{candidateContent(row)}</div> },
  { key: 'candidate_type', label: 'ТИП', width: '10%', sortable: true, filter: { kind: 'select', placeholder: 'Все типы', options: Object.entries(candidateTypeLabels).map(([value, label]) => ({ value, label })) }, render: (row) => <Badge tone="neutral">{candidateTypeLabels[row.candidate_type] ?? row.candidate_type}</Badge> },
  { key: 'readiness', label: 'УТВЕРЖДЕНИЕ', width: '16%',
    filter: { kind: 'select', placeholder: 'Все кандидаты', options: [{ value: 'ready', label: 'Готов к утверждению' }, { value: 'content', label: 'Ошибка содержания' }, { value: 'conflict', label: 'Есть конфликт' }, { value: 'dependencies', label: 'Ожидает зависимостей' }], getValue: candidateReadiness },
    render: (row) => <Badge tone={candidateReadiness(row) === 'ready' ? 'success' : 'warn'}>{readinessLabels[candidateReadiness(row)]}</Badge> },
  { key: 'scope_candidate', label: 'ОБЛАСТЬ', width: '12%', sortable: true, filter: { kind: 'select', placeholder: 'Все области', options: Object.entries(scopeLabels).map(([value, label]) => ({ value, label })), getValue: (row) => row.candidate_type === 'term' ? 'glossary' : row.scope_candidate || 'unknown' }, render: (row) => <div><Badge tone="info">{row.candidate_type === 'term' ? 'Общий глоссарий' : scopeLabels[row.scope_candidate || 'unknown'] ?? row.scope_candidate}</Badge>{row.scope_keys.length > 0 && <div className={styles.preview}>Применимость: {row.scope_keys.join(', ')}</div>}{row.scope_proposals.filter((scope) => scope.role === 'applies_to' && scope.status !== 'approved').map((scope) => <div key={scope.id} className={styles.preview}>Предложено: {scope.name}</div>)}{row.mentioned_scope_keys.length > 0 && <div className={styles.preview}>Упомянуты: {row.mentioned_scope_keys.join(', ')}</div>}{row.unmatched_scope_names.length > 0 && <div className={styles.preview}>Нет в каталоге: {row.unmatched_scope_names.join(', ')}</div>}</div> },
  { key: 'document_title', label: 'ИСТОЧНИК', width: '12%', sortable: true, filter: { kind: 'text', placeholder: 'Документ' }, render: (row) => <div>{row.document_title || 'Документ'}<div className={styles.preview}>Фрагментов: {row.evidence_section_ids.length}</div></div> },
  { key: 'extraction_confidence', label: 'ОЦЕНКА', width: '8%', align: 'right', sortable: true, filter: { kind: 'select', placeholder: 'Любая', options: [{ value: 'high', label: '≥ 80%' }, { value: 'medium', label: '50–79%' }, { value: 'low', label: '< 50%' }], getValue: (row) => row.extraction_confidence >= 0.8 ? 'high' : row.extraction_confidence >= 0.5 ? 'medium' : 'low' }, render: (row) => <span title="Самооценка экстрактора, не подтверждение администратора">{candidateConfidence(row.extraction_confidence)}</span> },
];
