import DataTable, { type DataTableColumn } from '@/shared/ui/DataTable/DataTable';

const SQL_DATA_COLUMNS: DataTableColumn<Record<string, unknown>>[] = [
  {
    key: 'table_name',
    label: 'Таблица',
    render: (row) => <code>{String(row.table_name ?? '—')}</code>,
  },
  {
    key: 'schema_columns',
    label: 'Колонок в схеме',
    render: (row) => {
      const schema = row.table_schema as Record<string, unknown> | undefined;
      const props = (schema?.properties ?? {}) as Record<string, unknown>;
      return Object.keys(props).length;
    },
  },
  {
    key: 'table_schema',
    label: 'Схема',
    render: (row) => {
      const schema = row.table_schema ?? {};
      return (
        <pre style={{ margin: 0, maxHeight: 140, overflow: 'auto', fontSize: 12 }}>
          {JSON.stringify(schema, null, 2)}
        </pre>
      );
    },
  },
];

interface SqlCatalogDataTableProps {
  data: Record<string, unknown>[];
  loading?: boolean;
}

export function SqlCatalogDataTable({ data, loading = false }: SqlCatalogDataTableProps) {
  return (
    <DataTable<Record<string, unknown>>
      columns={SQL_DATA_COLUMNS}
      data={data}
      keyField="id"
      loading={loading}
      emptyText="Нет данных. Добавьте таблицы через discovery."
    />
  );
}
