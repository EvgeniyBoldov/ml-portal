/**
 * DataTable - Reusable table component with selection, search, pagination
 * 
 * Features:
 * - Row selection (single/multiple)
 * - Search/filter
 * - Column filters in header
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
import { Select, type SelectOption } from '../Select';
import { Icon } from '../Icon';
import { Tags } from '../Tags';
import { TableHeader } from '../TableHeader';
import { ActionsButton, type ActionItem } from '../ActionsButton';
import styles from './DataTable.module.css';

export type DataTableFilterKind = 'text' | 'select' | 'tags' | 'date-range';
export type DataTableFilterValue =
  | string
  | string[]
  | { from?: string; to?: string }
  | null;

export interface DataTableColumnFilter<T = any> {
  kind: DataTableFilterKind;
  placeholder?: string;
  options?: SelectOption[];
  match?: 'contains' | 'equals' | 'any' | 'all';
  fromPlaceholder?: string;
  toPlaceholder?: string;
  getValue?: (row: T, columnKey: string) => unknown;
}

export interface DataTableColumn<T = any> {
  key: string;
  label?: string;
  /** Legacy alias */
  title?: string;
  width?: number | string;
  align?: 'left' | 'center' | 'right';
  sortable?: boolean;
  sortValue?: (row: T) => unknown;
  filter?: DataTableColumnFilter<T>;
  render?: (row: T, index: number) => React.ReactNode;
  className?: string;
}

