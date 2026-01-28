/**
 * AdminTable - Unified table component for admin pages
 * 
 * Features:
 * - Sortable columns
 * - Pagination
 * - Loading state with skeletons
 * - Empty state
 * - Row click handler
 * - Actions column support
 */
import React, { useState, useMemo, useCallback } from 'react';
import { Skeleton } from '../Skeleton';
import Button from '../Button';
import styles from './AdminTable.module.css';

export type SortDirection = 'asc' | 'desc' | null;

export interface AdminTableColumn<T = any> {
  /** Unique key for the column */
  key: string;
  /** Column header label */
  label: string;
  /** Column width (CSS value) */
  width?: number | string;
  /** Text alignment */
  align?: 'left' | 'center' | 'right';
  /** Whether column is sortable */
  sortable?: boolean;
  /** Custom render function */
  render?: (row: T, index: number) => React.ReactNode;
  /** Sort compare function (for custom sorting) */
  sortFn?: (a: T, b: T) => number;
}

export interface AdminTableProps<T = any> {
  /** Table columns configuration */
  columns: AdminTableColumn<T>[];
  /** Table data */
  data: T[];
  /** Unique key field in data */
  keyField?: string;
  /** Loading state */
  loading?: boolean;
  /** Empty state text */
  emptyText?: string;
  /** Row click handler */
  onRowClick?: (row: T) => void;
  
  // Pagination
  /** Enable pagination */
  paginated?: boolean;
  /** Items per page */
  pageSize?: number;
  /** Page size options */
  pageSizeOptions?: number[];
  /** Total items (for server-side pagination) */
  totalItems?: number;
  /** Current page (1-indexed, for controlled pagination) */
  currentPage?: number;
  /** Page change handler (for controlled pagination) */
  onPageChange?: (page: number) => void;
  /** Page size change handler */
  onPageSizeChange?: (size: number) => void;
  
  // Sorting
  /** Default sort column */
  defaultSortKey?: string;
  /** Default sort direction */
  defaultSortDirection?: SortDirection;
  /** Sort change handler (for controlled sorting) */
  onSortChange?: (key: string, direction: SortDirection) => void;
}

