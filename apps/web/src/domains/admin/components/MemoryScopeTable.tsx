import { Badge, type DataTableColumn } from '@/shared/ui';
import type { MemoryScopeAdminItem, MemoryScopeProposalAdminItem } from '@/shared/api/admin';
import MemoryActionsMenu from './MemoryActionsMenu';
import styles from './MemoryReviewTable.module.css';

export const scopeTypeLabels: Record<string, string> = { project: 'Проект', team: 'Команда' };
export const scopeStatusLabels: Record<string, string> = { active: 'Активен', deprecated: 'Удалён', awaiting_term: 'Ожидает термин', needs_review: 'На проверке', approved: 'Утверждён', rejected: 'Отклонён' };

type ScopeRowBase = { id: string; scope_type: string; key: string; name: string; aliases: string[]; status: string };
export type ScopeTableRow = ScopeRowBase & (
  { kind: 'published'; scope: MemoryScopeAdminItem } |
  { kind: 'proposal'; proposal: MemoryScopeProposalAdminItem }
);
type Actions = {
  onReview: (proposal: MemoryScopeProposalAdminItem) => void;
  onEdit: (scope: MemoryScopeAdminItem) => void;
  onLifecycle: (scope: MemoryScopeAdminItem, action: 'delete' | 'restore') => void;
};

export const scopeColumns = ({ onReview, onEdit, onLifecycle }: Actions): DataTableColumn<ScopeTableRow>[] => [
  { key: 'scope_type', label: 'ТИП', width: 150, sortable: true, filter: { kind: 'select', placeholder: 'Все типы', options: Object.entries(scopeTypeLabels).map(([value, label]) => ({ value, label })) }, render: (row) => <Badge tone="info">{scopeTypeLabels[row.scope_type] ?? row.scope_type}</Badge> },
  { key: 'name', label: 'НАЗВАНИЕ', sortable: true, filter: { kind: 'text', placeholder: 'Название' }, render: (row) => <div><strong>{row.name}</strong>{row.kind === 'published' && row.scope.project_type && <div className={styles.preview}>{row.scope.project_type}</div>}{row.kind === 'published' && row.scope.is_all && <div className={styles.preview}>Все области этого типа</div>}</div> },
  { key: 'key', label: 'КЛЮЧ', sortable: true, filter: { kind: 'text', placeholder: 'Ключ' }, render: (row) => <code>{row.key}</code> },
  { key: 'aliases', label: 'АЛИАСЫ', filter: { kind: 'text', placeholder: 'Алиас', getValue: (row) => row.aliases.join(' ') }, render: (row) => row.aliases.join(', ') || '—' },
  { key: 'term', label: 'ТЕРМИН', filter: { kind: 'text', placeholder: 'Термин', getValue: (row) => row.kind === 'proposal' ? row.proposal.term_name : '' }, render: (row) => row.kind === 'proposal' ? row.proposal.term_name || '—' : '—' },
  { key: 'status', label: 'СТАТУС', width: 240, filter: { kind: 'select', placeholder: 'Все статусы', options: ['active', 'deprecated', 'awaiting_term', 'needs_review'].map((value) => ({ value, label: scopeStatusLabels[value] })) }, render: (row) => <div><Badge tone={row.status === 'active' ? 'success' : 'warn'}>{scopeStatusLabels[row.status] ?? row.status}</Badge>{row.kind === 'proposal' ? row.proposal.approval_blockers.map((reason) => <div key={reason} className={styles.blocker}>{reason}</div>) : row.status === 'deprecated' && <div className={styles.preview}>Удалится через {row.scope.retention_days} дн.</div>}</div> },
  { key: 'actions', label: '', width: 80, render: (row) => <MemoryActionsMenu label="⋯" ariaLabel={`Действия со скоупом ${row.name}`} items={row.kind === 'proposal' ? [
    { label: 'Проверить', onClick: () => onReview(row.proposal) },
  ] : row.scope.lifecycle_status === 'active' ? [
    { label: 'Изменить', onClick: () => onEdit(row.scope) },
    { label: 'Удалить', variant: 'danger', onClick: () => onLifecycle(row.scope, 'delete') },
  ] : [{ label: 'Восстановить', onClick: () => onLifecycle(row.scope, 'restore') }]} /> },
];
