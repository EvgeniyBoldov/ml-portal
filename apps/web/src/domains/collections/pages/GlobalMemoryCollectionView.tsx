import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Badge, DataTable, EmptyState, Input, Skeleton, type DataTableColumn } from '@/shared/ui';
import { collectionsApi, type ProjectMemoryItem } from '@/shared/api/collections';
import styles from './ProjectMemoryCollectionView.module.css';

const columns: DataTableColumn<ProjectMemoryItem>[] = [
  { key: 'subject', label: 'КЛЮЧ', width: 260, sortable: true, filter: { kind: 'text', placeholder: 'Факт', getValue: (row) => `${row.subject} ${row.value}` }, render: (row) => <code className={styles.factKey}>{row.subject}</code> },
  { key: 'value', label: 'ЗНАНИЕ', render: (row) => <span className={styles.factValue}>{row.value}</span> },
  { key: 'kind', label: 'ТИП', width: 140, filter: { kind: 'select', placeholder: 'Все типы', options: ['description', 'relationship', 'rule', 'constraint', 'procedure', 'decision'].map((value) => ({ value, label: value })), getValue: (row) => row.kind }, render: (row) => <Badge tone="neutral">{row.kind}</Badge> },
  { key: 'status', label: 'СТАТУС', width: 160, filter: { kind: 'select', placeholder: 'Все статусы', options: [{ value: 'active', label: 'Актуально' }, { value: 'uncertain', label: 'Требует проверки' }, { value: 'stale', label: 'Устарело' }], getValue: (row) => row.status }, render: (row) => <Badge tone={row.status === 'active' ? 'success' : row.status === 'uncertain' ? 'warn' : 'danger'}>{row.status === 'active' ? 'Актуально' : row.status === 'uncertain' ? 'Требует проверки' : 'Устарело'}</Badge> },
  { key: 'source_count', label: 'ИСТОЧНИКИ', width: 110, align: 'right', sortable: true },
];

export default function GlobalMemoryCollectionView() {
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const memoryQuery = useQuery({
    queryKey: ['collections', 'global-memory', 'overview', { query, page, pageSize }],
    queryFn: () => collectionsApi.getGlobalMemoryOverview({ query: query || undefined, limit: pageSize, offset: (page - 1) * pageSize }),
  });

  if (memoryQuery.isLoading) return <div className={styles.loading}><Skeleton width={520} height={240} /></div>;
  if (memoryQuery.isError) return <EmptyState title="Не удалось загрузить глобальную память" description="Попробуйте обновить страницу позже." />;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerLeft}><div><h1>Глобальная память</h1><p>Общие факты и знания организации</p></div></div>
      </header>
      <section className={styles.factsSection} style={{ margin: 'var(--sp-5) var(--sp-6)' }}>
        <div className={styles.factsHeader}>
          <h2>Факты <span>({memoryQuery.data?.total ?? 0})</span></h2>
          <Input aria-label="Поиск глобальных фактов" placeholder="Поиск по фактам" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} />
        </div>
        <DataTable columns={columns} data={memoryQuery.data?.items ?? []} keyField="id" emptyText="Глобальных фактов пока нет" paginated serverPaginated currentPage={page} pageSize={pageSize} totalItems={memoryQuery.data?.total ?? 0} onPageChange={setPage} />
      </section>
    </div>
  );
}