export function AdminTable<T extends Record<string, any>>({
  columns,
  data,
  keyField = 'id',
  loading = false,
  emptyText = 'Нет данных',
  onRowClick,
  paginated = false,
  pageSize: initialPageSize = 20,
  pageSizeOptions = [10, 20, 50, 100],
  totalItems,
  currentPage: controlledPage,
  onPageChange,
  onPageSizeChange,
  defaultSortKey,
  defaultSortDirection = 'asc',
  onSortChange,
}: AdminTableProps<T>) {
  // Local state for uncontrolled mode
  const [localPage, setLocalPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [sortKey, setSortKey] = useState<string | null>(defaultSortKey || null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(defaultSortKey ? defaultSortDirection : null);

  // Use controlled or local page
  const currentPage = controlledPage ?? localPage;

  // Handle sort
  const handleSort = useCallback((key: string) => {
    const column = columns.find(c => c.key === key);
    if (!column?.sortable) return;

    let newDirection: SortDirection;
    if (sortKey !== key) {
      newDirection = 'asc';
    } else if (sortDirection === 'asc') {
      newDirection = 'desc';
    } else {
      newDirection = null;
    }

    setSortKey(newDirection ? key : null);
    setSortDirection(newDirection);
    onSortChange?.(key, newDirection);
  }, [columns, sortKey, sortDirection, onSortChange]);

  // Sort data
  const sortedData = useMemo(() => {
    if (!sortKey || !sortDirection) return data;

    const column = columns.find(c => c.key === sortKey);
    if (!column) return data;

    return [...data].sort((a, b) => {
      let result: number;
      
      if (column.sortFn) {
        result = column.sortFn(a, b);
      } else {
        const aVal = a[sortKey];
        const bVal = b[sortKey];
        
        if (aVal === bVal) return 0;
        if (aVal === null || aVal === undefined) return 1;
        if (bVal === null || bVal === undefined) return -1;
        
        if (typeof aVal === 'string' && typeof bVal === 'string') {
          result = aVal.localeCompare(bVal, 'ru');
        } else {
          result = aVal < bVal ? -1 : 1;
        }
      }

      return sortDirection === 'desc' ? -result : result;
    });
  }, [data, sortKey, sortDirection, columns]);

  // Paginate data
  const paginatedData = useMemo(() => {
    if (!paginated || totalItems !== undefined) return sortedData; // Server-side pagination
    
    const start = (currentPage - 1) * pageSize;
    return sortedData.slice(start, start + pageSize);
  }, [sortedData, paginated, currentPage, pageSize, totalItems]);

  // Calculate total pages
  const total = totalItems ?? data.length;
  const totalPages = Math.ceil(total / pageSize);

  // Handle page change
  const handlePageChange = useCallback((page: number) => {
    if (page < 1 || page > totalPages) return;
    setLocalPage(page);
    onPageChange?.(page);
  }, [totalPages, onPageChange]);

  // Handle page size change
  const handlePageSizeChange = useCallback((newSize: number) => {
    setPageSize(newSize);
    setLocalPage(1);
    onPageSizeChange?.(newSize);
  }, [onPageSizeChange]);

  // Render sort indicator
  const renderSortIndicator = (key: string) => {
    if (sortKey !== key) return <span className={styles.sortIcon}>↕</span>;
    return (
      <span className={styles.sortIconActive}>
        {sortDirection === 'asc' ? '↑' : '↓'}
      </span>
    );
  };

  return (
    <div className={styles.wrapper}>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              {columns.map(col => (
                <th
                  key={col.key}
                  style={{ 
                    width: col.width, 
                    textAlign: col.align || 'left',
                  }}
                  className={col.sortable ? styles.sortable : undefined}
                  onClick={col.sortable ? () => handleSort(col.key) : undefined}
                >
                  <span className={styles.thContent}>
                    {col.label}
                    {col.sortable && renderSortIndicator(col.key)}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              // Loading skeleton
              Array.from({ length: Math.min(pageSize, 5) }).map((_, i) => (
                <tr key={`skeleton-${i}`}>
                  {columns.map((col, j) => (
                    <td key={col.key}>
                      <Skeleton width={j === 0 ? 180 : 100} />
                    </td>
                  ))}
                </tr>
              ))
            ) : paginatedData.length === 0 ? (
              // Empty state
              <tr>
                <td colSpan={columns.length} className={styles.emptyState}>
                  {emptyText}
                </td>
              </tr>
            ) : (
              // Data rows
              paginatedData.map((row, index) => (
                <tr
                  key={row[keyField] ?? index}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={onRowClick ? styles.clickable : undefined}
                >
                  {columns.map(col => (
                    <td
                      key={col.key}
                      style={{ textAlign: col.align || 'left' }}
                    >
                      {col.render ? col.render(row, index) : row[col.key]}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {paginated && totalPages > 1 && (
        <div className={styles.pagination}>
          <div className={styles.paginationInfo}>
            Показано {((currentPage - 1) * pageSize) + 1}–{Math.min(currentPage * pageSize, total)} из {total}
          </div>
          
          <div className={styles.paginationControls}>
            <Button
              variant="outline"
              size="small"
              disabled={currentPage === 1}
              onClick={() => handlePageChange(1)}
            >
              «
            </Button>
            <Button
              variant="outline"
              size="small"
              disabled={currentPage === 1}
              onClick={() => handlePageChange(currentPage - 1)}
            >
              ‹
            </Button>
            
            <span className={styles.pageInfo}>
              {currentPage} / {totalPages}
            </span>
            
            <Button
              variant="outline"
              size="small"
              disabled={currentPage === totalPages}
              onClick={() => handlePageChange(currentPage + 1)}
            >
              ›
            </Button>
            <Button
              variant="outline"
              size="small"
              disabled={currentPage === totalPages}
              onClick={() => handlePageChange(totalPages)}
            >
              »
            </Button>
          </div>

          <div className={styles.pageSizeSelector}>
            <select
              value={pageSize}
              onChange={e => handlePageSizeChange(Number(e.target.value))}
              className={styles.pageSizeSelect}
            >
              {pageSizeOptions.map(size => (
                <option key={size} value={size}>
                  {size} / стр.
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminTable;
