import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Badge, DataTable, EntityPageV2, Tab, type DataTableColumn } from '@/shared/ui';
import { Block } from '@/shared/ui/GridLayout';
import { adminApi, type LongMemoryTriplePage } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import styles from './LongMemoryDocumentPage.module.css';

const statusLabel: Record<string, string> = {
  pending: 'В очереди', queued: 'В очереди', running: 'Обработка', completed: 'Готово',
  failed: 'Ошибка', cancelled: 'Отменено', deleted: 'Удалён из LongMemory', not_registered: 'Нет операции', not_started: 'Не запускался',
};

const statusTone = (status: string): 'success' | 'warn' | 'danger' | 'neutral' => {
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'pending' || status === 'queued' || status === 'running') return 'warn';
  return 'neutral';
};

const metricLabels: Array<[string, string]> = [
  ['passages', 'Фрагменты'], ['processed_passages', 'Обработано фрагментов'], ['entities', 'Сущности'],
  ['facts', 'Уникальные факты'], ['extracted_triples', 'Триплеты'], ['encoded_texts', 'Закодированные тексты'],
];

const TRIPLES_PAGE_SIZE = 50;

const tripleColumns: DataTableColumn<LongMemoryTriplePage['items'][number]>[] = [
  { key: 'subject', label: 'СУБЪЕКТ', sortable: true, className: styles.tripleCell, render: (row) => <strong>{row.subject}</strong> },
  { key: 'predicate', label: 'СВЯЗЬ', sortable: true, className: styles.tripleCell },
  { key: 'object', label: 'ОБЪЕКТ', sortable: true, className: styles.tripleCell },
  { key: 'source', label: 'ПОЗИЦИЯ В ИСТОЧНИКЕ', width: 180, render: (row) => row.source_start !== null && row.source_end !== null ? `${row.source_start}–${row.source_end}` : '—' },
];

export default function LongMemoryDocumentPage() {
  const { documentId = '' } = useParams();
  const [triplesPage, setTriplesPage] = useState(1);
  const document = useQuery({ queryKey: qk.admin.memory.longMemoryDocument(documentId), queryFn: () => adminApi.getLongMemoryDocument(documentId), enabled: Boolean(documentId) });
  const item = document.data;
  const triples = useQuery({
    queryKey: qk.admin.memory.longMemoryDocumentTriples(documentId, (triplesPage - 1) * TRIPLES_PAGE_SIZE),
    queryFn: () => adminApi.getLongMemoryDocumentTriples(documentId, { limit: TRIPLES_PAGE_SIZE, offset: (triplesPage - 1) * TRIPLES_PAGE_SIZE }),
    enabled: Boolean(item && item.triples_count > 0),
  });

  return <EntityPageV2 title={item?.title || 'Документ LongMemory'} subtitle={item?.filename} mode="view" loading={document.isLoading}
    breadcrumbs={[{ label: 'LongMemory', href: '/admin/memory?tab=long-memory' }, { label: item?.title || 'Документ' }]}
    backPath="/admin/memory?tab=long-memory">
    <Tab title="Обзор" id="summary" layout="grid">
      {document.isError ? <p role="alert">Не удалось загрузить документ LongMemory.</p> : item && <>
        <Block title="Инфо" icon="file" iconVariant="info" width="1/2"
          headerActions={<Badge tone={statusTone(item.status)}>{statusLabel[item.status] ?? item.status}</Badge>}>
          <div className={styles.infoList}>
            <div><span>Файл</span><strong>{item.filename}</strong></div>
            <div><span>Scope</span><strong>{item.scope_keys.length ? item.scope_keys.join(', ') : 'Не назначен'}</strong></div>
            <div><span>Последнее обновление</span><strong>{item.updated_at ? new Date(item.updated_at).toLocaleString('ru-RU') : '—'}</strong></div>
            {item.error && <p className={styles.error}>{item.error}</p>}
          </div>
        </Block>

        <Block title="Извлечённая память" icon="sparkles" iconVariant="primary" width="1/2">
          <dl className={styles.metricsList}>{metricLabels.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{item.metrics[key] ?? '—'}</dd></div>)}</dl>
        </Block>

        <Block title="Триплеты" icon="database" iconVariant="warning" width="full"
          headerLabels={<span className={styles.triplesCount}>{triples.data?.total ?? item.triples_count}</span>}>
          {item.triples_count === 0 ? <p className={styles.muted}>Для этого документа триплеты не извлечены.</p> : triples.isError ? <p className={styles.error} role="alert">Не удалось загрузить триплеты документа.</p> : <DataTable
            columns={tripleColumns}
            data={triples.data?.items ?? []}
            keyField="id"
            loading={triples.isLoading}
            emptyText="Триплеты не найдены"
            paginated
            serverPaginated
            pageSize={TRIPLES_PAGE_SIZE}
            pageSizeOptions={[TRIPLES_PAGE_SIZE]}
            currentPage={triplesPage}
            totalItems={triples.data?.total ?? item.triples_count}
            onPageChange={setTriplesPage}
          />}
        </Block>
      </>}
    </Tab>
  </EntityPageV2>;
}
