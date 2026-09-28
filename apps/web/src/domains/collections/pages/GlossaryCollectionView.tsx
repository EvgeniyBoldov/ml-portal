import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import {
  collectionsApi,
  type GlossaryCatalogTerm,
} from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';
import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  Icon,
  Input,
  Skeleton,
  type DataTableColumn,
} from '@/shared/ui';
import styles from './GlossaryCollectionView.module.css';

const GLOSSARY_COLUMNS: DataTableColumn<GlossaryCatalogTerm>[] = [
  {
    key: 'canonical_term',
    label: 'ТЕРМИН',
    width: 220,
    sortable: true,
    render: (entry) => <strong>{entry.canonical_term}</strong>,
  },
  {
    key: 'aliases',
    label: 'АЛИАСЫ',
    width: 280,
    render: (entry) => entry.aliases.length > 0
      ? <div className={styles.aliases}>{entry.aliases.map((alias) => <Badge key={alias} tone="info">{alias}</Badge>)}</div>
      : <span className={styles.muted}>—</span>,
  },
  {
    key: 'description',
    label: 'ОПРЕДЕЛЕНИЕ',
    render: (entry) => <span className={styles.description}>{entry.description}</span>,
  },
  {
    key: 'source_document_title',
    label: 'ДОКУМЕНТ',
    render: (entry) => entry.source_document_title,
  },
];

export default function GlossaryCollectionView() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const glossaryQuery = useQuery({
    queryKey: qk.collections.glossaryOverview({ query, page, pageSize }),
    queryFn: () => collectionsApi.getGlossaryOverview({ query: query || undefined, limit: pageSize, offset: (page - 1) * pageSize }),
  });

  if (glossaryQuery.isLoading) {
    return <div className={styles.loading}><Skeleton width={720} height={260} /></div>;
  }

  if (glossaryQuery.isError) {
    return (
      <EmptyState
        title="Не удалось загрузить глоссарий"
        description="Попробуйте обновить страницу позже."
      />
    );
  }

  const entries = glossaryQuery.data?.entries ?? [];
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <Button
            variant="outline"
            aria-label="Вернуться к коллекциям"
            onClick={() => navigate('/gpt/collections')}
          >
            <Icon name="chevron-left" size={18} />
          </Button>
          <div>
            <h1>Глоссарий</h1>
            <p>Утверждённые определения из корпоративных документов.</p>
          </div>
        </div>
      </header>

      <main className={styles.content}>
        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
          <Input aria-label="Поиск по глоссарию" placeholder="Поиск термина, алиаса или определения" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} />
        </div>
        {entries.length === 0 && !glossaryQuery.data?.total ? (
          <EmptyState
            title="В глоссарии пока нет терминов"
            description="Термины появятся здесь после утверждения определения из документа."
          />
        ) : (
          <DataTable
            columns={GLOSSARY_COLUMNS}
            data={entries}
            keyField="canonical_term"
            emptyText="Термины не найдены"
            paginated
            serverPaginated
            currentPage={page}
            pageSize={pageSize}
            totalItems={glossaryQuery.data?.total ?? 0}
            onPageChange={setPage}
          />
        )}
      </main>
    </div>
  );
}
