import { Badge } from '@/shared/ui';
import type { CollectionField } from '@/shared/api';
import type { DataTableColumn } from '@/shared/ui/DataTable/DataTable';
import styles from './fieldColumns.module.css';

export const collectionFieldColumns: DataTableColumn<CollectionField>[] = [
  { key: 'name', label: 'Название', render: (f) => <code>{f.name}</code> },
  {
    key: 'type',
    label: 'Тип',
    render: (f) => <Badge tone="neutral">{f.type}</Badge>,
  },
  {
    key: 'required',
    label: 'Обязательное',
    render: (f) => f.required ? <Badge tone="warn">Да</Badge> : <Badge tone="neutral">Нет</Badge>,
  },
  {
    key: 'search_modes',
    label: 'Поиск',
    render: (f) => (
      <span className={styles.searchModes}>
        {f.search_modes.map((m) => <Badge key={m} tone="info">{m}</Badge>)}
      </span>
    ),
  },
  { key: 'description', label: 'Описание', render: (f) => f.description || '—' },
];
