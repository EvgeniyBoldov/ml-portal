import React from 'react';
import DataTable, { type DataTableColumn } from './DataTable/DataTable';
import Button from './Button';
import Badge from './Badge';

interface ServerDataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  keyField: string;
  loading?: boolean;
  emptyText?: string;
  selectable?: boolean;
  selectedKeys?: Set<string | number>;
  onSelectionChange?: (keys: Set<string | number>) => void;
  onRowClick?: (row: T, index: number) => void;
  totalItems: number;
  currentPage: number;
  totalPages: number;
  onPrevPage: () => void;
  onNextPage: () => void;
  headerContent?: React.ReactNode;
}

export default function ServerDataTable<T>({
  columns,
  data,
  keyField,
  loading = false,
  emptyText = 'Нет данных',
  selectable = false,
  selectedKeys,
  onSelectionChange,
  onRowClick,
  totalItems,
  currentPage,
  totalPages,
  onPrevPage,
  onNextPage,
  headerContent,
}: ServerDataTableProps<T>) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {headerContent}
      <DataTable<T>
        columns={columns}
        data={data}
        keyField={keyField}
        loading={loading}
        emptyText={emptyText}
        selectable={selectable}
        selectedKeys={selectedKeys}
        onSelectionChange={onSelectionChange}
        onRowClick={onRowClick}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
          Показано {data.length} из {totalItems}
        </span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <Button variant="outline" onClick={onPrevPage} disabled={currentPage <= 1}>
            Назад
          </Button>
          <Badge tone="neutral">
            {currentPage} / {totalPages}
          </Badge>
          <Button variant="outline" onClick={onNextPage} disabled={currentPage >= totalPages}>
            Вперед
          </Button>
        </div>
      </div>
    </div>
  );
}
