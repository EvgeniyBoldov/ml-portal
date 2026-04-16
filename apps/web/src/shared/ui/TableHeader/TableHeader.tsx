/**
 * TableHeader - Reusable table header cell component
 * 
 * Provides consistent styling for all table headers across the app.
 * Supports sorting, custom alignment, and className override.
 */
import React from 'react';
import Popover from '../Popover';
import { Icon } from '../Icon';
import styles from './TableHeader.module.css';

export interface TableHeaderProps {
  label: string;
  width?: number | string;
  align?: 'left' | 'center' | 'right';
  sortable?: boolean;
  sortActive?: boolean;
  sortOrder?: 'asc' | 'desc';
  onSort?: () => void;
  filter?: React.ReactNode;
  filterActive?: boolean;
  className?: string;
}

export const TableHeader = React.forwardRef<HTMLTableCellElement, TableHeaderProps>(
  ({
    label,
    width,
    align = 'left',
    sortable = false,
    sortActive = false,
    sortOrder = 'asc',
    onSort,
    filter,
    filterActive = false,
    className,
  }, ref) => {
    return (
      <th
        ref={ref}
        className={`${styles.header} ${sortable ? styles.sortable : ''} ${sortActive ? styles.active : ''} ${className || ''}`}
        style={{
          width,
          textAlign: align,
        }}
        onClick={sortable ? onSort : undefined}
        role={sortable ? 'button' : undefined}
        tabIndex={sortable ? 0 : undefined}
        onKeyDown={sortable ? (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSort?.();
          }
        } : undefined}
      >
        <div className={styles.inner}>
          <div className={styles.labelRow}>
            <span className={styles.label}>{label}</span>
            {sortable && sortActive && (
              <Icon
                name={sortOrder === 'asc' ? 'chevron-up' : 'chevron-down'}
                size={14}
                className={styles.sortIcon}
              />
            )}
          </div>
          {filter && (
            <div className={styles.filterWrap} onClick={(e) => e.stopPropagation()}>
              <Popover
                align="end"
                content={filter}
                ariaLabel={`Фильтр: ${label}`}
                trigger={
                  <span className={`${styles.filterBtn} ${filterActive ? styles.filterBtnActive : ''}`}>
                    <Icon name="filter" size={14} className={styles.filterIcon} />
                  </span>
                }
              />
            </div>
          )}
        </div>
      </th>
    );
  }
);

TableHeader.displayName = 'TableHeader';

export default TableHeader;
