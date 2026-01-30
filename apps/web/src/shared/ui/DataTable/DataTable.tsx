/**
 * DataTable - Reusable table component with selection, search, pagination
 * 
 * Features:
 * - Row selection (single/multiple)
 * - Search/filter
 * - Pagination
 * - Custom cell renderers
 * - Bulk actions
 * 
 * Usage:
 * ```tsx
 * <DataTable
 *   columns={[
 *     { key: 'id', label: 'ID', width: 80 },
 *     { key: 'name', label: 'Name', render: (row) => <strong>{row.name}</strong> },
 *   ]}
 *   data={items}
 *   keyField="id"
 *   selectable
 *   onSelectionChange={(ids) => console.log(ids)}
 *   searchable
 *   searchPlaceholder="Search..."
 *   pageSize={50}
 * />
 * ```
 */
import React, { useState, useMemo, useCallback } from 'react';
import Input from '../Input';
import Button from '../Button';
import { Icon } from '../Icon';
import { TableHeader } from '../TableHeader';
import styles from './DataTable.module.css';

export interface DataTableColumn<T = any> {
  key: string;
  label: string;
  width?: number | string;
  align?: 'left' | 'center' | 'right';
  sortable?: boolean;
  render?: (row: T, index: number) => React.ReactNode;
  className?: string;
}

export interface DataTableProps<T = any> {
  columns: DataTableColumn<T>[];
  data: T[];
  keyField: string;
  
  // Selection
  selectable?: boolean;
  selectedKeys?: Set<string | number>;
  onSelectionChange?: (keys: Set<string | number>) => void;
  
  // Search
  searchable?: boolean;
  searchPlaceholder?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  searchFilter?: (row: T, query: string) => boolean;
  
  // Pagination
  paginated?: boolean;
  pageSize?: number;
  currentPage?: number;
  totalItems?: number;
  onPageChange?: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  pageSizeOptions?: number[];
  
  // Bulk actions
  bulkActions?: React.ReactNode;
  
  // Empty state
  emptyState?: React.ReactNode;
  emptyText?: string;
  
  // Loading
  loading?: boolean;
  
  // Styling
  className?: string;
  rowClassName?: (row: T, index: number) => string | undefined;
  
  // Events
  onRowClick?: (row: T, index: number) => void;
}

