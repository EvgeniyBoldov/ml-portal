import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import {
  collectionsApi,
  type GlossaryCatalogEntry,
} from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';
import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  Icon,
  Skeleton,
  type DataTableColumn,
} from '@/shared/ui';
import styles from './GlossaryCollectionView.module.css';

const GLOSSARY_COLUMNS: DataTableColumn<GlossaryCatalogEntry>[] = [
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
    label: 'ОПИСАНИЕ',
    render: (entry) => entry.description
      ? <span className={styles.description}>{entry.description}</span>
      : <span className={styles.muted}>—</span>,
  },
  {
    key: 'entity_type',
    label: 'ТИП',
    width: 150,
    render: (entry) => <Badge tone="neutral">{entry.entity_type}</Badge>,
  },
  {
    key: 'scope',
    label: 'ОБЛАСТЬ',
    width: 150,
    render: (entry) => (
      <Badge tone={entry.scope === 'global' ? 'info' : 'success'}>
        {entry.scope === 'global' ? 'Общий' : 'Текущий tenant'}
      </Badge>
    ),
  },
];

export default function GlossaryCollectionView() {
  const navigate = useNavigate();
  const glossaryQuery = useQuery({
    queryKey: qk.collections.glossaryOverview(),
    queryFn: () => collectionsApi.getGlossaryOverview(),
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
            <p>Канонические термины, сокращения и их алиасы.</p>
          </div>
        </div>
      </header>

      <main className={styles.content}>
        {entries.length === 0 ? (
          <EmptyState
            title="В глоссарии пока нет терминов"
            description="Общие и tenant-термины появятся здесь после добавления или подтверждения."
          />
        ) : (
          <DataTable
            columns={GLOSSARY_COLUMNS}
            data={entries}
            keyField="canonical_term"
            emptyText="Термины не найдены"
          />
        )}
      </main>
    </div>
  );
}
