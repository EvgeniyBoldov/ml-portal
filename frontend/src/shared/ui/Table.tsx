import React from 'react';
import styles from './Table.module.css';

export interface TableColumn<T = any> {
  key: string;
  title: string;
  dataIndex?: keyof T;
  render?: (value: any, record: T, index: number) => React.ReactNode;
  width?: string | number;
  align?: 'left' | 'center' | 'right';
  sortable?: boolean;
  className?: string;
}

export interface TableProps<T = any> {
  columns: TableColumn<T>[];
  data: T[];
  loading?: boolean;
  emptyText?: string;
  emptyIcon?: React.ReactNode;
  onRowClick?: (record: T, index: number) => void;
  onRowDoubleClick?: (record: T, index: number) => void;
  rowKey?: keyof T | ((record: T) => string);
  selectedRowKeys?: string[];
  _onSelectionChange?: (selectedKeys: string[]) => void;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
  onSort?: (column: string, order: 'asc' | 'desc') => void;
  className?: string;
  size?: 'small' | 'medium' | 'large';
  stickyHeader?: boolean;
}

export function Table<T = any>({
  columns,
  data,
  loading = false,
  emptyText = 'No data',
  emptyIcon,
  onRowClick,
  onRowDoubleClick,
  rowKey = 'id' as keyof T,
  selectedRowKeys = [],
  _onSelectionChange,
  sortBy,
  sortOrder,
  onSort,
  className = '',
  size = 'medium',
  stickyHeader = true,
}: TableProps<T>) {
  const getRowKey = (record: T, index: number): string => {
    if (typeof rowKey === 'function') {
      return rowKey(record);
    }
    return String(record[rowKey as keyof T] || index);
  };

  const handleSort = (column: string) => {
    if (!onSort) return;

    const newOrder = sortBy === column && sortOrder === 'asc' ? 'desc' : 'asc';
    onSort(column, newOrder);
  };

  const renderEmptyState = () => (
    <tr>
      <td colSpan={columns.length} className={styles.emptyState}>
        {emptyIcon && <div className={styles.emptyStateIcon}>{emptyIcon}</div>}
        <div className={styles.emptyStateTitle}>No data</div>
        <div className={styles.emptyStateDescription}>{emptyText}</div>
      </td>
    </tr>
  );

  // const _renderLoadingRow = () => (
  //   <tr>
  //     <td colSpan={columns.length} className={styles.loadingRow}>
  //       <div
  //         className={styles.skeleton}
  //         style={{ width: '200px', margin: '0 auto' }}
  //       />
  //     </td>
  //   </tr>
  // );

  const renderSkeletonRows = () => {
    return Array.from({ length: 5 }).map((_, index) => (
      <tr key={index}>
        {columns.map(column => (
          <td
            key={column.key}
            className={`${styles.tableCell} ${styles.loadingCell}`}
          >
            <div
              className={`${styles.skeleton} ${index % 3 === 0 ? styles.short : index % 3 === 1 ? styles.medium : styles.long}`}
            />
          </td>
        ))}
      </tr>
    ));
  };

  const renderHeader = () => (
    <thead className={styles.tableHeader}>
      <tr>
        {columns.map(column => (
          <th
            key={column.key}
            className={`
              ${styles.tableHeaderCell}
              ${column.sortable ? styles.sortable : ''}
              ${sortBy === column.key ? styles.active : ''}
              ${column.className || ''}
            `}
            style={{
              width: column.width,
              textAlign: column.align || 'left',
            }}
            onClick={column.sortable ? () => handleSort(column.key) : undefined}
          >
            {column.title}
            {column.sortable && sortBy === column.key && (
              <span style={{ marginLeft: '4px' }}>
                {sortOrder === 'asc' ? '↑' : '↓'}
              </span>
            )}
          </th>
        ))}
      </tr>
    </thead>
  );

  const renderBody = () => (
    <tbody className={styles.tableBody}>
      {loading
        ? renderSkeletonRows()
        : data.length === 0
          ? renderEmptyState()
          : data.map((record, index) => {
              const key = getRowKey(record, index);
              const isSelected = selectedRowKeys.includes(key);

              return (
                <tr
                  key={key}
                  className={`${styles.tableRow} ${isSelected ? styles.selected : ''}`}
                  onClick={() => onRowClick?.(record, index)}
                  onDoubleClick={() => onRowDoubleClick?.(record, index)}
                >
                  {columns.map(column => {
                    const value = column.dataIndex
                      ? record[column.dataIndex]
                      : undefined;
                    const cellContent = column.render
                      ? column.render(value, record, index)
                      : (value as React.ReactNode);

                    return (
                      <td
                        key={column.key}
                        className={`
                      ${styles.tableCell}
                      ${size === 'small' ? styles.compact : ''}
                      ${column.align === 'right' ? styles.numeric : ''}
                      ${column.key === 'actions' ? styles.actions : ''}
                      ${column.className || ''}
                    `}
                        style={{
                          textAlign: column.align || 'left',
                        }}
                      >
                        {cellContent}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
    </tbody>
  );

  return (
    <div className={`${styles.tableContainer} ${className}`}>
      <table className={styles.table}>
        {stickyHeader && renderHeader()}
        {renderBody()}
      </table>
    </div>
  );
}

export default Table;