export interface DataTableProps<T = any> {
  columns: DataTableColumn<T>[];
  data: T[];
  keyField?: string;
  /** Legacy alias */
  idField?: string;
  headerActions?: React.ReactNode | ActionItem[];
  beforeTableContent?: React.ReactNode;
  
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
  selectedCountLabel?: (count: number) => React.ReactNode;
  
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
  idField,
  selectable = false,
  selectedKeys: controlledSelectedKeys,
  onSelectionChange,
  searchable = false,
  searchPlaceholder = 'Поиск...',
  searchValue: controlledSearchValue,
  onSearchChange,
  searchFilter,
  paginated = false,
  pageSize: controlledPageSize,
  currentPage: controlledCurrentPage,
  totalItems,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [25, 50, 100],
  bulkActions,
  selectedCountLabel,
  emptyState,
  emptyText = 'Нет данных',
  loading = false,
  className,
  headerActions,
  beforeTableContent,
  rowClassName,
  onRowClick,
}: DataTableProps<T>) {
  const rowKeyField = keyField || idField || 'id';
  const normalizedColumns = useMemo(
    () =>
      columns.map((column) => ({
        ...column,
        label: column.label ?? column.title ?? column.key,
      })),
    [columns],
  );

  // Internal state for uncontrolled mode
  const [internalSelectedKeys, setInternalSelectedKeys] = useState<Set<string | number>>(new Set());
  const [internalSearchValue, setInternalSearchValue] = useState('');
  const [internalCurrentPage, setInternalCurrentPage] = useState(1);
  const [internalPageSize, setInternalPageSize] = useState(controlledPageSize ?? 50);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  const [columnFilters, setColumnFilters] = useState<Record<string, DataTableFilterValue>>({});

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

  const updateColumnFilter = useCallback((key: string, value: DataTableFilterValue) => {
    setColumnFilters(prev => ({
      ...prev,
      [key]: value,
    }));
    setInternalCurrentPage(1);
  }, []);

  const resetColumnFilters = useCallback(() => {
    setColumnFilters({});
    setInternalCurrentPage(1);
  }, []);

  // Filter data
  const filteredData = useMemo(() => {
    const hasSearch = searchable && Boolean(searchValue);
    const activeColumnFilters = normalizedColumns.filter(column => {
      const filter = column.filter;
      if (!filter) return false;
      return !isEmptyFilterValue(columnFilters[column.key], filter.kind);
    });

    let result = data;

    if (hasSearch) {
      if (searchFilter) {
        result = result.filter(row => searchFilter(row, searchValue));
      } else {
        const query = searchValue.toLowerCase();
        result = result.filter(row => {
          return Object.values(toRecord(row)).some(value => {
            if (typeof value === 'string') {
              return value.toLowerCase().includes(query);
            }
            if (typeof value === 'number') {
              return String(value).includes(query);
            }
            if (Array.isArray(value)) {
              return value.some(item => String(item).toLowerCase().includes(query));
            }
            return false;
          });
        });
      }
    }

    if (activeColumnFilters.length > 0) {
      result = result.filter((row) =>
        activeColumnFilters.every((column) =>
          matchesColumnFilter(row, column, columnFilters[column.key]),
        ),
      );
    }

    return result;
  }, [normalizedColumns, columnFilters, data, searchValue, searchable, searchFilter]);

  // Sort data
  const sortedData = useMemo(() => {
    if (!sortKey) return filteredData;
    
    return [...filteredData].sort((a, b) => {
      const column = normalizedColumns.find(col => col.key === sortKey);
      const aVal = column?.sortValue ? column.sortValue(a) : getRowValue(a, sortKey);
      const bVal = column?.sortValue ? column.sortValue(b) : getRowValue(b, sortKey);
      
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
  }, [filteredData, normalizedColumns, sortKey, sortOrder]);

  // Paginate data
  const paginatedData = useMemo(() => {
    if (!paginated) return sortedData;
    const start = (currentPage - 1) * pageSize;
    return sortedData.slice(start, start + pageSize);
  }, [sortedData, paginated, currentPage, pageSize]);

  const total = totalItems ?? filteredData.length;
  const totalPages = Math.ceil(total / pageSize);
  const offset = (currentPage - 1) * pageSize;
  const hasActiveColumnFilters = normalizedColumns.some(column =>
    column.filter && !isEmptyFilterValue(columnFilters[column.key], column.filter.kind),
  );

  // Selection handlers
  const handleSelectAll = useCallback(() => {
    const currentPageKeys = new Set(
      paginatedData
        .map(row => getRowSelectionKey(row, rowKeyField))
        .filter((key): key is string | number => key !== undefined)
    );
    
    // Check if all current page items are selected
    const allSelected = paginatedData.every(row => 
      hasSelectedKey(selectedKeys, row, rowKeyField)
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
  }, [paginatedData, selectedKeys, rowKeyField, handleSelectionChange]);

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
    hasSelectedKey(selectedKeys, row, rowKeyField)
  );

  const someCurrentPageSelected = paginatedData.some(row =>
    hasSelectedKey(selectedKeys, row, rowKeyField)
  );

  return (
    <div className={`${styles.container} ${className || ''}`}>
      {headerActions && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
          {Array.isArray(headerActions) ? <ActionsButton actions={headerActions} /> : headerActions}
        </div>
      )}

      {beforeTableContent && (
        <div style={{ marginBottom: 12 }}>
          {beforeTableContent}
        </div>
      )}

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
                      {selectedCountLabel ? selectedCountLabel(selectedKeys.size) : `Выбрано: ${selectedKeys.size}`}
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
            {hasActiveColumnFilters && (
              <Button
                variant="outline"
                size="small"
                onClick={resetColumnFilters}
              >
                Сбросить фильтры
              </Button>
            )}
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
                {normalizedColumns.map(col => (
                  <TableHeader
                    key={col.key}
                    label={col.label || col.key}
                    width={col.width}
                    align={col.align}
                    sortable={col.sortable}
                    sortActive={sortKey === col.key}
                    sortOrder={sortKey === col.key ? sortOrder : undefined}
                    onSort={col.sortable ? () => handleSort(col.key) : undefined}
                    filter={col.filter ? renderColumnFilter(col, columnFilters[col.key], updateColumnFilter) : undefined}
                    filterActive={col.filter ? !isEmptyFilterValue(columnFilters[col.key], col.filter.kind) : false}
                    className={col.className}
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {paginatedData.map((row, index) => {
                const rowKey = getRowSelectionKey(row, rowKeyField) ?? index;
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
                    {normalizedColumns.map(col => (
                      <td
                        key={col.key}
                        style={{ textAlign: col.align || 'left' }}
                        className={col.className}
                      >
                        {col.render
                          ? col.render(row, index)
                          : String(getRowValue(row, col.key) ?? '—')}
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

function isEmptyFilterValue(value: DataTableFilterValue, kind: DataTableFilterKind): boolean {
  if (value == null) return true;
  if (kind === 'text' || kind === 'select') {
    return String(value).trim().length === 0;
  }
  if (kind === 'tags') {
    return !Array.isArray(value) || value.length === 0;
  }
  if (kind === 'date-range') {
    const range = value as { from?: string; to?: string };
    return !range.from && !range.to;
  }
  return false;
}

function toRecord<T>(row: T): Record<string, unknown> {
  if (row && typeof row === 'object') {
    return row as Record<string, unknown>;
  }
  return {};
}

function getRowValue<T>(row: T, key: string): unknown {
  return toRecord(row)[key];
}

function getRowSelectionKey<T>(row: T, rowKeyField: string): string | number | undefined {
  const key = getRowValue(row, rowKeyField);
  if (typeof key === 'string' || typeof key === 'number') {
    return key;
  }
  return undefined;
}

function hasSelectedKey<T>(selectedKeys: Set<string | number>, row: T, rowKeyField: string): boolean {
  const key = getRowSelectionKey(row, rowKeyField);
  return key !== undefined && selectedKeys.has(key);
}

function normalizeCellValues(value: unknown): string[] {
  if (value == null) return [];
  if (Array.isArray(value)) {
    return value.flatMap(item => normalizeCellValues(item));
  }
  if (value instanceof Date) {
    return [value.toISOString()];
  }
  if (typeof value === 'string') {
    return [value];
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return [String(value)];
  }
  return [String(value)];
}

function matchesColumnFilter<T>(
  row: T,
  column: DataTableColumn<T>,
  value: DataTableFilterValue,
): boolean {
  if (!column.filter || isEmptyFilterValue(value, column.filter.kind)) return true;

  const cellValue = column.filter.getValue
    ? column.filter.getValue(row, column.key)
    : getRowValue(row, column.key);
  const filter = column.filter;

  switch (filter.kind) {
    case 'text': {
      const query = String(value ?? '').trim().toLowerCase();
      if (!query) return true;
      const haystack = normalizeCellValues(cellValue).join(' ').toLowerCase();
      return haystack.includes(query);
    }
    case 'select': {
      const selected = String(value ?? '').trim();
      if (!selected) return true;
      if (Array.isArray(cellValue)) {
        return cellValue.map(String).includes(selected);
      }
      return String(cellValue ?? '') === selected;
    }
    case 'tags': {
      const selectedTags = Array.isArray(value) ? value.map(v => String(v).trim()).filter(Boolean) : [];
      if (selectedTags.length === 0) return true;
      const rowTags = normalizeCellValues(cellValue)
        .flatMap(v => v.split(/[,\s]+/g))
        .map(v => v.trim())
        .filter(Boolean);

      const match = filter.match || 'any';
      if (match === 'all') {
        return selectedTags.every(tag => rowTags.includes(tag));
      }
      return selectedTags.some(tag => rowTags.includes(tag));
    }
    case 'date-range': {
      const range = value as { from?: string; to?: string };
      const raw = cellValue;
      if (!raw) return false;

      const date = raw instanceof Date ? raw : new Date(String(raw));
      if (Number.isNaN(date.getTime())) return false;

      if (range.from) {
        const from = new Date(`${range.from}T00:00:00`);
        if (!Number.isNaN(from.getTime()) && date < from) return false;
      }

      if (range.to) {
        const to = new Date(`${range.to}T23:59:59.999`);
        if (!Number.isNaN(to.getTime()) && date > to) return false;
      }

      return true;
    }
    default:
      return true;
  }
}

function renderColumnFilter<T>(
  column: DataTableColumn<T>,
  value: DataTableFilterValue,
  onChange: (key: string, value: DataTableFilterValue) => void,
) {
  const filter = column.filter!;

  switch (filter.kind) {
    case 'text':
      return (
        <Input
          value={typeof value === 'string' ? value : ''}
          onChange={e => onChange(column.key, e.target.value)}
          placeholder={filter.placeholder || 'Фильтр...'}
          className={styles.columnFilterInput}
        />
      );

    case 'select':
      return (
        <Select
          value={typeof value === 'string' ? value : ''}
          onChange={v => onChange(column.key, v)}
          placeholder={filter.placeholder || 'Все'}
          options={[
            { value: '', label: 'Все' },
            ...(filter.options || []),
          ]}
          className={styles.columnFilterSelect}
        />
      );

    case 'tags':
      return (
        <Tags
          value={Array.isArray(value) ? value : []}
          onChange={(tags) => onChange(column.key, tags)}
          placeholder={filter.placeholder || 'Теги...'}
        />
      );

    case 'date-range': {
      const range = (value && typeof value === 'object' ? value : {}) as { from?: string; to?: string };
      return (
        <div className={styles.dateRangeFilter}>
          <Input
            type="date"
            value={range.from || ''}
            onChange={e => onChange(column.key, { ...range, from: e.target.value || undefined })}
            className={styles.dateRangeInput}
            placeholder={filter.fromPlaceholder || 'От'}
          />
          <Input
            type="date"
            value={range.to || ''}
            onChange={e => onChange(column.key, { ...range, to: e.target.value || undefined })}
            className={styles.dateRangeInput}
            placeholder={filter.toPlaceholder || 'До'}
          />
        </div>
      );
    }

    default:
      return null;
  }
}
