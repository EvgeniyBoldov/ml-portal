import React, { useState } from 'react';
import { DataTable, type DataTableProps } from '@/shared/ui';
import styles from './DashboardTables.module.css';

type Props<T> = Omit<
  DataTableProps<T>,
  'pageSize' | 'onPageSizeChange' | 'pageSizeOptions' | 'paginated'
>;

export function DashboardTable<T>(props: Props<T>) {
  const [pageSize, setPageSize] = useState(5);
  return (
    <DataTable
      {...props}
      className={[styles['overview-table'], props.className]
        .filter(Boolean)
        .join(' ')}
      paginated
      pageSize={pageSize}
      onPageSizeChange={setPageSize}
      pageSizeOptions={[5, 10, 25]}
    />
  );
}