export default function DataTable<T = any>({
  columns,
  data,
  keyField,
  selectable = false,
  selectedKeys: controlledSelectedKeys,
  onSelectionChange,
  searchable = false,
  searchPlaceholder = 'Поиск...',
  searchValue: controlledSearchValue,
  onSearchChange,
  searchFilter,
  paginated = false,
  pageSize: controlledPageSize = 50,
  currentPage: controlledCurrentPage = 1,
  totalItems,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [25, 50, 100],
  bulkActions,
  emptyState,
  emptyText = 'Нет данных',
  loading = false,
  className,
  rowClassName,
  onRowClick,
}: DataTableProps<T>) {
  // Internal state for uncontrolled mode
  const [internalSelectedKeys, setInternalSelectedKeys] = useState<Set<string | number>>(new Set());
  const [internalSearchValue, setInternalSearchValue] = useState('');
  const [internalCurrentPage, setInternalCurrentPage] = useState(1);
  const [internalPageSize, setInternalPageSize] = useState(controlledPageSize);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // Use controlled or internal state
  const selectedKeys = controlledSelectedKeys ?? internalSelectedKeys;
  const searchValue = controlledSearchValue ?? internalSearchValue;
  const currentPage = controlledCurrentPage ?? internalCurrentPage;
  const pageSize = controlledPageSize ?? internalPageSize;

  // Handlers
  const handleSelectionChange = useCallback((keys: Set<string | number>) => {
    if (onSelectionChange) {
      onSelectionChange(keys);
    } else {
      setInternalSelectedKeys(keys);
    }
  }, [onSelectionChange]);

  const handleSearchChange = useCallback((value: string) => {
    if (onSearchChange) {
      onSearchChange(value);
    } else {
      setInternalSearchValue(value);
      setInternalCurrentPage(1);
    }
  }, [onSearchChange]);

  const handlePageChange = useCallback((page: number) => {
    if (onPageChange) {
      onPageChange(page);
    } else {
      setInternalCurrentPage(page);
    }
  }, [onPageChange]);

  const handlePageSizeChange = useCallback((size: number) => {
    if (onPageSizeChange) {
      onPageSizeChange(size);
    } else {
      setInternalPageSize(size);
      setInternalCurrentPage(1);
    }
  }, [onPageSizeChange]);

  // Handle sort
  const handleSort = useCallback((key: string) => {
    if (sortKey === key) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortOrder('asc');
    }
  }, [sortKey]);

  // Filter data
  const filteredData = useMemo(() => {
    if (!searchable || !searchValue) return data;
    
    if (searchFilter) {
      return data.filter(row => searchFilter(row, searchValue));
    }
    
    // Default search: check all string fields
    const query = searchValue.toLowerCase();
    return data.filter(row => {
      return Object.values(row as any).some(value => {
        if (typeof value === 'string') {
          return value.toLowerCase().includes(query);
        }
        if (typeof value === 'number') {
          return String(value).includes(query);
        }
        return false;
      });
    });
  }, [data, searchValue, searchable, searchFilter]);

  // Sort data
  const sortedData = useMemo(() => {
    if (!sortKey) return filteredData;
    
    return [...filteredData].sort((a, b) => {
      const aVal = (a as any)[sortKey];
      const bVal = (b as any)[sortKey];
      
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      
      let cmp = 0;
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        cmp = aVal.localeCompare(bVal);
      } else if (typeof aVal === 'number' && typeof bVal === 'number') {
        cmp = aVal - bVal;
      } else {
        cmp = String(aVal).localeCompare(String(bVal));
      }
      
      return sortOrder === 'asc' ? cmp : -cmp;
    });
  }, [filteredData, sortKey, sortOrder]);

  // Paginate data
  const paginatedData = useMemo(() => {
    if (!paginated) return sortedData;
    const start = (currentPage - 1) * pageSize;
    return sortedData.slice(start, start + pageSize);
  }, [sortedData, paginated, currentPage, pageSize]);

  const total = totalItems ?? filteredData.length;
  const totalPages = Math.ceil(total / pageSize);
  const offset = (currentPage - 1) * pageSize;

  // Selection handlers
  const handleSelectAll = useCallback(() => {
    const currentPageKeys = new Set(
      paginatedData.map(row => (row as any)[keyField])
    );
    
    // Check if all current page items are selected
    const allSelected = paginatedData.every(row => 
      selectedKeys.has((row as any)[keyField])
    );
    
    if (allSelected) {
      // Deselect all from current page
      const newKeys = new Set(selectedKeys);
      currentPageKeys.forEach(key => newKeys.delete(key));
      handleSelectionChange(newKeys);
    } else {
      // Select all from current page
      const newKeys = new Set(selectedKeys);
      currentPageKeys.forEach(key => newKeys.add(key));
      handleSelectionChange(newKeys);
    }
  }, [paginatedData, selectedKeys, keyField, handleSelectionChange]);

  const handleSelectRow = useCallback((key: string | number) => {
    const newKeys = new Set(selectedKeys);
    if (newKeys.has(key)) {
      newKeys.delete(key);
    } else {
      newKeys.add(key);
    }
    handleSelectionChange(newKeys);
  }, [selectedKeys, handleSelectionChange]);

  // Check if all current page items are selected
  const allCurrentPageSelected = paginatedData.length > 0 && paginatedData.every(row =>
    selectedKeys.has((row as any)[keyField])
  );

  const someCurrentPageSelected = paginatedData.some(row =>
    selectedKeys.has((row as any)[keyField])
  );

  return (
    <div className={`${styles.container} ${className || ''}`}>
      {/* Toolbar */}
      {(searchable || selectable) && (
        <div className={styles.toolbar}>
          <div className={styles.toolbarLeft}>
            {selectable && (
              <>
                <label className={styles.selectAll}>
                  <input
                    type="checkbox"
                    checked={allCurrentPageSelected}
                    ref={input => {
                      if (input) {
                        input.indeterminate = someCurrentPageSelected && !allCurrentPageSelected;
                      }
                    }}
                    onChange={handleSelectAll}
                  />
                  Выбрать все
                </label>
                {selectedKeys.size > 0 && (
                  <>
                    <span className={styles.selectedCount}>
                      Выбрано: {selectedKeys.size}
                    </span>
                    {bulkActions && (
                      <div className={styles.bulkActions}>{bulkActions}</div>
                    )}
                  </>
                )}
              </>
            )}
          </div>
          <div className={styles.toolbarRight}>
            {searchable && (
              <Input
                placeholder={searchPlaceholder}
                value={searchValue}
                onChange={e => handleSearchChange(e.target.value)}
                className={styles.search}
              />
            )}
          </div>
        </div>
      )}

      {/* Table */}
      <div className={styles.tableWrapper}>
        {loading ? (
          <div className={styles.loading}>Загрузка...</div>
        ) : paginatedData.length === 0 ? (
          <div className={styles.empty}>
            {emptyState || (
              <>
                <Icon name="inbox" size={48} />
                <p>{searchValue ? 'Ничего не найдено' : emptyText}</p>
              </>
            )}
          </div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                {selectable && (
                  <th className={styles.checkboxCol}>
                    <input
                      type="checkbox"
                      checked={allCurrentPageSelected}
                      ref={input => {
                        if (input) {
                          input.indeterminate = someCurrentPageSelected && !allCurrentPageSelected;
                        }
                      }}
                      onChange={handleSelectAll}
                    />
                  </th>
                )}
                {columns.map(col => (
                  <TableHeader
                    key={col.key}
                    label={col.label}
                    width={col.width}
                    align={col.align}
                    sortable={col.sortable}
                    sortActive={sortKey === col.key}
                    sortOrder={sortKey === col.key ? sortOrder : undefined}
                    onSort={col.sortable ? () => handleSort(col.key) : undefined}
                    className={col.className}
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {paginatedData.map((row, index) => {
                const rowKey = (row as any)[keyField];
                const isSelected = selectedKeys.has(rowKey);
                const customRowClass = rowClassName?.(row, index);
                
                return (
                  <tr
                    key={rowKey}
                    className={`${isSelected ? styles.selected : ''} ${customRowClass || ''}`}
                    onClick={() => onRowClick?.(row, index)}
                  >
                    {selectable && (
                      <td className={styles.checkboxCol}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={e => {
                            e.stopPropagation();
                            handleSelectRow(rowKey);
                          }}
                          onClick={e => e.stopPropagation()}
                        />
                      </td>
                    )}
                    {columns.map(col => (
                      <td
                        key={col.key}
                        style={{ textAlign: col.align || 'left' }}
                        className={col.className}
                      >
                        {col.render
                          ? col.render(row, index)
                          : String((row as any)[col.key] ?? '—')}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {paginated && total > 0 && (
        <div className={styles.pagination}>
          <div className={styles.paginationInfo}>
            Показано {offset + 1}–{Math.min(offset + pageSize, total)} из{' '}
            {total.toLocaleString()}
          </div>
          <div className={styles.paginationControls}>
            <button
              className={styles.paginationBtn}
              onClick={() => handlePageChange(1)}
              disabled={currentPage === 1}
              title="Первая страница"
            >
              <Icon name="chevrons-left" size={16} />
            </button>
            <button
              className={styles.paginationBtn}
              onClick={() => handlePageChange(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
              title="Предыдущая страница"
            >
              <Icon name="chevron-left" size={16} />
            </button>
            <span className={styles.pageInfo}>
              Страница {currentPage} из {totalPages}
            </span>
            <button
              className={styles.paginationBtn}
              onClick={() => handlePageChange(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
              title="Следующая страница"
            >
              <Icon name="chevron-right" size={16} />
            </button>
            <button
              className={styles.paginationBtn}
              onClick={() => handlePageChange(totalPages)}
              disabled={currentPage === totalPages}
              title="Последняя страница"
            >
              <Icon name="chevrons-right" size={16} />
            </button>
          </div>
          <div className={styles.pageSize}>
            <span>Показывать:</span>
            <select
              value={pageSize}
              onChange={e => handlePageSizeChange(Number(e.target.value))}
            >
              {pageSizeOptions.map(size => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
